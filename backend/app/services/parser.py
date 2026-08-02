import json
import re
import logging
import pdfplumber
from datetime import datetime
from typing import Dict, Any, List, Optional

logger = logging.getLogger("uvicorn.error")

# Comprehensive dictionary of technical skills, frameworks, and tools
EXPANDED_SKILLS_DICTIONARY = [
    # GenAI, LLMs & Agentic Frameworks
    "Generative AI", "Multi-Agent Systems", "RAG", "RAG Pipelines", "LangChain", 
    "LlamaIndex", "LangGraph", "CrewAI", "AutoGen", "ReAct", "MCP", "FastMCP", 
    "Prompt Engineering", "LLM Fine-Tuning", "Transformers", "Mistral", "Claude", 
    "OpenAI", "Gemini", "Hugging Face", "Sarvam LLM", "Sarvam", "LangSmith", 
    "Langfuse", "OCR", "AWS Textract", "Vector Databases",
    
    # Vector DBs & Databases
    "Qdrant", "ChromaDB", "Pinecone", "FAISS", "PostgreSQL", "MySQL", "MongoDB", 
    "Redis", "Metabase", "SSRS", "Zoho Analytics",
    
    # Frontend & UI
    "React", "React.js", "Next.js", "Vue.js", "Angular", "TypeScript", "JavaScript", 
    "Node.js", "Express.js", "MERN", "Tailwind CSS", "MUI", "Storybook", "HTML", "CSS",
    
    # Backend & Core Languages
    "Python", "FastAPI", "Django", "Flask", "Spring Boot", "Java", "C++", "C#", "Rust", 
    "Go", "RESTful APIs", "JWT", "OAuth2", "Pandas",
    
    # Cloud, DevOps & Automation
    "Docker", "AWS", "GCP", "Azure", "CI/CD", "Vercel", "NGINX", "Jenkins", 
    "Playwright", "Cypress", "Postman", "Jupyter", "Anaconda", "Git", "GitHub", 
    "GitLab", "UiPath", "RPA"
]

def extract_text_from_pdf(pdf_path: str) -> str:
    """
    Extracts structured markdown/text from PDF files using Docling (HuggingFace models)
    if available, falling back to pdfplumber with hyperlink annotation extraction.
    """
    # 1. Try Docling DocumentConverter first with explicit pipeline options
    try:
        from docling.document_converter import DocumentConverter, PdfFormatOption
        from docling.datamodel.pipeline_options import PdfPipelineOptions
        
        logger.info(f"Extracting PDF text using Docling (HuggingFace): {pdf_path}")
        
        # Configure pipeline options for clean Markdown conversion
        pipeline_options = PdfPipelineOptions()
        pipeline_options.do_ocr = False  # Text-based PDF extraction (fast & accurate)
        pipeline_options.do_table_structure = True
        
        converter = DocumentConverter(
            format_options={
                "pdf": PdfFormatOption(pipeline_options=pipeline_options)
            }
        )
        
        result = converter.convert(pdf_path)
        markdown_text = result.document.export_to_markdown()
        if markdown_text and len(markdown_text.strip()) > 50:
            logger.info(f"Docling successfully converted PDF to Markdown ({len(markdown_text)} chars).")
            return markdown_text.strip()
    except Exception as e:
        logger.warning(f"Docling parser fallback ({e}). Using pdfplumber parser.")

    # 2. Fallback to pdfplumber with hyperlink annotation extraction
    text = ""
    hyperlinks = []
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text:
                    text += page_text + "\n"
                
                if page.annots:
                    for annot in page.annots:
                        uri = annot.get("uri")
                        if uri:
                            hyperlinks.append(uri)
    except Exception as ex:
        logger.error(f"pdfplumber extraction error: {ex}")

    if hyperlinks:
        text += "\n--- Extracted PDF Links ---\n"
        text += "\n".join(hyperlinks) + "\n"

    return text.strip()

