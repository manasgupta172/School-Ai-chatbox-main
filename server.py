import os
import json
import requests
from flask import Flask, request, jsonify
from flask_cors import CORS

app = Flask(__name__)
# Enable CORS for all routes to allow the Next.js frontend to connect
CORS(app)

# Retrieve the API key securely from environment variables
API_KEY = os.environ.get("GEMINI_API_KEY")

# Always load the latest school_info.txt relative to this file
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SCHOOL_INFO_PATH = os.path.join(BASE_DIR, "school_info.txt")


def load_system_context():
    try:
        with open(SCHOOL_INFO_PATH, "r", encoding="utf-8") as f:
            info = f.read()
    except FileNotFoundError:
        info = "Fallback context: St. Anthony's Sr. Sec. School Chatbot."
        print("Warning: school_info.txt not found. Using fallback context.")

    return (
        "You are the official AI Assistant for St. Anthony's Sr. Sec. School, Barabanki. "
        "Answer questions accurately and politely using the official school information below. "
        "When asked about the Principal or his message, share the Principal's name (Fr. Prakash Soreng) "
        "and the Principal Message section below. If a question is not in the school information below, "
        "politely say: 'I do not have that specific information in my official school records. "
        "Please contact the school office directly at 05248-222568 or stanthonybbk@yahoo.com.'\n\n"
        + info
    )


# Try models in order if one is overloaded ("experiencing high demand") on Google's servers
MODELS_TO_TRY = [
    "gemini-3.8-flash",
    "gemini-3.5-flash",
    "gemini-3.8-flash-lite",
    "gemini-3.5-flash-lite",
    "gemini-2.0-flash",
]


@app.route("/api/chat", methods=["POST"])
def chat():
    if not API_KEY:
        return jsonify({"error": "API Key not configured on the server."}), 500

    data = request.get_json(silent=True)
    if not data or "history" not in data:
        return jsonify({"error": "Invalid payload. 'history' is required."}), 400

    history = data["history"]

    # Find the latest user message so a previous failed/overloaded turn NEVER blocks the next question
    latest_user_text = ""
    for msg in reversed(history):
        if msg.get("role") == "user":
            latest_user_text = (msg.get("content") or msg.get("text") or "").strip()
            if latest_user_text:
                break

    if not latest_user_text:
        return jsonify({"error": "No user message found."}), 400

    system_context = load_system_context()

    # Send a clean single-turn request with the full school_info.txt context.
    # This prevents old error messages from ever breaking subsequent questions and saves API tokens!
    payload = {
        "systemInstruction": {
            "parts": [{"text": system_context}]
        },
        "contents": [
            {
                "role": "user",
                "parts": [{"text": latest_user_text}]
            }
        ]
    }

    headers = {"Content-Type": "application/json"}
    last_error = "Failed to generate a response from the AI."

    for model_name in MODELS_TO_TRY:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={API_KEY}"
        try:
            # 12-second timeout per model so Gunicorn's 30-second limit is NEVER reached
            response = requests.post(url, headers=headers, data=json.dumps(payload), timeout=12)
            response_data = response.json()

            if "candidates" in response_data and len(response_data["candidates"]) > 0:
                candidate = response_data["candidates"][0]
                parts = candidate.get("content", {}).get("parts", [])
                text_chunks = [p["text"] for p in parts if isinstance(p, dict) and p.get("text")]
                if text_chunks:
                    return jsonify({"reply": "".join(text_chunks)}), 200
                return jsonify({
                    "reply": "I do not have that specific information in my official school records. Please contact the school office directly at 05248-222568 or stanthonybbk@yahoo.com."
                }), 200
            else:
                last_error = response_data.get("error", {}).get("message", last_error)
                print(f"Model {model_name} unavailable/busy: {last_error}")
                # Immediately try the next model in MODELS_TO_TRY
                continue
        except requests.exceptions.Timeout:
            print(f"Model {model_name} timed out after 12s, trying next model...")
            continue
        except Exception as e:
            print(f"Error with {model_name}: {e}")
            continue

    return jsonify({"error": last_error}), 502


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
