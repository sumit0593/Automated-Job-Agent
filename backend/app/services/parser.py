import json
import re
import pdfplumber
from typing import Dict, Any, List, Optional
from backend.app.services.llm import query_llm

COMMON_SKILLS = [
    "python", "javascript", "typescript", "react", "fastapi", "django", "flask", 
    "node", "express", "sql", "postgresql", "mysql", "mongodb", "redis", "docker", 
    "aws", "gcp", "azure", "git", "kubernetes", "langchain", "llama-index", "langgraph",
    "qdrant", "chromadb", "pinecone", "faiss", "crewai", "autogen", "mcp", "jwt",
    "machine learning", "deep learning", "nlp", "pytorch", "tensorflow",
    "html", "css", "tailwind", "next.js", "vue", "angular", "java", "c++", "c#", "rust", "go"
]

def extract_text_from_pdf(pdf_path: str) -> str:
    """
    Extracts plain text from a PDF file using pdfplumber,
    and appends hyperlinked URIs to the text so they can be parsed.
    """
    text = ""
    hyperlinks = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            page_text = page.extract_text()
            if page_text:
                text += page_text + "\n"
            
            # Extract hyperlink URIs from page annotations
            if page.annots:
                for annot in page.annots:
                    uri = annot.get("uri")
                    if uri:
                        hyperlinks.append(uri)
                        
    # Append the found hyperlinks to the bottom of the text so that
    # downstream regex/LLM parsers can extract them easily.
    if hyperlinks:
        text += "\n--- Extracted PDF Links ---\n"
        text += "\n".join(hyperlinks) + "\n"
        
    return text.strip()

def parse_resume_text_with_llm(raw_text: str) -> Dict[str, Any]:
    """
    Asks LLM to parse raw resume text and return structured details.
    """
    system_prompt = (
        "You are an expert ATS (Applicant Tracking System) parser. "
        "Your task is to analyze the provided resume text and extract key metadata in strict JSON format. "
        "Do not write any introductory or concluding text, only return valid JSON. "
        "The JSON object must have exactly these keys:\n"
        "1. 'skills': A list of technologies, frameworks, and programming languages found (e.g., ['React', 'FastAPI', 'Python']).\n"
        "2. 'experience': A float or integer representing the total years of professional experience (e.g., 4 or 2.5). Look for dates or explicitly stated years. If not found, default to 0.\n"
        "3. 'location': A string representing the candidate's current city/region (e.g., 'Delhi', 'San Francisco', 'Remote'). If not found, return null.\n"
    )
    
    user_prompt = f"Resume Text:\n---\n{raw_text}\n---\nExtract JSON:"
    
    llm_output = query_llm(system_prompt, user_prompt, json_mode=True)
    
    # Try parsing JSON from LLM output
    parsed_data = None
    try:
        # Find JSON boundaries in case LLM added markdown formatting (e.g. ```json ... ```)
        json_match = re.search(r"\{.*\}", llm_output, re.DOTALL)
        if json_match:
            parsed_data = json.loads(json_match.group(0))
            # Validate types
            if not isinstance(parsed_data.get("skills"), list):
                parsed_data["skills"] = []
            try:
                parsed_data["experience"] = float(parsed_data.get("experience", 0))
            except (ValueError, TypeError):
                parsed_data["experience"] = 0.0
    except Exception:
        pass
        
    # Get fallback parser results for hybrid skills merge
    fallback_data = parse_resume_text_fallback(raw_text)
    
    if parsed_data:
        # Merge skills: combine LLM-extracted skills and fallback regex skills
        llm_skills = [s.strip() for s in parsed_data.get("skills", []) if isinstance(s, str)]
        fallback_skills = fallback_data.get("skills", [])
        
        # Take unique union case-insensitively, but keep nice casing
        merged_skills_dict = {}
        for s in fallback_skills:
            merged_skills_dict[s.lower()] = s
        for s in llm_skills:
            if s.lower() not in merged_skills_dict:
                merged_skills_dict[s.lower()] = s
                
        parsed_data["skills"] = list(merged_skills_dict.values())

        # Merge location: prioritize specific physical cities over "Remote" or "Unknown"
        llm_loc = parsed_data.get("location")
        fb_loc = fallback_data.get("location")
        if (not llm_loc or str(llm_loc).lower() in ["unknown", "remote", "null", "none"]) and fb_loc and fb_loc.lower() not in ["unknown", "remote"]:
            parsed_data["location"] = fb_loc

        return parsed_data
        
    # If LLM or JSON parsing fails, run regex fallback
    return fallback_data

