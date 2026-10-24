import streamlit as st
import requests
import json
import base64
import os  # <-- Required for secure cloud deployment

try:
    # 1. Read the school information
    with open("school_info.txt", "r", encoding="utf-8") as f:
        system_context = f.read()

    # 2. Secure API Key Handling!
    # Python looks into the server's hidden vault for the label "GEMINI_API_KEY"
    API_KEY = os.environ.get("GEMINI_API_KEY")
    
    # Safety check: Stop the app if the key isn't found in the environment
    if not API_KEY:
        st.error("API Key not found! If running locally, set your GEMINI_API_KEY environment variable. If deploying, add it to your server's secret settings.")
        st.stop()
    
    # --- Custom Image Background ---
    # Convert the local image to a format Streamlit can use
    def get_base64_of_bin_file(bin_file):
        with open(bin_file, 'rb') as f:
            data = f.read()
        return base64.b64encode(data).decode()

    # Read the uploaded image file
    img_base64 = get_base64_of_bin_file('school_bg.png')
    
    # Apply the image as a full-screen background
    st.markdown(
        f"""
        <style>
        .stApp {{
            background-image: url("data:image/png;base64,{img_base64}");
            background-size: cover;
            background-position: center;
            background-repeat: no-repeat;
            background-attachment: fixed;
        }}
        </style>
        """,
        unsafe_allow_html=True
    )
    
    # 3. Set up the Streamlit app
    st.title("St. Anthony's High School Chatbot")

    # 4. Initialize chat history with your custom credit
    if "messages" not in st.session_state:
        welcome_msg = (
            "Hello! How can I help you today?\n\n"
            "**I am the official St. Anthony's Sr. Sec. School Chatbot, proudly developed by Manas Gupta, a Class 12 PCM student.**\n\n"
            "If you have any questions about the school—such as its admissions, timings, staff, student council, school rules, or history—feel free to ask!"
        )
        st.session_state.messages = [{"role": "assistant", "content": welcome_msg}]

    # 5. Display chat messages from history on app rerun
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    # 6. React to user input
    if prompt := st.chat_input("What is up?"):
        
        # Display user message
        st.chat_message("user").markdown(prompt)
        st.session_state.messages.append({"role": "user", "content": prompt})

        # 7. Connect directly to Google's API
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-3.5-flash:generateContent?key={API_KEY}"
        
        # Format the chat history correctly for the AI
        contents = []
        for msg in st.session_state.messages:
            role = "user" if msg["role"] == "user" else "model"
            contents.append({"role": role, "parts": [{"text": msg["content"]}]})

        payload = {
            "systemInstruction": {
                "parts": [{"text": system_context}]
            },
            "contents": contents
        }
        
        # 8. Send request and get response
        headers = {"Content-Type": "application/json"}
        response = requests.post(url, headers=headers, data=json.dumps(payload))
        data = response.json()
        
        # 9. Show the AI's reply
        if "candidates" in data:
            reply = data["candidates"][0]["content"]["parts"][0]["text"]
            with st.chat_message("assistant"):
                st.markdown(reply)
            st.session_state.messages.append({"role": "assistant", "content": reply})
        else:
            st.error(f"API Error: {data}")

except FileNotFoundError:
    st.error("Missing file: Please ensure 'school_info.txt' and 'school_bg.png' are uploaded to your project folder.")
except Exception as e:
    st.error(f"An error occurred: {e}")
