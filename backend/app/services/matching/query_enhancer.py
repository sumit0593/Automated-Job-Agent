import json
import logging
import re
from typing import Dict, Any, List
from backend.app.services.llm import query_llm
from backend.app.services.matching.normalizer import expand_skills, normalize_skill

logger = logging.getLogger("uvicorn.error")

def generate_hyde_doc(resume_text: str, skills: List[str], target_title: str = "") -> str:
    """
    Generates a Hypothetical Document (HyDE) representing an ideal job description
    tailored to the candidate's resume and skill set.
    """
    normalized_skills = [normalize_skill(s) for s in skills if s]
    skills_str = ", ".join(normalized_skills[:10])
    
    system_prompt = (
        "You are an expert technical recruiter and talent matching agent. "
        "Based on the candidate's resume and key skills, generate a detailed hypothetical "
        "Job Description (HyDE) that represents an ideal target career opportunity for this candidate. "
        "Include ideal job title, required skills, key responsibilities, and technical stack. "
        "Do not include conversational preamble."
    )
    
    user_prompt = (
        f"Target Role Title: {target_title or 'Senior Technical Specialist'}\n"
        f"Candidate Skills: {skills_str}\n"
        f"Resume Excerpt:\n{resume_text[:1000]}\n\n"
        f"Hypothetical Job Description:"
    )
    
    try:
        logger.info("Generating HyDE hypothetical job description...")
        hyde_output = query_llm(system_prompt, user_prompt, json_mode=False)
        if hyde_output and len(hyde_output.strip()) > 50:
            return hyde_output.strip()
    except Exception as e:
        logger.warning(f"HyDE generation failed: {e}. Using structured fallback.")
        
    # Structured fallback HyDE if LLM unavailable
    return f"Job Opportunity for {target_title or 'Software Engineer'}. Requirements: {skills_str}. Experience with {skills_str}. Candidate background: {resume_text[:400]}"

def decompose_query(resume_text: str, skills: List[str]) -> List[str]:
    """
    Decomposes a candidate profile into 3 distinct search query vectors:
    1. Core Technical Stack Query
    2. Primary Role & Domain Query
    3. Advanced Framework & Architecture Query
    """
    normalized_skills = [normalize_skill(s) for s in skills if s]
    expanded_all = expand_skills(skills)
    
    queries = []
    
    # Query 1: Core Technical Stack
    if normalized_skills:
        queries.append(f"Technical Stack: {', '.join(normalized_skills[:6])}")
        
    # Query 2: Secondary / Expanded Stack
    if len(normalized_skills) > 4:
        queries.append(f"Engineering Role: {', '.join(normalized_skills[3:10])}")
    elif expanded_all:
        queries.append(f"Skills: {', '.join(expanded_all[:8])}")
        
    # Query 3: Full Resume Excerpt Summary
    summary_snippet = resume_text[:300].replace("\n", " ").strip()
    if summary_snippet:
        queries.append(f"Job requirements matching experience: {summary_snippet}")
        
    return queries if queries else ["Software Developer Python JavaScript Engineer"]

def classify_query_intent(query_text: str) -> str:
    """Classifies the query string into standard search intent categories."""
    q_lower = query_text.lower()
    if any(k in q_lower for k in ["remote", "location", "salary", "experience", "full-time", "part-time"]):
        return "filtered_search"
    elif any(k in q_lower for k in ["python", "react", "fastapi", "sql", "aws", "docker", "node", "java", "c++"]):
        return "skill_search"
    elif len(query_text.split()) > 8:
        return "semantic_search"
    return "job_search"
