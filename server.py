import os
import json
import requests
from flask import Flask, request, jsonify
from flask_cors import CORS

app = Flask(__name__)
# Enable CORS for all routes to allow the Next.js frontend to connect
CORS(app)

# Always load school_info.txt relative to this script's directory
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SCHOOL_INFO_PATH = os.path.join(BASE_DIR, "school_info.txt")

try:
    with open(SCHOOL_INFO_PATH, "r", encoding="utf-8") as f:
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
# Use gemini-flash-latest directly (from Google AI Studio cURL quickstart)
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-flash-latest")


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

    # Keep only recent conversation turns and disable heavy "thinking" tokens
    # so Gemini responds in ~2-4 seconds (well under Gunicorn's 30-second worker timeout)
    payload = {
        "systemInstruction": {
            "parts": [{"text": SYSTEM_INSTRUCTION}]
        },
        "contents": contents[-10:],
        "generationConfig": {
            "thinkingConfig": {
                "thinkingBudget": 0
            },
            "maxOutputTokens": 1024,
            "temperature": 0.3
        }
    }

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"
    headers = {
        "Content-Type": "application/json",
        "X-goog-api-key": API_KEY,
    }

    try:
        response = requests.post(url, headers=headers, data=json.dumps(payload), timeout=25)
        response_data = response.json()

        # If the model doesn't support thinkingConfig, retry once without thinkingConfig
        if response.status_code == 400 and "thinkingConfig" in json.dumps(response_data):
            payload.pop("generationConfig", None)
            response = requests.post(url, headers=headers, data=json.dumps(payload), timeout=25)
            response_data = response.json()

        candidates = response_data.get("candidates")
        if candidates and len(candidates) > 0:
            content_obj = candidates[0].get("content", {})
            parts = content_obj.get("parts", [])
            # Collect all non-thought text parts safely
            text_chunks = [
                p["text"]
                for p in parts
                if isinstance(p, dict) and p.get("text") and not p.get("thought")
            ]
            if not text_chunks:
                text_chunks = [p["text"] for p in parts if isinstance(p, dict) and p.get("text")]

            if text_chunks:
                reply = "".join(text_chunks)
                return jsonify({"reply": reply}), 200

            return jsonify({
                "reply": "I don't have that specific information in my official school records. Please contact the school administration directly at 05248-222568 or stanthonybbk@yahoo.com for assistance."
            }), 200
        else:
            print("API Error:", response_data)
            error_detail = response_data.get("error", {}).get("message", "Failed to generate a response from the AI.")
            return jsonify({"error": error_detail}), 502
    except Exception as e:
        print("Server Error:", str(e))
        return jsonify({"error": "The AI server took too long to respond. Please try asking again."}), 500


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
