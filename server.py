import os
import json
import re
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


def load_school_info() -> str:
    try:
        with open(SCHOOL_INFO_PATH, "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        print("Warning: school_info.txt not found. Using fallback context.")
        return "St. Anthony's Sr. Sec. School, Civil Lines, Court Road, Barabanki, Uttar Pradesh – 225001."


def select_relevant_context(query: str, full_info: str) -> str:
    """Selects the relevant sections of school_info.txt (plus core school overview)
    so Gemini processes ~10x fewer tokens and responds in 2-4 seconds instead of timing out!
    """
    raw_sections = re.split(r"\n(?=\*+)", "\n" + full_info)
    sections = [s.strip() for s in raw_sections if s.strip()]
    if len(sections) <= 3:
        return full_info

    q_lower = query.lower()
    # Extract meaningful search words from the user's question
    words = [
        w
        for w in re.findall(r"[a-z0-9]+", q_lower)
        if len(w) >= 3
        and w not in {"what", "whats", "who", "where", "when", "how", "the", "and", "for", "are", "school", "anthony", "anthonys", "tell", "about", "can", "you"}
    ]

    # Always keep the first overview section so Gemini always knows the school's core details
    selected = [sections[0]]

    scored = []
    for idx, sec in enumerate(sections[1:], start=1):
        sec_lower = sec.lower()
        heading_line = sec.splitlines()[0].lower()
        score = 0

        for w in words:
            if w in heading_line:
                score += 6
            elif w in sec_lower:
                score += 2
            # Handle common spelling variations (e.g. lily <-> lilly, praveen <-> parveen)
            w_collapsed = re.sub(r"(.)\1+", r"\1", w)
            if len(w_collapsed) >= 3 and w_collapsed in re.sub(r"(.)\1+", r"\1", sec_lower):
                score += 2

        # Ensure Principal queries always include both Principal Message and Administration sections
        if any(k in q_lower for k in ("principal", "prakash", "soreng", "message")):
            if "principal" in heading_line or "administration" in heading_line or "prakash" in sec_lower:
                score += 10

        # Ensure anthem / motto / prayer / patron queries include History / Mission / Anthem sections
        if any(k in q_lower for k in ("anthem", "song", "prayer", "motto", "patron", "history", "founded")):
            if any(h in heading_line for h in ("anthem", "mission", "history", "about", "prayer")):
                score += 10

        # Ensure council / cabinet / prefect / house queries include Student Council & Cabinet sections
        if any(k in q_lower for k in ("council", "cabinet", "head boy", "head girl", "prefect", "captain", "house")):
            if any(h in heading_line for h in ("council", "cabinet", "house")):
                score += 10

        if score > 0:
            scored.append((score, idx, sec))

    scored.sort(key=lambda x: (-x[0], x[1]))

    # Pick top 4 matching sections (or all sections if the query is very broad)
    if scored:
        for _, _, sec in scored[:4]:
            if sec not in selected:
                selected.append(sec)
        return "\n\n".join(selected)

    return full_info


@app.route("/api/chat", methods=["POST"])
def chat():
    if not API_KEY:
        return jsonify({"error": "API Key not configured on the server."}), 500

    data = request.get_json(silent=True)
    if not data or "history" not in data:
        return jsonify({"error": "Invalid payload. 'history' is required."}), 400

    history = data["history"]

    # Get the latest user question
    latest_user_text = ""
    for msg in reversed(history):
        if msg.get("role") == "user":
            latest_user_text = (msg.get("content") or msg.get("text") or "").strip()
            if latest_user_text:
                break

    if not latest_user_text:
        return jsonify({"error": "No user message found."}), 400

    full_info = load_school_info()
    relevant_info = select_relevant_context(latest_user_text, full_info)

    # Put the concise context + user question together in a single fast user prompt
    prompt_text = (
        "You are the official AI Assistant for St. Anthony's Sr. Sec. School, Barabanki (independently developed by Manas Gupta, Class 12 PCM + Computer Science student).\n"
        "Answer the user's question accurately, naturally, and concisely using ONLY the official school records below. "
        "If the answer is not in the records below, politely say that you do not have that specific information in the official school records and share the school contact (05248-222568 / stanthonybbk@yahoo.com).\n\n"
        f"--- OFFICIAL SCHOOL RECORDS ---\n{relevant_info}\n--- END OF RECORDS ---\n\n"
        f"User Question: {latest_user_text}"
    )

    payload = {
        "contents": [
            {
                "role": "user",
                "parts": [{"text": prompt_text}]
            }
        ]
    }

    headers = {"Content-Type": "application/json"}
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-3.5-flash-lite:generateContent?key={API_KEY}"

    try:
        response = requests.post(url, headers=headers, data=json.dumps(payload), timeout=25)
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

        last_error = response_data.get("error", {}).get("message", "Failed to generate a response from the AI.")
        print("API Error:", response_data)
        return jsonify({"error": last_error}), 502
    except Exception as e:
        print("Server Error:", str(e))
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
