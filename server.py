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
        "Answer questions naturally, concisely, and politely using ONLY the official school information below. "
        "Important rules:\n"
        "1. Do NOT dump huge raw paragraphs when a user asks a specific question. Give a clean, well-formatted, direct answer.\n"
        "2. When asked about the Principal or his message, state that the Principal is **Fr. Prakash Soreng** and share the **Principal's Message** section clearly.\n"
        "3. Be smart with spelling variations and honorifics for teachers/staff (for example, 'Lily ma'am', 'Lily', or 'Lily Mishra' refers to **Mrs. Lilly Mishra** (PGT); 'Praveen' refers to **Ms. Rana Parveen** or **Ms. Kuba Parveen** (PRT/PPRT); 'Father' or 'Fr.' refers to priests/administration).\n"
        "4. If a detail is genuinely not in the school information below, politely say: "
        "'I do not have that specific information in my official school records. Please contact the school office directly at 05248-222568 or stanthonybbk@yahoo.com.'\n\n"
        + info
    )


def extract_sections(info: str):
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
    return sections


def find_staff_matches(query: str, info: str):
    """Exact, ranked staff name matcher so 'who is lily mishra' ONLY returns Mrs. Lilly Mishra and never matches random sentences."""
    q_lower = query.lower()
    ignore = {
        "who", "what", "is", "are", "the", "about", "tell", "me", "maam", "ma", "am",
        "mam", "madam", "sir", "teacher", "staff", "faculty", "miss", "mrs", "mr",
        "ms", "dr", "fr", "father", "sister", "sr", "in", "of", "at", "school",
        "anthony", "anthonys", "please", "know", "do", "you", "message", "his", "her"
    }
    tokens = [t for t in re.findall(r"[a-z]+", q_lower) if t not in ignore and len(t) >= 3]
    if not tokens:
        return []

    def normalize(word: str) -> str:
        # Collapse double letters ("lilly" -> "lily") and common spelling variations
        w = re.sub(r"(.)\1+", r"\1", word.lower())
        w = w.replace("parveen", "praveen").replace("praveen", "parveen")
        w = w.replace("shrivastav", "srivastav").replace("srivastava", "srivastav")
        return w

    norm_tokens = [normalize(t) for t in tokens]

    # Extract ONLY clean person names (starting with Mrs., Mr., Ms., Sr., Fr., Dr.) and their category
    person_pattern = re.compile(
        r"\b((?:Mrs?\.|Ms\.|Sr\.|Fr\.|Dr\.)\s+[A-Z][A-Za-z.\s]{2,35}?)(?=\s*(?:[,;.\n]|—|-|\(|$))"
    )

    candidates = []
    seen_names = set()

    # Determine role category based on surrounding section text
    for line in info.splitlines():
        line_s = line.strip()
        if not line_s:
            continue

        # Split line into category chunks if PGT:, TGT:, PRT / PPRT:, Specialist staff: appear inline
        chunks = re.split(r"(?=(?:PGT:|TGT:|PRT / PPRT:|Specialist staff:))", line_s)
        for chunk in chunks:
            role_label = "Faculty / Administration"
            if chunk.startswith("PGT:"):
                role_label = "Post Graduate Teacher (PGT)"
            elif chunk.startswith("TGT:"):
                role_label = "Trained Graduate Teacher (TGT)"
            elif chunk.startswith("PRT / PPRT:"):
                role_label = "Primary / Pre-Primary Teacher (PRT / PPRT)"
            elif chunk.startswith("Specialist staff:"):
                role_label = "Specialist Staff"

            for match in person_pattern.finditer(chunk):
                person_name = match.group(1).strip().rstrip(".,;:")
                # Skip historical bishops/priests if already covered or keep clean role
                if person_name in seen_names:
                    continue
                name_words = [
                    normalize(w)
                    for w in re.findall(r"[a-zA-Z]+", person_name)
                    if w.lower() not in {"mrs", "mr", "ms", "sr", "fr", "dr"} and len(w) >= 3
                ]
                if not name_words:
                    continue

                # Count how many query tokens match this person's actual name words
                matched_count = 0
                for nt in norm_tokens:
                    if any(nt == nw or (len(nt) >= 4 and len(nw) >= 4 and (nt in nw or nw in nt)) for nw in name_words):
                        matched_count += 1

                if matched_count > 0:
                    seen_names.add(person_name)
                    candidates.append((matched_count, person_name, role_label))

    if not candidates:
        return []

    # Keep ONLY the highest-scoring matches (e.g., if user typed "lily mishra" (2 words),
    # ONLY return Mrs. Lilly Mishra (score 2), NOT other teachers named Mishra (score 1)!)
    max_score = max(c[0] for c in candidates)
    best_matches = [
        f"**{name}** is a **{role}** at St. Anthony's Sr. Sec. School, Barabanki."
        for score, name, role in candidates
        if score == max_score
    ]
    return best_matches


