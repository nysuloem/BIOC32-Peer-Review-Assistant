import openai
import os
import sys
from dotenv import load_dotenv

# Load API key from .env
load_dotenv()
openai.api_key = os.getenv("OPENAI_API_KEY")

# === Step 1: Parse command-line arguments ===
if len(sys.argv) != 3:
    print("Usage: python grade_section.py <section_number 1-5> <student_submission_file.txt>")
    sys.exit(1)

section_num = sys.argv[1]
student_file = sys.argv[2]

section_labels = ["intro", "design", "ethics", "results", "discussion"]

try:
    section_name = section_labels[int(section_num) - 1]
except (IndexError, ValueError):
    print("Error: Section number must be 1–5.")
    sys.exit(1)

# === Step 2: Load rubric ===
rubric_path = f"prompts/rubric_{section_num}_{section_name}.txt"

try:
    with open(rubric_path, 'r', encoding='utf-8') as rfile:
        rubric = rfile.read()
except FileNotFoundError:
    print(f"Error: Rubric file not found: {rubric_path}")
    sys.exit(1)

# === Step 3: Load student submission ===
try:
    with open(student_file, 'r', encoding='utf-8') as sfile:
        submission = sfile.read()
except FileNotFoundError:
    print(f"Error: Could not find submission file: {student_file}")
    sys.exit(1)

# === Step 4: Create prompt ===
prompt = f"""
You are a peer reviewer for a university assignment. Provide detailed, constructive feedback based on the rubric below. DO NOT assign a grade.

Rubric:
{rubric}

Student Submission:
{submission}

Respond with strengths and specific suggestions for improvement.
"""

# === Step 5: Call OpenAI API ===
response = openai.ChatCompletion.create(
    model="gpt-4",
    messages=[{"role": "user", "content": prompt}],
    temperature=0.4,
    max_tokens=1000
)

# === Step 6: Display feedback ===
print("\n📝 === FEEDBACK ===\n")
print(response['choices'][0]['message']['content'])