def calculate_years_from_date_ranges(text: str) -> float:
    """
    Calculates total years of experience from employment date ranges in text
    (e.g., 'Apr 2024 - Present', 'Aug 2023 - Mar 2024', '2022 - 2024').
    """
    months_map = {
        "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
        "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12
    }
    
    current_year = datetime.now().year
    current_month = datetime.now().month
    
    total_months = 0
    
    # Pattern: Month Year - Month/Present Year (e.g. Apr 2024 - Present, Aug 2023 - Mar 2024)
    pattern1 = r"(?i)\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s+(\d{4})\s*[-–—\s\bto]+\s*(present|(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s+\d{4})\b"
    matches1 = re.findall(pattern1, text)
    
    for start_m_str, start_y_str, end_str in matches1:
        try:
            s_m = months_map.get(start_m_str.lower()[:3], 1)
            s_y = int(start_y_str)
            
            if "present" in end_str.lower():
                e_m = current_month
                e_y = current_year
            else:
                parts = end_str.strip().split()
                e_m = months_map.get(parts[0].lower()[:3], 1)
                e_y = int(parts[1])
                
            diff = ((e_y - s_y) * 12) + (e_m - s_m)
            if diff > 0:
                total_months += diff
        except Exception:
            pass

    # Explicit text patterns like "3 years", "over 3 years", "3.5 yrs"
    exp_text_matches = re.findall(r"(?i)\b(?:over|more than|around)?\s*(\d+(?:\.\d+)?)\s*(?:\+|\s*plus)?\s*(?:years?|yrs?)\b", text)
    explicit_years = [float(x) for x in exp_text_matches if float(x) <= 40.0]
    
    date_calc_years = round(total_months / 12.0, 1)
    max_explicit = max(explicit_years) if explicit_years else 0.0
    
    return max(date_calc_years, max_explicit)

