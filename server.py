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
        "Answer questions naturally, concisely, and politely using ONLY the official school information below.\n"
        "Important rules:\n"
        "1. Give clean, well-formatted, direct answers using Markdown. Never dump huge raw unformatted paragraphs.\n"
        "2. Developer / Creator: If asked about **Manas**, **Manas Gupta**, or who created/developed this chatbot, state that **Manas Gupta** is a Class 12 PCM student at St. Anthony's Sr. Sec. School, Barabanki (and was also the Yellow House Prefect in 2024–25) who independently developed this official AI Chatbot.\n"
        "3. Principal & Message: When asked about the Principal or his message, state that the Principal is **Fr. Prakash Soreng** (2025 – Present) and share the **Principal's Message** section clearly.\n"
        "4. Staff & Student Council Names: Handle spelling variations and honorifics intelligently (e.g., 'Lily ma'am' or 'Lily' -> **Mrs. Lilly Mishra** (PGT); 'Praveen' -> **Ms. Rana Parveen** & **Ms. Kuba Parveen** (PRT/PPRT); 'Swati Gupta' -> **Mrs. Swati Gupta** (Special Educator); never confuse 'Manas Gupta' with 'Mrs. Swati Gupta').\n"
        "5. If a detail is genuinely not in the school information below, politely say: "
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


def normalize_word(word: str) -> str:
    w = re.sub(r"(.)\1+", r"\1", word.lower())
    w = w.replace("parveen", "praveen").replace("praveen", "parveen")
    w = w.replace("shrivastav", "srivastav").replace("srivastava", "srivastav")
    return w


def find_people_in_records(query: str, info: str):
    """Accurately finds any person (Teacher, Principal, Staff, or Student Council member) in school_info.txt.
    Requires ALL name words in the user's query to match the person's name so 'manas gupta' NEVER matches 'Mrs. Swati Gupta'.
    """
    q_lower = query.lower()
    ignore = {
        "who", "what", "is", "are", "was", "the", "about", "tell", "me", "maam", "ma", "am",
        "mam", "madam", "sir", "teacher", "staff", "faculty", "miss", "mrs", "mr",
        "ms", "dr", "fr", "father", "sister", "sr", "in", "of", "at", "school",
        "anthony", "anthonys", "please", "know", "do", "you", "message", "his", "her", "role"
    }
    tokens = [t for t in re.findall(r"[a-z]+", q_lower) if t not in ignore and len(t) >= 3]
    if not tokens:
        return []

    norm_tokens = [normalize_word(t) for t in tokens]

    # Build a complete directory of people from school_info.txt + known developer credit
    people_directory = [
        (
            "Manas Gupta",
            "Class 12 PCM student at St. Anthony's Sr. Sec. School, Barabanki (and Yellow House Prefect in the 2024–25 Student Cabinet) who independently developed this official St. Anthony's AI Chatbot",
        )
    ]

    # 1. Extract titled staff/admin names (Mrs., Mr., Ms., Sr., Fr., Dr.)
    person_pattern = re.compile(
        r"\b((?:Mrs?\.|Ms\.|Sr\.|Fr\.|Dr\.)\s+[A-Z][A-Za-z.\s]{2,35}?)(?=\s*(?:[,;.\n]|—|-|\(|$))"
    )

    seen_entries = {"Manas Gupta"}
    for line in info.splitlines():
        line_s = line.strip()
        if not line_s:
            continue

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
                # Check if there is an explicit role after an em-dash right after the name
                after_text = chunk[match.end(): match.end() + 60]
                dash_role = re.match(r"^\s*[—\-]\s*([^.;,\n]+)", after_text)
                specific_role = f"{dash_role.group(1).strip()} ({role_label})" if dash_role else role_label

                if person_name not in seen_entries:
                    seen_entries.add(person_name)
                    people_directory.append((person_name, specific_role))

    # 2. Extract Student Council / Cabinet names from lines with "—" or ":" in Student Council section
    for heading, body, _ in extract_sections(info):
        if any(k in heading.lower() for k in ("council", "cabinet", "house")):
            for line in body.splitlines():
                # Match patterns like "Head Boy: Name" or "Name — Role"
                for m in re.finditer(r"([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)\s*[—\-:]\s*([^.,;\n]+)", line):
                    p_name = m.group(1).strip()
                    p_role = m.group(2).strip()
                    if p_name not in seen_entries and len(p_name.split()) <= 4:
                        seen_entries.add(p_name)
                        people_directory.append((p_name, f"{p_role} (Student Council)"))

    # Match user tokens against each person in the directory
    # Rule: EVERY query token must match a word in the person's name!
    matched_results = []
    for person_name, role_desc in people_directory:
        name_words = [
            normalize_word(w)
            for w in re.findall(r"[a-zA-Z]+", person_name)
            if w.lower() not in {"mrs", "mr", "ms", "sr", "fr", "dr"} and len(w) >= 2
        ]
        if not name_words:
            continue

        all_tokens_matched = True
        for nt in norm_tokens:
            if not any(
                nt == nw or (len(nt) >= 4 and len(nw) >= 4 and (nt in nw or nw in nt))
                for nw in name_words
            ):
                all_tokens_matched = False
                break

        if all_tokens_matched:
            matched_results.append((len(norm_tokens), person_name, role_desc))

    if not matched_results:
        return []

    return [
        f"**{name}** — {role_desc} at St. Anthony's Sr. Sec. School, Barabanki."
        for _, name, role_desc in matched_results
    ]


