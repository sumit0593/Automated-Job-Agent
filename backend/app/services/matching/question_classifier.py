import re
import logging
from typing import Dict, Any, Optional
from backend.app.services.llm import query_llm

logger = logging.getLogger("uvicorn.error")

DEFAULT_PROFILE = {
    "name": "Sumit Kumar",
    "email": "sumit@gmail.com",
    "phone": "+91 7011676185",
    "experience_years": 3.0,
    "current_ctc": "₹5 LPA",
    "expected_ctc": "₹8 LPA",
    "notice_period": "Immediate",
    "current_location": "Noida",
    "preferred_locations": ["Noida", "Delhi", "Gurgaon", "Remote"],
    "work_authorization": "India",
    "willing_to_relocate": "Yes",
    "remote_preference": "Hybrid"
}

DEFAULT_ANSWER_BANK = {
    "why_join": "I enjoy building production-grade AI systems, multi-agent frameworks, and scalable cloud architectures.",
    "strengths": "Problem solving, backend engineering, GenAI, multi-agent systems, and Python microservices.",
    "career_goal": "To become a Lead AI Platform Engineer building scalable agentic systems.",
    "why_leaving": "Seeking higher impact roles specializing in Generative AI and Multi-Agent Orchestration."
}

def classify_and_resolve_question(
    question: str, 
    user_profile: Dict[str, Any] = None,
    company_name: str = None,
    company_description: str = None
) -> Dict[str, Any]:
    """
    Classifies a recruiter/form question and resolves the answer deterministically 
    from profile data or stored answer bank before using LLM reasoning.
    """
    if not user_profile:
        user_profile = DEFAULT_PROFILE

    q_lower = question.lower().strip()

    # 1. Notice Period
    if any(k in q_lower for k in ["notice period", "notice", "how soon can you start", "availability", "join date"]):
        return {
            "source": "profile.json (Notice Period)",
            "answer": str(user_profile.get("notice_period", "Immediate")),
            "confidence": 1.0,
            "used_llm": False
        }

    # 2. Expected Salary / CTC
    if any(k in q_lower for k in ["expected salary", "expected ctc", "salary expectation", "desired salary"]):
        return {
            "source": "profile.json (Expected CTC)",
            "answer": str(user_profile.get("expected_ctc", "₹8 LPA")),
            "confidence": 1.0,
            "used_llm": False
        }

    # 3. Current Salary / CTC
    if any(k in q_lower for k in ["current salary", "current ctc", "present ctc", "existing salary"]):
        return {
            "source": "profile.json (Current CTC)",
            "answer": str(user_profile.get("current_ctc", "₹5 LPA")),
            "confidence": 1.0,
            "used_llm": False
        }

    # 4. Preferred Location / Current Location
    if any(k in q_lower for k in ["preferred location", "location preference", "where are you located", "current location"]):
        locations = user_profile.get("preferred_locations", ["Noida", "Remote"])
        loc_str = ", ".join(locations) if isinstance(locations, list) else str(locations)
        return {
            "source": "profile.json (Preferred Locations)",
            "answer": loc_str,
            "confidence": 1.0,
            "used_llm": False
        }

    # 5. Experience Years
    if any(k in q_lower for k in ["years of experience", "total experience", "how many years"]):
        return {
            "source": "resume.json / profile.json (Experience)",
            "answer": f"{user_profile.get('experience_years', 3.0)} years",
            "confidence": 1.0,
            "used_llm": False
        }

    # 6. Stored Answers Lookup (Why Join / Strengths / Career Goal)
    if any(k in q_lower for k in ["why join", "why work with us", "why do you want to join"]):
        return {
            "source": "answers.json (why_join)",
            "answer": DEFAULT_ANSWER_BANK["why_join"],
            "confidence": 1.0,
            "used_llm": False
        }
    if any(k in q_lower for k in ["strength", "greatest strength", "key skills"]):
        return {
            "source": "answers.json (strengths)",
            "answer": DEFAULT_ANSWER_BANK["strengths"],
            "confidence": 1.0,
            "used_llm": False
        }
    if any(k in q_lower for k in ["career goal", "where do you see yourself"]):
        return {
            "source": "answers.json (career_goal)",
            "answer": DEFAULT_ANSWER_BANK["career_goal"],
            "confidence": 1.0,
            "used_llm": False
        }

    # 7. Company-Specific Customization (e.g. "Why Microsoft?")
    if company_name and f"why {company_name.lower()}" in q_lower:
        logger.info(f"QuestionClassifier: Tailoring company-specific answer for '{company_name}' via LLM...")
        system_prompt = "You are a professional candidate generating a tailored, company-specific answer for a job application."
        user_prompt = (
            f"Company: {company_name}\n"
            f"Company Context: {company_description or 'Leading technology company'}\n"
            f"Candidate Stored Motivation: '{DEFAULT_ANSWER_BANK['why_join']}'\n"
            f"Question: '{question}'\n"
            f"Provide a concise tailored 2-sentence response:"
        )
        try:
            tailored = query_llm(system_prompt, user_prompt, json_mode=False)
            return {
                "source": "LLM (Company-Specific Customization)",
                "answer": tailored.strip(),
                "confidence": 0.95,
                "used_llm": True
            }
        except Exception:
            pass

    # 8. Dynamic Fallback via LLM Reasoning
    logger.info(f"QuestionClassifier: Uncached question '{question}'. Invoking LLM...")
    system_prompt = "Answer the recruiter question concisely and professionally based on candidate profile."
    user_prompt = f"Profile: {user_profile}\nQuestion: '{question}'\nConcise Answer:"
    try:
        llm_ans = query_llm(system_prompt, user_prompt, json_mode=False)
        return {
            "source": "Dynamic LLM Reasoning Engine",
            "answer": llm_ans.strip(),
            "confidence": 0.90,
            "used_llm": True
        }
    except Exception as e:
        logger.error(f"LLM question resolution error: {e}")
        return {
            "source": "Default Candidate Profile Fallback",
            "answer": "Full-Stack Engineer with 3+ years experience specializing in GenAI and multi-agent systems.",
            "confidence": 0.80,
            "used_llm": False
        }
