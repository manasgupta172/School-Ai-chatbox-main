import os
import json
import requests
from flask import Flask, request, jsonify
from flask_cors import CORS

app = Flask(__name__)
# Enable CORS for all routes to allow the Next.js frontend to connect
CORS(app)

# Load the school information context dynamically from school_info.txt
try:
    with open("school_info.txt", "r", encoding="utf-8") as f:
        school_context = f.read()
except FileNotFoundError:
    school_context = "Fallback context: St. Anthony's Sr. Sec. School, Barabanki Chatbot."
    print("Warning: school_info.txt not found. Using fallback context.")

SYSTEM_INSTRUCTION = f"""You are the official AI Assistant for St. Anthony's Sr. Sec. School, Barabanki.
Answer questions from students, parents, and visitors accurately, politely, and clearly using ONLY the official school records provided below.

Official School Information:
{school_context}

Rules for responding:
1. If the user asks about the Principal or the Principal's Message, provide the Principal's name (Fr. Prakash Soreng) and the Principal's Message from the Official School Information above.
2. If a user asks a question that is outside the scope of the Official School Information or not mentioned in the records, do NOT fail or return an empty response—politely reply: "I don't have that specific information in my official school records. Please contact the school office directly at 05248-222568 or stanthonybbk@yahoo.com for further assistance."
3. Format responses cleanly using Markdown (bullet points and bold text where helpful).
"""

# Retrieve the API key securely from environment variables
API_KEY = os.environ.get("GEMINI_API_KEY")

# Ordered list of Gemini models to try automatically
CANDIDATE_MODELS = [
    os.environ.get("GEMINI_MODEL", "gemini-3.5-flash"),
    "gemini-3.8-flash",
    "gemini-2.5-flash",
]


@app.route("/api/chat", methods=["POST"])
def chat():
    if not API_KEY:
        return jsonify({"error": "API Key not configured on the server."}), 500

    data = request.get_json(silent=True)
    if not data or "history" not in data:
        return jsonify({"error": "Invalid payload. 'history' is required."}), 400

    history = data["history"]
    contents = []

    # Map the frontend history format to the Gemini API format
    # Frontend sends: { "role": "user" | "ai" | "model", "content" | "text": "..." }
    for msg in history:
        role = "user" if msg.get("role") == "user" else "model"
        text = (msg.get("content") or msg.get("text") or "").strip()

        if not text:
            continue

        # Gemini API requires the first turn in `contents` to be from "user"
        # Skip the initial hardcoded welcome message from the assistant
        if not contents and role == "model":
            continue

        # Prevent consecutive messages with the same role (which happens if a prior turn failed)
        # If two "user" messages appear back-to-back, replace the failed/unanswered turn with the latest one
        if contents and contents[-1]["role"] == role:
            if role == "user":
                contents[-1]["parts"] = [{"text": text}]
            else:
                contents[-1]["parts"][0]["text"] += "\n\n" + text
        else:
            contents.append({"role": role, "parts": [{"text": text}]})

    if not contents:
        return jsonify({"error": "No user message found in history."}), 400

    payload = {
        "systemInstruction": {
            "parts": [{"text": SYSTEM_INSTRUCTION}]
        },
        "contents": contents
    }

    headers = {"Content-Type": "application/json"}
    last_error = "Failed to generate a response from the AI."

    # Try candidate models in order (gemini-3.5-flash -> gemini-3.8-flash -> gemini-2.5-flash)
    seen_models = set()
    for model_name in CANDIDATE_MODELS:
        if not model_name or model_name in seen_models:
            continue
        seen_models.add(model_name)

        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={API_KEY}"
        try:
            response = requests.post(url, headers=headers, data=json.dumps(payload), timeout=30)
            response_data = response.json()

            candidates = response_data.get("candidates")
            if candidates and len(candidates) > 0:
                content_obj = candidates[0].get("content", {})
                parts = content_obj.get("parts", [])
                if parts and "text" in parts[0]:
                    reply = parts[0]["text"]
                    return jsonify({"reply": reply}), 200

                # Handle cases where the model stopped early without text parts
                return jsonify({
                    "reply": "I don't have that specific information in my official school records. Please contact the school administration directly at 05248-222568 or stanthonybbk@yahoo.com for assistance."
                }), 200
            else:
                last_error = response_data.get("error", {}).get("message", last_error)
                print(f"API Error with {model_name}:", response_data)
        except Exception as e:
            last_error = str(e)
            print(f"Server Error with {model_name}:", last_error)

    return jsonify({"error": last_error}), 502


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
