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

# Configuration
SUBMISSION_LOG = "submission_log.csv"
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin123")  # Change this in your .env file

def load_submissions():
    """Load submission data from CSV file"""
    submissions = []
    if os.path.exists(SUBMISSION_LOG):
        try:
            with open(SUBMISSION_LOG, mode='r', newline='', encoding='utf-8') as file:
                reader = csv.DictReader(file)
                for row in reader:
                    submissions.append(row)
        except Exception as e:
            st.error(f"Error loading submissions: {e}")
    return submissions

def save_submissions(submissions):
    """Save submission data to CSV file"""
    try:
        with open(SUBMISSION_LOG, mode='w', newline='', encoding='utf-8') as file:
            if submissions:
                fieldnames = ["timestamp", "module", "groupnumber", "included_figures"]
                writer = csv.DictWriter(file, fieldnames=fieldnames)
                writer.writeheader()
                for submission in submissions:
                    writer.writerow(submission)
            else:
                # Create empty file with headers
                fieldnames = ["timestamp", "module", "groupnumber", "included_figures"]
                writer = csv.DictWriter(file, fieldnames=fieldnames)
                writer.writeheader()
        return True
    except Exception as e:
        st.error(f"Error saving submissions: {e}")
        return False

def has_group_submitted(group_number, module):
    """Check if a group has already submitted for a specific module"""
    submissions = load_submissions()
    
    for submission in submissions:
        if (submission.get('groupnumber', '') == str(group_number) and 
            submission.get('module', '') == module):
            return True
    
    return False

def log_submission(module, group_number, included_figures):
    """Log a new submission to the CSV file"""
    submissions = load_submissions()
    
    new_submission = {
        "timestamp": datetime.now().isoformat(),
        "module": module,
        "groupnumber": str(group_number),
        "included_figures": str(included_figures)
    }
    
    submissions.append(new_submission)
    return save_submissions(submissions)

def get_submission_stats(submissions):
    """Calculate submission statistics"""
    if not submissions:
        return {"total": 0, "unique_groups": 0, "modules_with_submissions": 0}
    
    unique_groups = set()
    unique_modules = set()
    
    for submission in submissions:
        unique_groups.add(submission.get('groupnumber', ''))
        unique_modules.add(submission.get('module', ''))
    
    return {
        "total": len(submissions),
        "unique_groups": len(unique_groups),
        "modules_with_submissions": len(unique_modules)
    }

def get_submissions_by_module(submissions):
    """Group submissions by module"""
    modules = {}
    for submission in submissions:
        module = submission.get('module', '')
        if module not in modules:
            modules[module] = []
        modules[module].append(submission)
    return modules

def format_timestamp(timestamp_str):
    """Format timestamp for display"""
    try:
        dt = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
        return dt.strftime('%Y-%m-%d %H:%M:%S')
    except:
        return timestamp_str

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

