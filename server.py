import os
import json
import requests
from flask import Flask, request, jsonify
from flask_cors import CORS

app = Flask(__name__)
# Enable CORS for all routes to allow the Next.js frontend to connect
CORS(app)

# Load the school information context
try:
    with open("school_info.txt", "r", encoding="utf-8") as f:
        system_context = f.read()
except FileNotFoundError:
    system_context = "Fallback context: St. Anthony's High School Chatbot."
    print("Warning: school_info.txt not found. Using fallback context.")

# Retrieve the API key securely from environment variables
API_KEY = os.environ.get("GEMINI_API_KEY")

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
        contents.append({"role": role, "parts": [{"text": msg.get("content", "")}]})

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

        if "candidates" in response_data:
            reply = response_data["candidates"][0]["content"]["parts"][0]["text"]
            return jsonify({"reply": reply}), 200
        else:
            print("API Error:", response_data)
            return jsonify({"error": "Failed to generate a response from the AI."}), 502
    except Exception as e:
        print("Server Error:", str(e))
        return jsonify({"error": "An internal server error occurred."}), 500

if __name__ == "__main__":
    # Run the server on port 5000
    app.run(host="0.0.0.0", port=5000, debug=True)
