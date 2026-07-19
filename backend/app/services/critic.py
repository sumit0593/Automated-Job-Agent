import json
import re
import logging
from typing import Dict, Any, List
from backend.app.services.llm import query_llm

logger = logging.getLogger("uvicorn.error")

def evaluate_resume_with_critic(resume_text: str, job_title: str, job_description: str) -> Dict[str, Any]:
    """
    Evaluates a resume against a job description using LLM to generate an ATS score
    and identify missing keywords.
    """
    system_prompt = (
        "You are an advanced ATS (Applicant Tracking System) critic agent. "
        "Your role is to critically assess how well a candidate's resume matches a specific job description. "
        "You must analyze the text and output a strict JSON object with these keys:\n"
        "1. 'ats_score': An integer from 0 to 100 indicating the matching rating.\n"
        "2. 'missing_keywords': A list of key skills, frameworks, or concepts requested in the job description that are missing or weakly represented in the resume.\n"
        "3. 'recommendations': A list of bullet points detailing how the candidate can strengthen their resume for this specific position.\n"
        "Do not output any normal conversational text, only valid JSON."
    )
    
    user_prompt = (
        f"Job Title: {job_title}\n"
        f"Job Description:\n{job_description}\n\n"
        f"Candidate Resume:\n{resume_text}\n\n"
        f"Critic Assessment JSON:"
    )
    
    logger.info(f"Running ATS Critic for role: {job_title}...")
    llm_output = query_llm(system_prompt, user_prompt, json_mode=True)
    
    try:
        # Find JSON boundaries
        json_match = re.search(r"\{.*\}", llm_output, re.DOTALL)
        if json_match:
            parsed_data = json.loads(json_match.group(0))
            # Validate types
            parsed_data["ats_score"] = int(parsed_data.get("ats_score", 0))
            if not isinstance(parsed_data.get("missing_keywords"), list):
                parsed_data["missing_keywords"] = []
            if not isinstance(parsed_data.get("recommendations"), list):
                parsed_data["recommendations"] = []
            return parsed_data
    except Exception as e:
        logger.error(f"Failed to parse ATS Critic LLM response: {e}. Running fallback critic.")
        
    return run_fallback_critic(resume_text, job_description)

def run_fallback_critic(resume_text: str, job_description: str) -> Dict[str, Any]:
    """
    Fallback critic calculating simple keyword overlap density to determine score.
    """
    resume_lower = resume_text.lower()
    job_lower = job_description.lower()
    
    # Extract important keywords from job description
    potential_keywords = [
        "python", "javascript", "typescript", "react", "fastapi", "django", "flask", 
        "postgres", "sql", "docker", "aws", "gcp", "kubernetes", "langchain", "qdrant",
        "machine learning", "pytorch", "tensorflow", "tailored", "agile", "cicd", "git"
    ]
    
    required_keywords = []
    for kw in potential_keywords:
        if re.search(r"\b" + re.escape(kw) + r"\b", job_lower):
            required_keywords.append(kw)
            
    # Check which are missing in resume
    missing_keywords = []
    found_count = 0
    
    for kw in required_keywords:
        if re.search(r"\b" + re.escape(kw) + r"\b", resume_lower):
            found_count += 1
        else:
            missing_keywords.append(kw.capitalize())
            
    # Compute relative score
    if required_keywords:
        ats_score = int((found_count / len(required_keywords)) * 100)
    else:
        ats_score = 70  # default baseline
        
    recommendations = []
    if missing_keywords:
        recommendations.append(f"Add direct mentions of these technical skills: {', '.join(missing_keywords)}")
    recommendations.append("Align your project experience bullets to match responsibilities listed in the job post.")
    
    return {
        "ats_score": ats_score,
        "missing_keywords": missing_keywords,
        "recommendations": recommendations
    }