def admin_panel():
    """Admin interface for managing submissions"""
    st.header("🔧 Admin Panel")
    
    # Password protection
    if 'admin_authenticated' not in st.session_state:
        st.session_state.admin_authenticated = False
    
    if not st.session_state.admin_authenticated:
        password = st.text_input("Enter admin password:", type="password")
        if st.button("Login"):
            if password == ADMIN_PASSWORD:
                st.session_state.admin_authenticated = True
                st.success("Admin access granted!")
                st.rerun()
            else:
                st.error("Invalid password!")
        return
    
    # Load current submissions
    submissions = load_submissions()
    
    if not submissions:
        st.info("No submissions found.")
        if st.button("🚪 Logout", type="secondary"):
            st.session_state.admin_authenticated = False
            st.rerun()
        return
    
    # Display submission statistics
    st.subheader("📊 Submission Statistics")
    stats = get_submission_stats(submissions)
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.metric("Total Submissions", stats["total"])
    
    with col2:
        st.metric("Unique Groups", stats["unique_groups"])
    
    with col3:
        st.metric("Modules with Submissions", stats["modules_with_submissions"])
    
    # Display submissions by module
    st.subheader("📋 Submissions by Module")
    modules_data = get_submissions_by_module(submissions)
    
    for module in sorted(modules_data.keys()):
        module_submissions = modules_data[module]
        with st.expander(f"{module} ({len(module_submissions)} submissions)"):
            for i, submission in enumerate(module_submissions):
                col1, col2, col3 = st.columns([2, 2, 2])
                with col1:
                    st.write(f"**Group:** {submission.get('groupnumber', 'N/A')}")
                with col2:
                    st.write(f"**Time:** {format_timestamp(submission.get('timestamp', ''))}")
                with col3:
                    st.write(f"**Figures:** {submission.get('included_figures', 'N/A')}")
                if i < len(module_submissions) - 1:
                    st.divider()
    
    # Management options
    st.subheader("🛠️ Management Options")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.write("**Remove specific submission:**")
        if submissions:
            # Create selection options
            selection_options = []
            for i, submission in enumerate(submissions):
                display_text = f"Group {submission.get('groupnumber', 'N/A')} - {submission.get('module', 'N/A')} ({format_timestamp(submission.get('timestamp', ''))})"
                selection_options.append((i, display_text))
            
            selected_index = st.selectbox(
                "Select submission to remove:",
                options=[opt[0] for opt in selection_options],
                format_func=lambda x: next(opt[1] for opt in selection_options if opt[0] == x)
            )
            
            if st.button("🗑️ Remove Selected Submission", type="secondary"):
                if 'confirm_single_removal' not in st.session_state:
                    st.session_state.confirm_single_removal = False
                
                if not st.session_state.confirm_single_removal:
                    st.session_state.confirm_single_removal = True
                    st.warning("Click again to confirm removal.")
                    st.rerun()
                else:
                    # Remove the selected submission
                    updated_submissions = [sub for i, sub in enumerate(submissions) if i != selected_index]
                    if save_submissions(updated_submissions):
                        st.success("Submission removed successfully!")
                        st.session_state.confirm_single_removal = False
                        st.rerun()
    
    with col2:
        st.write("**Reset specific group/module:**")
        reset_group = st.text_input("Group number to reset:")
        reset_module = st.selectbox("Module to reset:", [
            "All modules",
            "2 - Research Questions",
            "3 - Study Design", 
            "4 - Human Research Ethics",
            "5 - Presenting Results",
            "6 - Discussion Section"
        ])
        
        if st.button("🔄 Reset Group Submissions", type="secondary"):
            if not reset_group:
                st.warning("Please enter a group number.")
            else:
                if 'confirm_group_reset' not in st.session_state:
                    st.session_state.confirm_group_reset = False
                
                if not st.session_state.confirm_group_reset:
                    st.session_state.confirm_group_reset = True
                    if reset_module == "All modules":
                        st.warning(f"Click again to confirm removal of ALL submissions for Group {reset_group}.")
                    else:
                        st.warning(f"Click again to confirm removal of Group {reset_group}'s submission for {reset_module}.")
                    st.rerun()
                else:
                    # Filter submissions
                    if reset_module == "All modules":
                        updated_submissions = [sub for sub in submissions if sub.get('groupnumber', '') != reset_group]
                        success_msg = f"All submissions for Group {reset_group} removed!"
                    else:
                        updated_submissions = [sub for sub in submissions 
                                             if not (sub.get('groupnumber', '') == reset_group and 
                                                   sub.get('module', '') == reset_module)]
                        success_msg = f"Group {reset_group}'s submission for {reset_module} removed!"
                    
                    if save_submissions(updated_submissions):
                        st.success(success_msg)
                        st.session_state.confirm_group_reset = False
                        st.rerun()
    
    # Danger zone
    st.subheader("⚠️ Danger Zone")
    with st.expander("Reset All Submissions", expanded=False):
        st.warning("This will delete ALL submission records. This action cannot be undone!")
        
        confirm_text = st.text_input("Type 'RESET ALL' to confirm:")
        if st.button("🚨 RESET ALL SUBMISSIONS", type="primary"):
            if confirm_text == "RESET ALL":
                if save_submissions([]):
                    st.success("All submissions have been reset!")
                    st.rerun()
            else:
                st.error("Please type 'RESET ALL' to confirm.")
    
    # Export data
    st.subheader("📥 Export Data")
    if submissions:
        # Create CSV string
        output = io.StringIO()
        fieldnames = ["timestamp", "module", "groupnumber", "included_figures"]
        writer = csv.DictWriter(output, fieldnames=fieldnames)
        writer.writeheader()
        for submission in submissions:
            writer.writerow(submission)
        csv_data = output.getvalue()
        
        st.download_button(
            label="📥 Download Submission Data (CSV)",
            data=csv_data,
            file_name=f"submissions_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
            mime="text/csv"
        )
    
    # Logout button
    if st.button("🚪 Logout", type="secondary"):
        st.session_state.admin_authenticated = False
        st.rerun()

