import logging
from pathlib import Path
from datetime import datetime
from backend.app.config import settings
from backend.app.services.llm import query_llm

logger = logging.getLogger("uvicorn.error")

def tailor_resume_for_job(resume_text: str, job_title: str, job_company: str, job_description: str) -> str:
    """
    Queries LLM to tailor the resume text for a specific job description.
    """
    system_prompt = (
        "You are an elite executive resume writer and career consultant. "
        "Your task is to tailor the candidate's resume to align with the provided job description. "
        "Strictly follow these guidelines:\n"
        "1. Highlight skills and projects that match the job description.\n"
        "2. Rephrase past experience bullet points to reflect similar responsibilities and keywords requested in the job description.\n"
        "3. DO NOT invent false work history, titles, or certifications. Maintain absolute factual accuracy.\n"
        "4. Format the final output in clean, professional Markdown."
    )
    
    user_prompt = (
        f"Job Title: {job_title}\n"
        f"Company: {job_company}\n"
        f"Job Description:\n{job_description}\n\n"
        f"Candidate Resume:\n{resume_text}\n\n"
        f"Tailored Resume (Markdown):"
    )
    
    logger.info(f"Generating tailored resume for {job_title} at {job_company}...")
    tailored_text = query_llm(system_prompt, user_prompt, json_mode=False)
    return tailored_text

def generate_cover_letter(resume_text: str, job_title: str, job_company: str, job_description: str) -> str:
    """
    Queries LLM to generate a customized cover letter for the job description.
    """
    system_prompt = (
        "You are a professional career coach. Write a compelling, highly customized cover letter "
        "addressed to the hiring manager for the specified job description. "
        "Guidelines:\n"
        "1. Start with a strong hook explaining why the candidate is excited about the role.\n"
        "2. Use 2-3 body paragraphs connecting the candidate's actual resume points directly to the job needs.\n"
        "3. Maintain a professional, confident, and engaging tone.\n"
        "4. Output the letter in clean plain text format."
    )
    
    user_prompt = (
        f"Job Title: {job_title}\n"
        f"Company: {job_company}\n"
        f"Job Description:\n{job_description}\n\n"
        f"Candidate Resume:\n{resume_text}\n\n"
        f"Cover Letter:"
    )
    
    logger.info(f"Generating cover letter for {job_title} at {job_company}...")
    cover_letter = query_llm(system_prompt, user_prompt, json_mode=False)
    return cover_letter

def save_tailored_resume(resume_id: int, job_id: int, tailored_content: str) -> str:
    """
    Saves the tailored resume to the local storage folder and returns the file path.
    """
    filename = f"resume_{resume_id}_job_{job_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
    file_path = Path(settings.TAILORED_RESUMES_PATH) / filename
    
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(tailored_content)
        
    logger.info(f"Saved tailored resume to {file_path}")
    return str(file_path)
