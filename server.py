import os
import json
import time
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
        "Answer questions accurately, naturally, and politely using ONLY the official school information provided below. "
        "If a question is about something not mentioned in the school information below, politely inform the user "
        "that you only have information from the official school records.\n\n"
        + info
    )


# Ordered list of Gemini models:
# Uses Gemini 3.5 Flash Lite and Gemini 3.1 Flash Lite first (highest free quota & fastest response)
# with fallback to Gemini 3.8 Flash, Gemini 3.6 Flash, and Gemini 3.5 Flash
GEMINI_MODELS = (
    "gemini-3.5-flash-lite",
    "gemini-3.1-flash-lite",
    "gemini-3.8-flash",
    "gemini-3.6-flash",
    "gemini-3.5-flash",
)


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
    for msg in history:
        role = "user" if msg.get("role") == "user" else "model"
        text = (msg.get("content") or msg.get("text") or "").strip()
        if not text:
            continue

        # 1. Skip the initial welcome message from the bot so contents ALWAYS starts with "user"
        if not contents and role == "model":
            continue

        # 2. Keep strict "user" <-> "model" alternation so a previous failed turn never breaks the next question
        if contents and contents[-1]["role"] == role:
            if role == "user":
                contents[-1]["parts"] = [{"text": text}]
            else:
                contents[-1]["parts"][0]["text"] += "\n\n" + text
        else:
            contents.append({"role": role, "parts": [{"text": text}]})

    if not contents:
        return jsonify({"error": "No user message found."}), 400

    # Keep the last 6 messages so the conversation stays clean
    contents = contents[-6:]

    system_context = load_system_context()

    payload = {
        "systemInstruction": {
            "parts": [{"text": system_context}]
        },
        "contents": contents
    }

    headers = {"Content-Type": "application/json"}
    last_error = "Failed to generate a response from the AI."

    # 100% Real Gemini AI ONLY — with extended 90-second timeout so responses are never cut off early
    for model_name in GEMINI_MODELS:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={API_KEY}"
        try:
            response = requests.post(url, headers=headers, data=json.dumps(payload), timeout=90)
            response_data = response.json()

            if "candidates" in response_data and len(response_data["candidates"]) > 0:
                candidate = response_data["candidates"][0]
                parts = candidate.get("content", {}).get("parts", [])
                text_chunks = [
                    p["text"]
                    for p in parts
                    if isinstance(p, dict) and p.get("text") and not p.get("thought")
                ]
                if not text_chunks:
                    text_chunks = [p["text"] for p in parts if isinstance(p, dict) and p.get("text")]
                if text_chunks:
                    return jsonify({"reply": "".join(text_chunks)}), 200

            # If this model hit its rate limit (429), high demand (503), or isn't available, immediately try the next model
            last_error = response_data.get("error", {}).get("message", last_error)
            print(f"API Error with {model_name} (status {response.status_code}):", last_error)
            continue
        except Exception as e:
            last_error = str(e)
            print(f"Server Error with {model_name}:", last_error)
            continue

    return jsonify({"error": last_error}), 502


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
