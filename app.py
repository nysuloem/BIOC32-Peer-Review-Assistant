import streamlit as st
import openai
import os
import csv
import time
import base64
from datetime import datetime
from docx import Document
from docx.document import Document as DocumentType
from docx.oxml.table import CT_Tbl
from docx.oxml.text.paragraph import CT_P
from docx.table import _Cell, Table
from docx.text.paragraph import Paragraph
from PIL import Image
import io
from dotenv import load_dotenv

# Load environment variables
load_dotenv()
openai.api_key = os.getenv("OPENAI_API_KEY")

def extract_images_from_docx(doc):
    """Extract all images from a Word document"""
    images = []
    
    # Get all relationships in the document
    for rel in doc.part.rels.values():
        if "image" in rel.target_ref:
            try:
                # Get the image data
                image_data = rel.target_part.blob
                # Convert to PIL Image
                image = Image.open(io.BytesIO(image_data))
                images.append(image)
            except Exception as e:
                st.warning(f"Could not extract an image: {e}")
                continue
    
    return images

def encode_image_for_api(image):
    """Convert PIL Image to base64 string for API"""
    buffer = io.BytesIO()
    # Convert to RGB if necessary (for compatibility)
    if image.mode in ("RGBA", "P"):
        image = image.convert("RGB")
    image.save(buffer, format="JPEG")
    img_str = base64.b64encode(buffer.getvalue()).decode()
    return img_str

def analyze_images_with_gpt4_vision(images, module):
    """Analyze images using GPT-4 Vision"""
    if not images:
        return "No figures found in the document."
    
    # Load image analysis prompt from file
    image_prompt_file_path = f"prompts/image_rubric_{module.split(' ')[0]}.txt"
    try:
        with open(image_prompt_file_path, 'r', encoding='utf-8') as f:
            prompt = f.read()
    except FileNotFoundError:
        # Fall back to a default prompt if specific module prompt doesn't exist
        try:
            with open("prompts/image_rubric_default.txt", 'r', encoding='utf-8') as f:
                prompt = f.read()
        except FileNotFoundError:
            prompt = "Analyze these figures and provide feedback on clarity, appropriateness, and professional presentation standards."
    
    # Prepare messages for API call
    messages = [
        {
            "role": "system",
            "content": f"You are an expert peer reviewer evaluating scientific figures. {prompt}"
        }
    ]
    
    # Add each image to the message
    for i, image in enumerate(images):
        base64_image = encode_image_for_api(image)
        messages.append({
            "role": "user",
            "content": [
                {
                    "type": "text",
                    "text": f"Figure {i+1}:"
                },
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/jpeg;base64,{base64_image}",
                        "detail": "high"
                    }
                }
            ]
        })
    
    try:
        response = openai.chat.completions.create(
            model="gpt-4o",  # Use gpt-4o for vision capabilities
            messages=messages,
            max_tokens=1500
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"Error analyzing images: {e}"

st.title("AI Peer Reviewer for BIOC32")
st.markdown("This AI Peer Reviewer will provide feedback to help you improve your submission before it is evaluated by the teaching assistants. It will not provide a grade for your submission.")
st.markdown("**Note:** Each group may only submit their work **once per module**. Multiple submissions are not permitted.")

# Dropdown for module selection
module = st.selectbox("Select Module", [
    "2 - Research Questions",
    "3 - Study Design",
    "4 - Human Research Ethics",
    "5 - Presenting Results",
    "6 - Discussion Section"
])

# Show ethics-specific prompt when module 4 is selected
if module == "4 - Human Research Ethics":
    st.info("Please make sure you have included the full experimental design at the start of the document so the AI Peer Review Assistant can properly evaluate your ethics review.")

# Show figure-specific prompt for results module
if module == "5 - Presenting Results":
    st.info("📊 This module includes analysis of figures and graphs. Make sure your figures are embedded in the Word document with proper labels (e.g., 'Figure 1'), descriptive captions, axis labels, and appropriate formatting.")

# Always analyze figures when present
analyze_figures = True

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

        # Extract and analyze images if requested
        image_feedback = ""
        if analyze_figures:
            with st.spinner("Extracting and analyzing figures..."):
                try:
                    images = extract_images_from_docx(doc)
                    if images:
                        st.success(f"Found {len(images)} figure(s) in the document.")
                        image_feedback = analyze_images_with_gpt4_vision(images, module)
                    else:
                        image_feedback = "No figures were found in the document. If you have figures, make sure they are properly embedded in the Word document."
                except Exception as e:
                    st.warning(f"Could not analyze figures: {e}")
                    image_feedback = "Figure analysis was not available for this submission."

        # Load rubric prompt
        rubric_file_path = f"prompts/rubric_{module.split(' ')[0]}.txt"
        try:
            with open(rubric_file_path, 'r', encoding='utf-8') as f:
                rubric_prompt = f.read()
        except FileNotFoundError:
            st.error("Rubric prompt file not found. Please check the prompts directory.")
            st.stop()

        # Call OpenAI API for text analysis
        try:
            with st.spinner("Analyzing text content..."):
                response = openai.chat.completions.create(
                    model="gpt-4-turbo",
                    messages=[
                        {"role": "system", "content": rubric_prompt},
                        {"role": "user", "content": full_text}
                    ]
                )
                text_feedback = response.choices[0].message.content
        except Exception as e:
            st.error(f"OpenAI API error: {e}")
            st.stop()

        # Log the submission
        with open(SUBMISSION_LOG, mode='a', newline='') as file:
            writer = csv.DictWriter(file, fieldnames=["timestamp", "module", "groupnumber", "included_figures"])
            if file.tell() == 0:
                writer.writeheader()
            writer.writerow({
                "timestamp": datetime.now().isoformat(), 
                "module": module, 
                "groupnumber": group_number,
                "included_figures": analyze_figures
            })

        # Display the feedback
        st.subheader("Peer Review Feedback")
        
        # Text feedback
        st.markdown("### 📝 Content Analysis")
        st.write(text_feedback)
        
        # Figure feedback if available
        if analyze_figures and image_feedback:
            st.markdown("### 📊 Figure Analysis")
            st.write(image_feedback)
            
else:
    st.info("Please fill out all fields and upload a .docx file to receive feedback.")
