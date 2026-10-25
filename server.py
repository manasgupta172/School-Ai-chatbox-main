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


@app.route("/api/chat", methods=["POST"])
def chat():
    if not API_KEY:
        return jsonify({"error": "API Key not configured on the server."}), 500

    data = request.get_json()
    if not data or "history" not in data:
        return jsonify({"error": "Invalid payload. 'history' is required."}), 400

    history = data["history"]
    contents = []

    # Map the frontend history format to the Gemini API format
    # Frontend format: { "role": "user" | "ai", "content": "..." }
    for msg in history:
        role = "user" if msg.get("role") == "user" else "model"
        text = (msg.get("content") or msg.get("text") or "").strip()
        if not text:
            continue
        contents.append({"role": role, "parts": [{"text": text}]})

    system_context = load_system_context()

    payload = {
        "systemInstruction": {
            "parts": [{"text": system_context}]
        },
        "contents": contents
    }

    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-3.5-flash:generateContent?key={API_KEY}"
    headers = {"Content-Type": "application/json"}

    try:
        response = requests.post(url, headers=headers, data=json.dumps(payload))
        response_data = response.json()

        if "candidates" in response_data and len(response_data["candidates"]) > 0:
            candidate = response_data["candidates"][0]
            parts = candidate.get("content", {}).get("parts", [])
            if parts and "text" in parts[0]:
                reply = parts[0]["text"]
                return jsonify({"reply": reply}), 200
            else:
                return jsonify({
                    "reply": "I do not have that specific information in my official school records. Please contact the school office directly at 05248-222568 or stanthonybbk@yahoo.com."
                }), 200
        else:
            print("API Error:", response_data)
            return jsonify({"error": "Failed to generate a response from the AI."}), 502
    except Exception as e:
        print("Server Error:", str(e))
        return jsonify({"error": "An internal server error occurred."}), 500


if __name__ == "__main__":
    # Run the server on port 5000
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
