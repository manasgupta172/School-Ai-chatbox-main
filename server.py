import os
import json
import time
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


def load_school_info():
    try:
        with open(SCHOOL_INFO_PATH, "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        print("Warning: school_info.txt not found. Using fallback context.")
        return "St. Anthony's Sr. Sec. School, Civil Lines, Court Road, Barabanki, Uttar Pradesh – 225001."


def build_system_context(info: str) -> str:
    return (
        "You are the official AI Assistant for St. Anthony's Sr. Sec. School, Barabanki. "
        "Answer questions accurately and politely using the official school information below. "
        "When asked about the Principal or his message, share the Principal's name (Fr. Prakash Soreng) "
        "and the Principal Message section below. If a question is not in the school information below, "
        "politely say: 'I do not have that specific information in my official school records. "
        "Please contact the school office directly at 05248-222568 or stanthonybbk@yahoo.com.'\n\n"
        + info
    )


def local_school_info_answer(query: str, info: str) -> str:
    """Instant fallback search over school_info.txt so the chatbot ALWAYS answers even when Google's free tier is overloaded."""
    q = query.lower().strip()

    # Greetings
    if q in ("hi", "hello", "hey", "hii", "hiii", "good morning", "good afternoon", "good evening"):
        return (
            "Hello! Welcome to **St. Anthony's Sr. Sec. School, Barabanki**.\n\n"
            "How can I assist you today? Feel free to ask about our **Principal & Principal's Message**, "
            "**School Timings**, **Admissions**, **School Uniform**, **Student Council**, **Staff**, or **School Rules**!"
        )

    # Split school_info.txt into sections by '*' headings
    raw_sections = re.split(r"\n(?=\*+)", "\n" + info)
    sections = []
    for sec in raw_sections:
        sec = sec.strip()
        if not sec:
            continue
        lines = sec.splitlines()
        heading = lines[0].lstrip("*").strip()
        body = "\n".join(lines[1:]).strip()
        sections.append((heading, body, sec))

    # Specific high-priority topic matching
    if any(k in q for k in ("principal", "prakash", "soreng", "father", "fr.")):
        matched = []
        for heading, body, full in sections:
            if "principal" in heading.lower() or "administration" in heading.lower() or "fr. prakash soreng" in full.lower():
                matched.append(f"### {heading}\n{body}")
        if matched:
            return (
                "**Principal:** Fr. Prakash Soreng\n\n"
                + "\n\n".join(matched)
            )

    if any(k in q for k in ("timing", "time", "hours", "schedule", "summer", "winter", "recess")):
        for heading, body, _ in sections:
            if "timing" in heading.lower() or "schedule" in heading.lower():
                return f"### {heading}\n\n{body}"

    if any(k in q for k in ("uniform", "dress", "blazer", "shirt", "tie", "skirt", "trouser")):
        for heading, body, _ in sections:
            if "uniform" in heading.lower():
                return f"### {heading}\n\n{body}"

    if any(k in q for k in ("council", "head boy", "head girl", "captain", "prefect", "house")):
        for heading, body, _ in sections:
            if "council" in heading.lower() or "house" in heading.lower():
                return f"### {heading}\n\n{body}"

    if any(k in q for k in ("admission", "withdraw", "tc", "transfer certificate", "age criteria", "document", "registration")):
        for heading, body, _ in sections:
            if "admission" in heading.lower():
                return f"### {heading}\n\n{body}"

    if any(k in q for k in ("fee", "payment", "installment", "tuition")):
        for heading, body, _ in sections:
            if "fee" in heading.lower():
                return f"### {heading}\n\n{body}"

    if any(k in q for k in ("stream", "subject", "curriculum", "syllabus", "science", "commerce", "ncert", "cbse")):
        for heading, body, _ in sections:
            if "curriculum" in heading.lower() or "stream" in heading.lower():
                return f"### {heading}\n\n{body}"

    if any(k in q for k in ("exam", "promotion", "grading", "attendance", "pass")):
        for heading, body, _ in sections:
            if "examination" in heading.lower() or "promotion" in heading.lower():
                return f"### {heading}\n\n{body}"

    if any(k in q for k in ("rule", "discipline", "conduct", "mobile", "phone", "late", "punish")):
        for heading, body, _ in sections:
            if "conduct" in heading.lower() or "rule" in heading.lower() or "discipline" in heading.lower():
                return f"### {heading}\n\n{body}"

    if any(k in q for k in ("facility", "facilities", "infrastructure", "lab", "library", "transport", "bus", "playground", "cctv")):
        for heading, body, _ in sections:
            if "infrastructure" in heading.lower() or "facilities" in heading.lower():
                return f"### {heading}\n\n{body}"

    if any(k in q for k in ("history", "founded", "patron", "antony", "diocese", "bishop", "managing committee", "about", "mission", "motto")):
        matched = [
            f"### {heading}\n\n{body}"
            for heading, body, _ in sections
            if any(w in heading.lower() for w in ("mission", "history", "managing", "st. anthony"))
        ]
        if matched:
            return "\n\n".join(matched)

    if any(k in q for k in ("contact", "phone", "email", "address", "location", "website", "where")):
        for heading, body, _ in sections:
            if "contact" in heading.lower():
                return f"### {heading}\n\n{body}"

    if any(k in q for k in ("staff", "teacher", "faculty", "administration")):
        for heading, body, _ in sections:
            if "administration" in heading.lower() or "staff" in heading.lower():
                return f"### {heading}\n\n{body}"

    if any(k in q for k in ("calendar", "vacation", "holiday", "term")):
        for heading, body, _ in sections:
            if "calendar" in heading.lower() or "term" in heading.lower():
                return f"### {heading}\n\n{body}"

    # General keyword scoring across all sections in school_info.txt
    words = [w for w in re.findall(r"[a-z0-9]+", q) if len(w) > 2 and w not in {"what", "who", "where", "when", "how", "the", "and", "for", "are", "school", "anthony", "tell", "about", "can", "you", "his", "her"}]
    if words:
        scored = []
        for heading, body, full in sections:
            full_lower = full.lower()
            score = sum(3 if w in heading.lower() else (1 if w in full_lower else 0) for w in words)
            if score > 0:
                scored.append((score, f"### {heading}\n\n{body}"))
        scored.sort(key=lambda x: x[0], reverse=True)
        if scored:
            return scored[0][1]

    # Polite out-of-scope response when the topic is not in school_info.txt
    return (
        "I do not have that specific information in my official school records. "
        "Please contact the school office directly at **05248-222568** or **stanthonybbk@yahoo.com** for further assistance."
    )


@app.route("/api/chat", methods=["POST"])
def chat():
    data = request.get_json(silent=True)
    if not data or "history" not in data:
        return jsonify({"error": "Invalid payload. 'history' is required."}), 400

    history = data["history"]

    # Extract the latest user question
    latest_user_text = ""
    for msg in reversed(history):
        if msg.get("role") == "user":
            latest_user_text = (msg.get("content") or msg.get("text") or "").strip()
            if latest_user_text:
                break

    if not latest_user_text:
        return jsonify({"error": "No user message found."}), 400

    school_info = load_school_info()
    system_context = build_system_context(school_info)

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

    # 1. Try gemini-3.8-flash and gemini-3.5-flash on Google's API first
    if API_KEY:
        for model_name in ("gemini-3.8-flash", "gemini-3.5-flash"):
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={API_KEY}"
            try:
                response = requests.post(url, headers=headers, data=json.dumps(payload), timeout=10)
                response_data = response.json()

                if "candidates" in response_data and len(response_data["candidates"]) > 0:
                    candidate = response_data["candidates"][0]
                    parts = candidate.get("content", {}).get("parts", [])
                    text_chunks = [p["text"] for p in parts if isinstance(p, dict) and p.get("text")]
                    if text_chunks:
                        return jsonify({"reply": "".join(text_chunks)}), 200
            except Exception as e:
                print(f"Error with {model_name}: {e}")
                continue

    # 2. If Google's Gemini API is experiencing high demand / rate-limited,
    # immediately answer directly from school_info.txt so the user NEVER sees an error!
    fallback_reply = local_school_info_answer(latest_user_text, school_info)
    return jsonify({"reply": fallback_reply}), 200


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