def local_school_info_answer(query: str, info: str) -> str:
    """Comprehensive, natural fallback answer engine over school_info.txt."""
    q = query.lower().strip()
    sections = extract_sections(info)

    # 1. Greetings
    if q in ("hi", "hello", "hey", "hii", "hiii", "good morning", "good afternoon", "good evening"):
        return (
            "Hello! Welcome to **St. Anthony's Sr. Sec. School, Barabanki**.\n\n"
            "How can I assist you today? Feel free to ask about our **Principal & Principal's Message**, "
            "**School Timings**, **Admissions**, **School Uniform**, **Student Council**, **Faculty & Staff**, or **School Rules**!"
        )

    # 2. Questions about Manas / Manas Gupta / Developer of the Chatbot
    if "manas" in q or ("who" in q and any(w in q for w in ("made", "created", "developed", "built", "developer", "creator"))):
        return (
            "**Manas Gupta** is a **Class 12 PCM student** at St. Anthony's Sr. Sec. School, Barabanki "
            "(and served as the **Yellow House Prefect** in the 2024–25 Student Cabinet). "
            "He independently designed and developed this official **St. Anthony's Sr. Sec. School AI Chatbot**!"
        )

    # 3. Principal & Principal's Message
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

    # 4. Specific Person Lookup (Teachers, Staff, Admin, Student Council)
    if not any(k in q for k in ("timing", "uniform", "fee", "admission", "stream", "syllabus", "history", "facility", "facilities", "rule", "exam", "calendar", "contact")):
        people_matches = find_people_in_records(query, info)
        if people_matches:
            if len(people_matches) == 1:
                return f"Based on our official school records:\n\n{people_matches[0]}"
            else:
                return (
                    "Based on our official school records, here are the matching members:\n\n"
                    + "\n".join(f"- {m}" for m in people_matches)
                )

    # 5. School Timings
    if any(k in q for k in ("timing", "time", "hours", "schedule", "summer", "winter", "recess")):
        for heading, body, _ in sections:
            if "timing" in heading.lower() or "schedule" in heading.lower():
                return f"### {heading}\n\n{body}"

    # 6. School Uniform
    if any(k in q for k in ("uniform", "dress", "blazer", "shirt", "tie", "skirt", "trouser")):
        for heading, body, _ in sections:
            if "uniform" in heading.lower():
                return f"### {heading}\n\n{body}"

    # 7. Student Council & Houses
    if any(k in q for k in ("council", "head boy", "head girl", "captain", "prefect", "house", "cabinet")):
        for heading, body, _ in sections:
            if "council" in heading.lower() or "house" in heading.lower() or "cabinet" in heading.lower():
                return f"### {heading}\n\n{body}"

    # 8. Admissions & Withdrawals
    if any(k in q for k in ("admission", "withdraw", "tc", "transfer certificate", "age criteria", "document", "registration")):
        for heading, body, _ in sections:
            if "admission" in heading.lower():
                return f"### {heading}\n\n{body}"

    # 9. Fee Structure
    if any(k in q for k in ("fee", "payment", "installment", "tuition")):
        for heading, body, _ in sections:
            if "fee" in heading.lower():
                return f"### {heading}\n\n{body}"

    # 10. Curriculum & Streams
    if any(k in q for k in ("stream", "subject", "curriculum", "syllabus", "science", "commerce", "ncert", "cbse")):
        for heading, body, _ in sections:
            if "curriculum" in heading.lower() or "stream" in heading.lower():
                return f"### {heading}\n\n{body}"

    # 11. Examinations & Promotion
    if any(k in q for k in ("exam", "promotion", "grading", "attendance", "pass")):
        for heading, body, _ in sections:
            if "examination" in heading.lower() or "promotion" in heading.lower():
                return f"### {heading}\n\n{body}"

    # 12. Rules & Code of Conduct
    if any(k in q for k in ("rule", "discipline", "conduct", "mobile", "phone", "late", "punish")):
        for heading, body, _ in sections:
            if "conduct" in heading.lower() or "rule" in heading.lower() or "discipline" in heading.lower():
                return f"### {heading}\n\n{body}"

    # 13. Facilities & Infrastructure
    if any(k in q for k in ("facility", "facilities", "infrastructure", "lab", "library", "transport", "bus", "playground", "cctv")):
        for heading, body, _ in sections:
            if "infrastructure" in heading.lower() or "facilities" in heading.lower():
                return f"### {heading}\n\n{body}"

    # 14. Managing Committee
    if "managing committee" in q or "committee" in q or "minority" in q:
        for heading, body, _ in sections:
            if "managing" in heading.lower():
                return f"### {heading}\n\n{body}"

    # 15. History & About
    if any(k in q for k in ("history", "founded", "patron", "antony", "diocese", "bishop", "about", "mission", "motto")):
        for heading, body, _ in sections:
            if any(w in heading.lower() for w in ("mission", "history", "about")):
                return f"### {heading}\n\n{body}"

    # 16. Contact Info
    if any(k in q for k in ("contact", "phone", "email", "address", "location", "website", "where")):
        for heading, body, _ in sections:
            if "contact" in heading.lower() or "st. anthony" in heading.lower():
                return f"### {heading}\n\n{body}"

    # 17. Full Staff / Faculty list if user asks generally about teachers/staff
    if any(k in q for k in ("staff", "teacher", "teachers", "faculty")):
        for heading, body, _ in sections:
            if "staff" in heading.lower() or "faculty" in heading.lower() or "administration" in heading.lower():
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

    # Use clean, standard Gemini payload (no experimental thinkingConfig that causes 400 errors on gemini-3.5-flash)
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

    headers = {
        "Content-Type": "application/json",
        "X-goog-api-key": API_KEY or "",
    }

    if API_KEY:
        for model_name in ("gemini-3.5-flash", "gemini-3.8-flash", "gemini-flash-latest"):
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={API_KEY}"
            try:
                response = requests.post(url, headers=headers, data=json.dumps(payload), timeout=18)
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

    # Instant, accurate fallback from school_info.txt if Google's API is busy
    fallback_reply = local_school_info_answer(latest_user_text, school_info)
    return jsonify({"reply": fallback_reply}), 200


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