def parse_resume_text_fallback(text: str) -> Dict[str, Any]:
    """
    Fallback parser using regexes and keyword matching when LLM is unavailable.
    """
    text_lower = text.lower()
    
    # 1. Experience extraction
    experience = 0.0
    # Search for patterns like "4 years", "3.5 yrs", "experience: 5 years"
    exp_matches = re.findall(r"(\d+(?:\.\d+)?)\s*(?:years?|yrs?)\b", text_lower)
    if exp_matches:
        try:
            # Take the maximum number of years found as a heuristic
            experience = max(float(x) for x in exp_matches)
        except ValueError:
            pass
            
    # 2. Skill extraction
    skills = []
    for skill in COMMON_SKILLS:
        # Use word boundaries to avoid matching sub-words (e.g. "go" in "google")
        if re.search(r"\b" + re.escape(skill) + r"\b", text_lower):
            # Capitalize nicely based on common naming conventions
            display_name = skill
            if skill in ["python", "javascript", "typescript", "django", "flask", "docker", "kubernetes", "django", "postgres", "mysql", "mongodb", "redis", "pinecone", "faiss"]:
                display_name = skill.capitalize()
            elif skill in ["react", "fastapi", "next.js", "pytorch", "langchain", "langgraph", "qdrant", "chromadb", "crewai", "autogen"]:
                display_name = skill.replace("api", "API").replace("js", "JS").replace("chain", "Chain").replace("graph", "Graph")
                # Special cases
                if skill == "react": display_name = "React"
                if skill == "fastapi": display_name = "FastAPI"
                if skill == "next.js": display_name = "Next.js"
                if skill == "chromadb": display_name = "ChromaDB"
                if skill == "crewai": display_name = "CrewAI"
                if skill == "autogen": display_name = "AutoGen"
            elif skill in ["html", "css", "sql", "aws", "gcp", "nlp", "mcp", "jwt"]:
                display_name = skill.upper()
            skills.append(display_name)
            
    # 3. Location extraction (simple heuristics)
    location = "Unknown"
    major_cities = ["delhi", "mumbai", "bangalore", "bengaluru", "pune", "hyderabad", "chennai", "noida", "gurgaon", 
                    "san francisco", "new york", "london", "remote", "berlin", "tokyo", "singapore"]
    for city in major_cities:
        if re.search(r"\b" + re.escape(city) + r"\b", text_lower):
            location = city.capitalize()
            break
            
    return {
        "skills": list(set(skills)),
        "experience": experience,
        "location": location
    }

def extract_links(text: str) -> Dict[str, Optional[str]]:
    """
    Extracts LinkedIn, GitHub, and Portfolio URLs from raw resume text using regex.
    """
    linkedin = None
    github = None
    portfolio = None
    
    # Extract linkedin
    li_match = re.search(r"(?:https?://)?(?:www\.)?linkedin\.com/in/[\w\-]+/?", text, re.IGNORECASE)
    if li_match:
        linkedin = li_match.group(0).strip()
        
    # Extract github
    gh_match = re.search(r"(?:https?://)?(?:www\.)?github\.com/[\w\-]+/?", text, re.IGNORECASE)
    if gh_match:
        github = gh_match.group(0).strip()
        
    # Extract other URLs (excluding linkedin, github, and standard page/schema links)
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