def local_school_info_answer(query: str, info: str) -> str:
    """Concise, natural fallback answer engine over school_info.txt when Gemini API is busy."""
    q = query.lower().strip()
    sections = extract_sections(info)

    # 1. Greetings
    if q in ("hi", "hello", "hey", "hii", "hiii", "good morning", "good afternoon", "good evening"):
        return (
            "Hello! Welcome to **St. Anthony's Sr. Sec. School, Barabanki**.\n\n"
            "How can I assist you today? Feel free to ask about our **Principal & Principal's Message**, "
            "**School Timings**, **Admissions**, **School Uniform**, **Student Council**, **Faculty & Staff**, or **School Rules**!"
        )

    # 2. Principal & Principal's Message
    if any(k in q for k in ("principal", "prakash", "soreng")):
        principal_msg = ""
        for heading, body, _ in sections:
            if "principal" in heading.lower() and "message" in heading.lower():
                principal_msg = body.strip()
                break

        if "message" in q or principal_msg:
            msg_block = f"\n\n### Principal's Message\n{principal_msg}" if principal_msg else ""
            return (
                "The Principal of St. Anthony's Sr. Sec. School, Barabanki is **Fr. Prakash Soreng** (2025 – Present)."
                + msg_block
            )
        return "The Principal of St. Anthony's Sr. Sec. School, Barabanki is **Fr. Prakash Soreng** (serving from 2025 to present)."

    # 3. Specific Teacher / Staff Lookup (e.g. "who is lily mishra", "who is lily ma'am", "who is Praveen")
    staff_matches = find_staff_matches(query, info)
    if staff_matches and not any(k in q for k in ("timing", "uniform", "fee", "admission", "stream", "syllabus", "history")):
        if len(staff_matches) == 1:
            return f"Based on our official school records, {staff_matches[0]}"
        else:
            return (
                "Based on our official school records, here are the matching faculty members:\n\n"
                + "\n".join(f"- {m}" for m in staff_matches)
            )

    # 4. School Timings
    if any(k in q for k in ("timing", "time", "hours", "schedule", "summer", "winter", "recess")):
        for heading, body, _ in sections:
            if "timing" in heading.lower() or "schedule" in heading.lower():
                return f"### {heading}\n\n{body}"

    # 5. School Uniform
    if any(k in q for k in ("uniform", "dress", "blazer", "shirt", "tie", "skirt", "trouser")):
        for heading, body, _ in sections:
            if "uniform" in heading.lower():
                return f"### {heading}\n\n{body}"

    # 6. Student Council & Houses
    if any(k in q for k in ("council", "head boy", "head girl", "captain", "prefect", "house", "cabinet")):
        for heading, body, _ in sections:
            if "council" in heading.lower() or "house" in heading.lower() or "cabinet" in heading.lower():
                return f"### {heading}\n\n{body}"

    # 7. Admissions & Withdrawals
    if any(k in q for k in ("admission", "withdraw", "tc", "transfer certificate", "age criteria", "document", "registration")):
        for heading, body, _ in sections:
            if "admission" in heading.lower():
                return f"### {heading}\n\n{body}"

    # 8. Fee Structure
    if any(k in q for k in ("fee", "payment", "installment", "tuition")):
        for heading, body, _ in sections:
            if "fee" in heading.lower():
                return f"### {heading}\n\n{body}"

    # 9. Curriculum & Streams
    if any(k in q for k in ("stream", "subject", "curriculum", "syllabus", "science", "commerce", "ncert", "cbse")):
        for heading, body, _ in sections:
            if "curriculum" in heading.lower() or "stream" in heading.lower():
                return f"### {heading}\n\n{body}"

    # 10. Examinations & Promotion
    if any(k in q for k in ("exam", "promotion", "grading", "attendance", "pass")):
        for heading, body, _ in sections:
            if "examination" in heading.lower() or "promotion" in heading.lower():
                return f"### {heading}\n\n{body}"

    # 11. Rules & Code of Conduct
    if any(k in q for k in ("rule", "discipline", "conduct", "mobile", "phone", "late", "punish")):
        for heading, body, _ in sections:
            if "conduct" in heading.lower() or "rule" in heading.lower() or "discipline" in heading.lower():
                return f"### {heading}\n\n{body}"

    # 12. Facilities & Infrastructure
    if any(k in q for k in ("facility", "facilities", "infrastructure", "lab", "library", "transport", "bus", "playground", "cctv")):
        for heading, body, _ in sections:
            if "infrastructure" in heading.lower() or "facilities" in heading.lower():
                return f"### {heading}\n\n{body}"

    # 13. Managing Committee
    if "managing committee" in q or "committee" in q or "minority" in q:
        for heading, body, _ in sections:
            if "managing" in heading.lower():
                return f"### {heading}\n\n{body}"

    # 14. History & About
    if any(k in q for k in ("history", "founded", "patron", "antony", "diocese", "bishop", "about", "mission", "motto")):
        for heading, body, _ in sections:
            if any(w in heading.lower() for w in ("mission", "history", "about")):
                return f"### {heading}\n\n{body}"

    # 15. Contact Info
    if any(k in q for k in ("contact", "phone", "email", "address", "location", "website", "where")):
        for heading, body, _ in sections:
            if "contact" in heading.lower() or "st. anthony" in heading.lower():
                return f"### {heading}\n\n{body}"

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
        ],
        "generationConfig": {
            "thinkingConfig": {
                "thinkingBudget": 0
            },
            "maxOutputTokens": 800,
            "temperature": 0.3
        }
    }

    headers = {
        "Content-Type": "application/json",
        "X-goog-api-key": API_KEY or "",
    }

    if API_KEY:
        for model_name in ("gemini-flash-latest", "gemini-3.5-flash", "gemini-3.8-flash"):
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={API_KEY}"
            try:
                response = requests.post(url, headers=headers, data=json.dumps(payload), timeout=12)
                response_data = response.json()

                if response.status_code == 400 and "thinkingConfig" in json.dumps(response_data):
                    simple_payload = {
                        "systemInstruction": payload["systemInstruction"],
                        "contents": payload["contents"],
                    }
                    response = requests.post(url, headers=headers, data=json.dumps(simple_payload), timeout=12)
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
            except Exception as e:
                print(f"Error with {model_name}: {e}")
                continue

    # Instant, clean, concise fallback from school_info.txt if Google's API is busy
    fallback_reply = local_school_info_answer(latest_user_text, school_info)
    return jsonify({"reply": fallback_reply}), 200


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
