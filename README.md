Markdown
# 🏫 St. Anthony's AI Chatbot

A custom-built, AI-powered interactive assistant designed specifically for St. Anthony's Sr. Sec. School. This project leverages Google's Gemini AI to instantly answer queries regarding school admissions, timings, faculty, student council rules, and history.

Proudly developed independently for the school exhibition by **Manas (Class 12 PCM)**.

## ✨ Features
* **Custom Knowledge Base:** Grounded in specific school data to provide accurate, localized answers.
* **Direct AI Integration:** Connects securely to Google's `gemini-1.5-flash` model via REST API.
* **Immersive UI:** Custom full-screen background integration natively built into Streamlit.
* **Cloud-Ready Security:** API keys are protected using environment variables, making it safe for public GitHub hosting and cloud deployment.
* **Cross-Platform:** Can be run locally on Windows/Mac or instantly deployed via cloud workstations (like NixOS).

## 🛠️ Tech Stack
* **Language:** Python 3
* **Frontend/Framework:** Streamlit
* **AI Engine:** Google Gemini API
* **Network Routing:** Python `requests` & `json`

## 📂 Project Structure
```text
school-ai-chatbot/
│
├── app.py                 # The main Streamlit Python application
├── school_info.txt        # The custom AI training data/system instructions
├── school_bg.png          # The custom background image for the UI
├── requirements.txt       # The list of Python dependencies
└── README.md              # Project documentation
🚀 How to Run Locally
1. Prerequisites
Make sure you have Python installed on your computer.
Clone this repository to your local machine:

Bash
git clone [https://github.com/yourusername/school-ai-chatbot.git](https://github.com/yourusername/school-ai-chatbot.git)
cd school-ai-chatbot
2. Install Dependencies
Install the required Python libraries using pip:

Bash
pip install -r requirements.txt
3. Set up the AI Brain (API Key)
You need a free Google Gemini API key to run this project. For security, the app looks for an environment variable.

On Windows (Command Prompt):

DOS
set GEMINI_API_KEY=your_actual_api_key_here
On Mac/Linux/Cloud Terminal:

Bash
export GEMINI_API_KEY="your_actual_api_key_here"
4. Launch the App
Start the Streamlit server:

Bash
streamlit run app.py
(Note for Cloud Workstations like NixOS: Use streamlit run app.py --server.enableCORS=false --server.enableXsrfProtection=false to bypass strict proxy security).

🛡️ Security Note
Never upload your actual API key to GitHub. This project is specifically configured to use os.environ.get("GEMINI_API_KEY") so that your private keys stay hidden inside your local computer or your cloud host's secret manager.

Built for the future. Built for St. Anthony's.


***

### 🚀 What to do next:
1. Open Notepad or VS Code.
2. Paste all of the code above (the stuff inside the gray box).
3. Change the `yourusername` part in the GitHub link (under Prerequisites) to your actual GitHub username.
4. Save the file as **`README.md`**.
5. Drag and drop this single new file into your GitHub upload box just like you did with the others!
