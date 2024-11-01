from flask import Flask, render_template, request
import PyPDF2
import os
import base64
import re
import logging
from openai import AzureOpenAI
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size
app.config['UPLOAD_FOLDER'] = 'uploads'

# Ensure upload folder exists
if not os.path.exists(app.config['UPLOAD_FOLDER']):
    os.makedirs(app.config['UPLOAD_FOLDER'])

# Initialize Azure OpenAI client
client = AzureOpenAI(
  azure_endpoint = "https://hkust.azure-api.net",
  api_version = "2023-05-15",
  api_key = "a743ecc47399464199738f91c45113d7" #put your api key here
)

def get_completion(prompt, instruction):
    """Get completion from Azure OpenAI."""
    try:
        response = client.chat.completions.create(
            model='gpt-35-turbo',
            temperature=1,
            messages=[
                {"role": "system", "content": instruction},
                {"role": "user", "content": prompt}
            ]
        )
        return response.choices[0].message.content
    except Exception as e:
        logger.error(f"Azure OpenAI API error: {str(e)}")
        raise Exception("Failed to get AI response")

def preprocess_text(text):
    """Clean and preprocess extracted text."""
    # Remove extra whitespace
    text = ' '.join(text.split())
    # Remove special characters while keeping essential ones
    text = re.sub(r'[^\w\s.,@()-]', '', text)
    # Add sentence separation for better parsing
    text = text.replace('.', '.\n')
    # Normalize spaces
    text = re.sub(r'\s+', ' ', text)
    return text.strip()

def extract_text_from_pdf(pdf_file):
    """Extract and preprocess text from PDF file."""
    try:
        reader = PyPDF2.PdfReader(pdf_file)
        text = ""
        for page in reader.pages:
            text += page.extract_text()
        return preprocess_text(text)
    except Exception as e:
        logger.error(f"PDF extraction error: {str(e)}")
        raise Exception("Failed to extract text from PDF")

def get_section_description(text, section):
    """Get structured information for each CV section."""
    instructions = {
        'education': "You are an AI assistant specialized in analyzing educational qualifications from CVs. Summarize in 2 sentences. Plane text in single paragraph, no formatting.",
        'experience': "You are an AI assistant specialized in analyzing work experience from CVs. Focus on roles, responsibilities, and achievements. Summarize in 2 sentences. Plane text in single paragraph, no formatting. Just list the companies and positions using , sign.",
        'skills': "You are an AI assistant specialized in analyzing technical and soft skills from CVs. Provide a comprehensive, categorized list. Summarize in 2 sentences. Plane text in single paragraph, no formatting. Just list the skills using , sign.",
        'contact': "You are an AI assistant specialized in extracting contact and personal information from CVs. Ensure all relevant details are included. Summarize in 2 sentences. Plane text in single paragraph, no formatting."
    }
    
    prompts = {
        'education': f"Analyze the following CV text and describe the individual's educational qualifications. Plane text in single paragraph, no formatting. CV Text: {text}",
        'experience': f"Extract and structure all work experience from this CV.  Just list the companies and positions using , sign. Plane text in single paragraph, no formatting. CV Text: {text}",
        'skills': f"Create a comprehensive list of all skills mentioned in this CV, including technical skills, software proficiency, languages, and soft skills, and nothing else. Plane text in single paragraph, no formatting. Just list the skills using , sign. CV Text: {text}",
        'contact': f"Extract all contact information from this CV, including name, email, phone number and nothing else. Plane text in single paragraph, no formatting. NO FORMATTING! CV Text: {text}"
    }
    
    try:
        response = get_completion(prompts[section], instructions[section])
        
        # Validate response
        if not response or len(response) < 20:
            return f"No detailed {section} information could be extracted from the CV."
            
        # Post-process response
        response = response.replace('\n', '<br>')
        response = re.sub(r'\s+', ' ', response)
        
        return response
        
    except Exception as e:
        logger.error(f"Error generating description for {section}: {str(e)}")
        return f"Error analyzing {section} section. Please try again."

@app.route('/', methods=['GET', 'POST'])
def upload_file():
    if request.method == 'POST':
        if 'file' not in request.files:
            return 'No file uploaded', 400
        
        file = request.files['file']
        if file.filename == '':
            return 'No file selected', 400
        
        if not file.filename.lower().endswith('.pdf'):
            return 'Only PDF files are supported', 400
        
        try:
            # Save the file with a secure filename
            filename = os.path.join(app.config['UPLOAD_FOLDER'], 'temp.pdf')
            file.save(filename)
            
            # Extract text
            text = extract_text_from_pdf(filename)
            
            # Validate extracted text
            if not text.strip():
                return 'Could not extract text from PDF. Please ensure the PDF is text-based and not scanned.', 400
            
            # Get descriptions for each section
            sections = {}
            for section in ['education', 'experience', 'skills', 'contact']:
                sections[section] = get_section_description(text, section)
            
            # Read file for display
            with open(filename, 'rb') as pdf_file:
                pdf_base64 = base64.b64encode(pdf_file.read()).decode('utf-8')
            
            # Clean up temporary file
            os.remove(filename)
            
            return render_template('index.html', 
                                sections=sections, 
                                pdf_data=pdf_base64,
                                pdf_loaded=True)
                                
        except Exception as e:
            logger.error(f"Error processing file: {str(e)}")
            # Clean up temporary file if it exists
            if os.path.exists(filename):
                os.remove(filename)
            return f'Error processing PDF file: {str(e)}', 500
                
    return render_template('index.html', pdf_loaded=False)

if __name__ == '__main__':
    app.run(debug=True, port=8000, host='0.0.0.0')