def main_app():
    """Main application interface"""
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

    # Show question-specific prompt when module 3 is selected
    if module == "3 - Study Design":
        st.info("Please make sure you have included your full introduction at the start of the document so the AI Peer Review Assistant can properly assess whether your experimental design is appropriate to answer your research question.")

    # Show ethics-specific prompt when module 4 is selected
    if module == "4 - Human Research Ethics":
        st.info("Please make sure you have included the full experimental design at the start of the document so the AI Peer Review Assistant can properly evaluate your ethics review.")

    # Show figure-specific prompt for results module
    if module == "5 - Presenting Results":
        st.info("📊 This module includes analysis of figures and graphs. Make sure your figures are embedded in the Word document with proper labels (e.g., 'Figure 1'), descriptive captions, axis labels, and appropriate formatting.")

    # Show Module 5 results prompt for discussion section
    if module == "6 - Discussion Section":
        st.info("📋 Please make sure you have included the text section of your Module 5 results at the bottom of your document with the heading 'Module 5' so the AI can properly evaluate how well your discussion connects to your results.")

    # Only analyze figures for Module 5
    analyze_figures = (module == "5 - Presenting Results")

    # Group number input
    group_number = st.text_input("Enter Group Number (numbers only)")

    # File upload
    uploaded_file = st.file_uploader("Upload your .docx file (Word only). If you used Google Docs, download it as a Word file first and upload it here.", type="docx")

    # Check for duplicate submission
    submission_blocked = False
    if group_number and module:
        if has_group_submitted(group_number, module):
            st.error(f"❌ Group {group_number} has already submitted for {module}. Only one submission per module is allowed.")
            st.info("If you need to resubmit due to an error, please contact your instructor.")
            submission_blocked = True

    # Main submission logic
    if uploaded_file and group_number and module and not submission_blocked:
        # Read content from .docx
        try:
            doc = Document(uploaded_file)
            full_text = "\n".join([para.text for para in doc.paragraphs])
        except Exception as e:
            st.error(f"Could not read file: {e}")
            st.stop()

        # Extract and analyze images if requested (only for Module 5)
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
        if log_submission(module, group_number, analyze_figures):
            st.success("✅ Submission logged successfully!")
        else:
            st.warning("⚠️ Submission processed but logging failed. Please contact your instructor.")

        # Display the feedback
        st.subheader("Peer Review Feedback")
        
        # Text feedback
        st.markdown("### 📝 Content Analysis")
        st.write(text_feedback)
        
        # Figure feedback if available (only for Module 5)
        if analyze_figures and image_feedback:
            st.markdown("### 📊 Figure Analysis")
            st.write(image_feedback)
            
    elif not submission_blocked:
        st.info("Please fill out all fields and upload a .docx file to receive feedback.")

# Main app logic
def main():
    # Sidebar navigation
    st.sidebar.title("Navigation")
    page = st.sidebar.selectbox("Choose a page:", ["Student Submission", "Admin Panel"])
    
    if page == "Student Submission":
        main_app()
    elif page == "Admin Panel":
        admin_panel()

if __name__ == "__main__":
    main()