def parse_resume_text_fallback(text: str) -> Dict[str, Any]:
    """
    Comprehensive fallback parser extracting skills, experience, location, name, email, and phone using regex.
    """
    text_lower = text.lower()
    
    # 1. Experience extraction
    experience = calculate_years_from_date_ranges(text)
    
    # 2. Comprehensive Skill extraction
    extracted_skills = []
    for skill in EXPANDED_SKILLS_DICTIONARY:
        s_lower = skill.lower()
        pattern = r"(?i)\b" + re.escape(s_lower) + r"\b"
        if re.search(pattern, text):
            extracted_skills.append(skill)

    # 3. Location extraction
    location = "Unknown"
    major_cities = [
        "noida", "delhi", "gurgaon", "gurugram", "bangalore", "bengaluru", 
        "mumbai", "pune", "hyderabad", "chennai", "kolkata", "san francisco", 
        "new york", "london", "remote", "singapore"
    ]
    for city in major_cities:
        if re.search(r"(?i)\b" + re.escape(city) + r"\b", text):
            location = city.capitalize()
            break

    # 4. Email extraction
    email = None
    email_match = re.search(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b", text)
    if email_match:
        email = email_match.group(0).strip()

    # 5. Phone & Country Code extraction
    phone = None
    country_code = "+91"
    phone_match = re.search(r"\b(?:\+?91[\s-]?)?([6-9]\d{9})\b", text)
    if phone_match:
        phone = phone_match.group(1).strip()
    else:
        general_phone = re.search(r"\b\d{10}\b", text)
        if general_phone:
            phone = general_phone.group(0).strip()

    # 6. Name extraction fallback (usually first non-empty line)
    name = None
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    if lines:
        first_line = lines[0]
        if len(first_line.split()) <= 4 and not any(c in first_line for c in ["@", "http", ":", "/"]):
            name = first_line

    return {
        "name": name,
        "email": email,
        "phone": phone,
        "country_code": country_code,
        "skills": list(dict.fromkeys(extracted_skills)),
        "experience": experience,
        "location": location
    }

def parse_resume_text_with_llm(raw_text: str) -> Dict[str, Any]:
    """
    Parses resume text using LLM and combines with comprehensive fallback parser.
    Extracts name, email, phone, country_code, skills, experience, and location.
    """
    system_prompt = (
        "You are an expert ATS (Applicant Tracking System) parser. "
        "Analyze the provided resume text and extract key metadata in strict JSON format. "
        "Do not write introductory text, only return valid JSON.\n"
        "The JSON object must have:\n"
        "1. 'name': Full candidate name (or null if not found).\n"
        "2. 'email': Candidate email address (or null if not found).\n"
        "3. 'phone': Candidate 10-digit phone number without country code (or null if not found).\n"
        "4. 'country_code': Country dialing code e.g. '+91' (default '+91').\n"
        "5. 'skills': A comprehensive list of all technical skills, frameworks, AI models, tools, and databases mentioned.\n"
        "6. 'experience': A float representing total years of professional experience (e.g. 3.0 or 3.5).\n"
        "7. 'location': String representing city/region (e.g. 'Noida', 'Bangalore', 'Remote').\n"
    )
    
    user_prompt = f"Resume Text:\n---\n{raw_text[:4000]}\n---\nExtract JSON:"
    
    fallback_data = parse_resume_text_fallback(raw_text)
    parsed_data = None
    
    try:
        from backend.app.services.llm import query_llm
        llm_output = query_llm(system_prompt, user_prompt, json_mode=True)
        json_match = re.search(r"\{.*\}", llm_output, re.DOTALL)
        if json_match:
            parsed_data = json.loads(json_match.group(0))
    except Exception as e:
        logger.warning(f"LLM parsing fallback triggered: {e}")

    if not parsed_data:
        parsed_data = {}

    # Merge skills: take unique union of LLM skills + regex fallback skills
    llm_skills = [s.strip() for s in parsed_data.get("skills", []) if isinstance(s, str)]
    fb_skills = fallback_data.get("skills", [])
    
    merged_skills_map = {}
    for s in fb_skills + llm_skills:
        if s and s.lower() not in merged_skills_map:
            merged_skills_map[s.lower()] = s
            
    final_skills = list(merged_skills_map.values())
    
    # Merge experience: take max of LLM experience and regex/date calculated experience
    try:
        llm_exp = float(parsed_data.get("experience", 0))
    except Exception:
        llm_exp = 0.0
        
    fb_exp = fallback_data.get("experience", 0.0)
    final_experience = max(llm_exp, fb_exp)
    
    # Merge location
    llm_loc = parsed_data.get("location")
    fb_loc = fallback_data.get("location")
    final_location = "Unknown"
    if llm_loc and str(llm_loc).lower() not in ["null", "none", "unknown"]:
        final_location = str(llm_loc).strip()
    elif fb_loc:
        final_location = fb_loc

    # Merge contact details
    final_name = parsed_data.get("name") or fallback_data.get("name")
    final_email = parsed_data.get("email") or fallback_data.get("email")
    final_phone = parsed_data.get("phone") or fallback_data.get("phone")
    final_country_code = parsed_data.get("country_code") or fallback_data.get("country_code") or "+91"

    return {
        "name": str(final_name).strip() if final_name else None,
        "email": str(final_email).strip() if final_email else None,
        "phone": str(final_phone).strip() if final_phone else None,
        "country_code": str(final_country_code).strip() if final_country_code else "+91",
        "skills": final_skills,
        "experience": final_experience,
        "location": final_location
    }

def extract_links(text: str) -> Dict[str, Optional[str]]:
    """
    Extracts LinkedIn, GitHub, and Portfolio URLs from raw resume text using regex.
    """
    linkedin = None
    github = None
    portfolio = None
    
    li_match = re.search(r"(?:https?://)?(?:www\.)?linkedin\.com/in/[\w\-]+/?", text, re.IGNORECASE)
    if li_match:
        linkedin = li_match.group(0).strip()
        
    gh_match = re.search(r"(?:https?://)?(?:www\.)?github\.com/[\w\-]+/?", text, re.IGNORECASE)
    if gh_match:
        github = gh_match.group(0).strip()
        
    urls = re.findall(r"https?://(?:[a-zA-Z0-9\-]+\.)+[a-zA-Z]{2,6}(?:/[\w\-./?%&=]*)?", text)
    for url in urls:
        url_lower = url.lower()
        if "linkedin.com" not in url_lower and "github.com" not in url_lower and "schema.org" not in url_lower:
            portfolio = url.strip()
            break
            
    return {
        "linkedin": linkedin,
        "github": github,
        "portfolio": portfolio
    }
