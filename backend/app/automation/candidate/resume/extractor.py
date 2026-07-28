import json
import re
import logging
from typing import Dict, Any
from backend.app.services.llm import query_llm

logger = logging.getLogger("uvicorn.error")

def extract_candidate_profile(raw_resume_text: str) -> Dict[str, Any]:
    """
    Uses the LLM to parse raw resume text and extract a comprehensive, structured
    Candidate Profile JSON matching the required schema.
    """
    system_prompt = (
        "You are a professional ATS parser and talent researcher. Your job is to extract "
        "detailed, structured biographical and professional data from raw resume text. "
        "Return ONLY a valid JSON object matching the schema below. Do not output any "
        "conversational text, markdown blocks other than JSON, or explanations.\n\n"
        "JSON SCHEMA:\n"
        "{\n"
        "  \"personal\": {\n"
        "    \"email\": \"...\",\n"
        "    \"phone\": \"...\",\n"
        "    \"address\": \"...\",\n"
        "    \"location\": \"...\",\n"
        "    \"linkedin\": \"...\",\n"
        "    \"github\": \"...\",\n"
        "    \"portfolio\": \"...\",\n"
        "    \"leetcode\": \"...\"\n"
        "  },\n"
        "  \"employment\": {\n"
        "    \"current_company\": \"...\",\n"
        "    \"current_designation\": \"...\",\n"
        "    \"current_ctc\": \"...\",\n"
        "    \"expected_ctc\": \"...\",\n"
        "    \"notice_period\": \"...\",\n"
        "    \"preferred_locations\": [],\n"
        "    \"preferred_roles\": [],\n"
        "    \"visa_status\": \"...\",\n"
        "    \"work_authorization\": \"...\"\n"
        "  },\n"
        "  \"education\": [\n"
        "    {\n"
        "      \"degree\": \"...\",\n"
        "      \"university\": \"...\",\n"
        "      \"graduation_year\": \"...\"\n"
        "    }\n"
        "  ],\n"
        "  \"skills\": {\n"
        "    \"skill_categories\": {\n"
        "      \"category_name\": [\"skill1\", \"skill2\"]\n"
        "    },\n"
        "    \"years_of_experience_per_skill\": {\n"
        "      \"skill_name\": 0.0\n"
        "    },\n"
        "    \"total_experience\": 0.0\n"
        "  },\n"
        "  \"projects\": [\n"
        "    {\n"
        "      \"name\": \"...\",\n"
        "      \"technologies\": [],\n"
        "      \"responsibilities\": \"...\",\n"
        "      \"achievements\": \"...\"\n"
        "    }\n"
        "  ],\n"
        "  \"certifications\": [],\n"
        "  \"languages\": [],\n"
        "  \"strengths\": [],\n"
        "  \"achievements\": [],\n"
        "  \"career_summary\": \"...\"\n"
        "}\n\n"
        "Factual Rule: Extract ONLY information present in the resume. If a field is missing, "
        "leave it as null or empty string, do not hallucinate."
    )

    user_prompt = f"Resume Text:\n---\n{raw_resume_text}\n---\nJSON Output:"

    try:
        logger.info("extractor: Calling LLM to parse detailed Candidate Profile...")
        output = query_llm(system_prompt, user_prompt, json_mode=True)
        # Find JSON boundaries
        json_match = re.search(r"\{.*\}", output, re.DOTALL)
        if json_match:
            profile_dict = json.loads(json_match.group(0))
            return normalize_extracted_profile(profile_dict, raw_resume_text)
    except Exception as e:
        logger.error(f"extractor: LLM-based profile extraction failed: {e}")
    
    return generate_fallback_profile(raw_resume_text)

def normalize_extracted_profile(profile: Dict[str, Any], raw_text: str) -> Dict[str, Any]:
    """Ensures keys exist and parses common values if missing."""
    # Basic normalization
    if "personal" not in profile:
        profile["personal"] = {}
    
    # Try using regex for social links if LLM missed them
    p = profile["personal"]
    if not p.get("linkedin"):
        li_match = re.search(r"(?:https?://)?(?:www\.)?linkedin\.com/in/[\w\-]+/?", raw_text, re.IGNORECASE)
        p["linkedin"] = li_match.group(0).strip() if li_match else ""
    if not p.get("github"):
        gh_match = re.search(r"(?:https?://)?(?:www\.)?github\.com/[\w\-]+/?", raw_text, re.IGNORECASE)
        p["github"] = gh_match.group(0).strip() if gh_match else ""
        
    if "employment" not in profile:
        profile["employment"] = {}
    
    emp = profile["employment"]
    # Fallbacks for CTC & Notice Period
    if not emp.get("notice_period"):
        emp["notice_period"] = "Immediate"
    if not emp.get("current_ctc"):
        emp["current_ctc"] = "Not specified"
    if not emp.get("expected_ctc"):
        emp["expected_ctc"] = "Negotiable"

    if "skills" not in profile:
        profile["skills"] = {"skill_categories": {}, "years_of_experience_per_skill": {}, "total_experience": 0.0}
    
    return profile

def generate_fallback_profile(raw_text: str) -> Dict[str, Any]:
    """Generates a structured profile with basic details if LLM fails completely."""
    from backend.app.services.parser import parse_resume_text_fallback, extract_links
    parsed = parse_resume_text_fallback(raw_text)
    links = extract_links(raw_text)
    
    return {
        "personal": {
            "email": "",
            "phone": "",
            "address": "",
            "location": parsed.get("location", "Unknown"),
            "linkedin": links.get("linkedin") or "",
            "github": links.get("github") or "",
            "portfolio": links.get("portfolio") or "",
            "leetcode": ""
        },
        "employment": {
            "current_company": "",
            "current_designation": "",
            "current_ctc": "Not specified",
            "expected_ctc": "Negotiable",
            "notice_period": "Immediate",
            "preferred_locations": [],
            "preferred_roles": [],
            "visa_status": "",
            "work_authorization": ""
        },
        "education": [],
        "skills": {
            "skill_categories": {
                "Technical Skills": parsed.get("skills", [])
            },
            "years_of_experience_per_skill": {},
            "total_experience": parsed.get("experience", 0.0)
        },
        "projects": [],
        "certifications": [],
        "languages": [],
        "strengths": [],
        "achievements": [],
        "career_summary": "Extracted profile from resume."
    }
