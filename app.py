import streamlit as st
import openai
import os
import csv
import time
from datetime import datetime
from docx import Document
from dotenv import load_dotenv

# Load environment variables
load_dotenv()
openai.api_key = os.getenv("OPENAI_API_KEY")

st.title("AI Peer Review Assistant for BIOC32")
st.markdown("This peer review assistant will provide feedback to help you improve your submission before it is evaluated by the teaching assistants. It will not provide a grade for your submission.")
st.markdown("**Note:** Each group may only submit their work **once per module**. Multiple submissions are not permitted.")

# Dropdown for module selection
module = st.selectbox("Select Module", [
    "2 - Research Questions",
    "3 - Study Design",
    "4 - Human Research Ethics",
    "5 - Presenting Results",
    "6 - Discussion Section"
])

# Group number input
group_number = st.text_input("Enter Group Number (numbers only)")

# File upload
uploaded_file = st.file_uploader("Upload your .docx file (Word only). If you used Google Docs, download it as a Word file first and upload it here.", type="docx")

# Load previous submissions to prevent duplicates
SUBMISSION_LOG = "submission_log.csv"
submitted_groups = set()
if os.path.exists(SUBMISSION_LOG):
    with open(SUBMISSION_LOG, mode='r', newline='') as file:
        reader = csv.DictReader(file)
        for row in reader:
            submitted_groups.add((row["module"], row["groupnumber"]))

# Main submission logic
if uploaded_file and group_number and module:
    if (module, group_number) in submitted_groups:
        st.error("This group has already submitted for this module. Only one submission per module is allowed.")
    else:
        # Read content from .docx
        try:
            doc = Document(uploaded_file)
            full_text = "\n".join([para.text for para in doc.paragraphs])
        except Exception as e:
            st.error(f"Could not read file: {e}")
            st.stop()

        # Load rubric prompt
        rubric_file_path = f"prompts/rubric_{module.split(' ')[0]}.txt"
        try:
            with open(rubric_file_path, 'r', encoding='utf-8') as f:
                rubric_prompt = f.read()
        except FileNotFoundError:
            st.error("Rubric prompt file not found. Please check the prompts directory.")
            st.stop()

        # Call OpenAI API
        try:
            response = openai.chat.completions.create(
                model="gpt-4-turbo",
                messages=[
                    {"role": "system", "content": rubric_prompt},
                    {"role": "user", "content": full_text}
                ]
            )
            feedback = response.choices[0].message.content
        except Exception as e:
            st.error(f"OpenAI API error: {e}")
            st.stop()

        # Log the submission
        with open(SUBMISSION_LOG, mode='a', newline='') as file:
            writer = csv.DictWriter(file, fieldnames=["timestamp", "module", "groupnumber"])
            if file.tell() == 0:
                writer.writeheader()
            writer.writerow({"timestamp": datetime.now().isoformat(), "module": module, "groupnumber": group_number})

        # Display the feedback
        st.subheader("Peer Review Feedback")
        st.write(feedback)
else:
    st.info("Please fill out all fields and upload a .docx file to receive feedback.")
