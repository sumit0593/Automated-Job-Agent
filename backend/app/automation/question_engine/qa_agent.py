import logging
import re
from typing import Dict, Any, List, Optional
from backend.app.services.llm import query_llm
from backend.app.services.vectorstore import vector_store

logger = logging.getLogger("uvicorn.error")

class QuestionAnsweringAgent:
    """
    Intelligent Question Answering Agent for Job Applications.
    Executes: Intent Detection -> Entity Extraction -> Semantic Search -> LLM Synthesis -> Validation.
    """
    def __init__(self, db_session = None):
        self.db = db_session

    def detect_intent(self, question: str) -> str:
        """Detects the category or intent of the question."""
        q_lower = question.lower()
        
        # Simple rule-based classification first for speed
        if any(x in q_lower for x in ["notice", "joining", "start date", "earliest date", "how soon"]):
            return "notice_period"
        elif any(x in q_lower for x in ["current ctc", "current salary", "present ctc", "present salary"]):
            return "current_ctc"
        elif any(x in q_lower for x in ["expected ctc", "expected salary", "salary expectation", "compensation expectation"]):
            return "expected_ctc"
        elif any(x in q_lower for x in ["last working day", "last day"]):
            return "last_working_day"
        elif "python" in q_lower:
            return "python_experience"
        elif "react" in q_lower:
            return "react_experience"
        elif any(x in q_lower for x in ["leader", "manage", "led", "team"]):
            return "leadership"
        elif any(x in q_lower for x in ["relocate", "relocation"]):
            return "relocation"
        elif "remote" in q_lower:
            return "remote"
        elif "hybrid" in q_lower:
            return "hybrid"
        elif any(x in q_lower for x in ["visa", "sponsor", "work authorization", "authorized to work", "citizenship"]):
            return "visa_status"
        elif any(x in q_lower for x in ["current company", "current employer", "work at"]):
            return "current_company"
        elif any(x in q_lower for x in ["leaving", "reason for change"]):
            return "reason_for_leaving"
        elif any(x in q_lower for x in ["why hire", "why should we hire", "why this role", "interest in"]):
            return "why_hire_you"
        elif any(x in q_lower for x in ["describe yourself", "introduce yourself", "about yourself"]):
            return "about_yourself"
        elif "github" in q_lower:
            return "github"
        elif "portfolio" in q_lower or "website" in q_lower:
            return "portfolio"
        elif "linkedin" in q_lower:
            return "linkedin"
        elif any(x in q_lower for x in ["strength", "greatest strength"]):
            return "strengths"
        elif any(x in q_lower for x in ["achievement", "accomplishment"]):
            return "achievements"

        # LLM fallback for intent detection
        system_prompt = (
            "You are an intent classifier. Categorize the given job application question "
            "into exactly one of these labels, returning ONLY the label name: "
            "notice_period, current_ctc, expected_ctc, last_working_day, python_experience, "
            "react_experience, leadership, relocation, remote, hybrid, visa_status, "
            "current_company, reason_for_leaving, why_hire_you, about_yourself, github, "
            "portfolio, linkedin, strengths, achievements, general_experience, general_interest."
        )
        try:
            intent = query_llm(system_prompt, f"Question: {question}", json_mode=False).strip().lower()
            return intent
        except Exception:
            return "general"

    def extract_entities(self, question: str) -> List[str]:
        """Extracts technical terms or keywords mentioned in the question."""
        entities = []
        tech_words = [
            "python", "react", "node", "javascript", "typescript", "fastapi", "django", 
            "docker", "kubernetes", "aws", "gcp", "azure", "sql", "postgresql"
        ]
        for word in tech_words:
            if re.search(r"\b" + re.escape(word) + r"\b", question.lower()):
                entities.append(word.capitalize())
        return entities

    def retrieve_context(self, resume_id: int, question: str, intent: str) -> str:
        """Retrieves semantic profile chunks from Qdrant matching the question context."""
        try:
            logger.info(f"qa_agent: Querying Qdrant for question context: '{question}'...")
            hits = vector_store.search_profile_chunks(resume_id, query=question, limit=4)
            if hits:
                return "\n\n".join(f"[{h['category'].upper()}]\n{h['content']}" for h in hits)
        except Exception as e:
            logger.error(f"qa_agent: Context retrieval from Qdrant failed: {e}")
        return ""

    def generate_answer(self, resume_id: int, question: str, candidate_profile: Dict[str, Any]) -> str:
        """
        Main answering logic. Combines Intent detection, Entity extraction,
        Semantic Search, Profile details and LLM synthesis.
        """
        intent = self.detect_intent(question)
        entities = self.extract_entities(question)
        semantic_context = self.retrieve_context(resume_id, question, intent)

        # Build precise candidate fact sheet from structured profile to feed the LLM
        personal = candidate_profile.get("personal", {})
        employment = candidate_profile.get("employment", {})
        skills = candidate_profile.get("skills", {})
        
        profile_facts = {
            "full_name": f"{personal.get('first_name', '')} {personal.get('last_name', '')}",
            "email": personal.get("email", ""),
            "phone": personal.get("phone", ""),
            "location": personal.get("location", ""),
            "linkedin": personal.get("linkedin", ""),
            "github": personal.get("github", ""),
            "portfolio": personal.get("portfolio", ""),
            "current_company": employment.get("current_company", ""),
            "current_designation": employment.get("current_designation", ""),
            "current_ctc": employment.get("current_ctc", ""),
            "expected_ctc": employment.get("expected_ctc", ""),
            "notice_period": employment.get("notice_period", ""),
            "visa_status": employment.get("visa_status", ""),
            "work_authorization": employment.get("work_authorization", ""),
            "total_experience": skills.get("total_experience", 0.0),
        }

        # Match specific intent parameters directly as high-priority constraints
        intent_hint = ""
        if intent == "notice_period" and profile_facts["notice_period"]:
            intent_hint = f"Candidate notice period is: {profile_facts['notice_period']}."
        elif intent == "current_ctc" and profile_facts["current_ctc"]:
            intent_hint = f"Candidate current CTC is: {profile_facts['current_ctc']}."
        elif intent == "expected_ctc" and profile_facts["expected_ctc"]:
            intent_hint = f"Candidate expected CTC is: {profile_facts['expected_ctc']}."
        elif intent == "current_company" and profile_facts["current_company"]:
            intent_hint = f"Candidate's current company is: {profile_facts['current_company']} and current title is {profile_facts['current_designation']}."
        elif intent == "visa_status" and profile_facts["visa_status"]:
            intent_hint = f"Candidate visa status/work authorization: {profile_facts['visa_status']}, {profile_facts['work_authorization']}."
        elif "experience" in intent:
            # Check years of experience per skill
            exp_per_skill = skills.get("years_of_experience_per_skill", {})
            for entity in entities:
                if entity.lower() in exp_per_skill:
                    intent_hint += f"Candidate has {exp_per_skill[entity.lower()]} years of experience in {entity}. "

        system_prompt = (
            "You are a job application assistant. Your task is to write a brief, factual, "
            "professional answer to a job application form question on behalf of the candidate.\n"
            "Strictly follow these rules:\n"
            "1. Output ONLY the answer text, no greetings, introductions, or meta-commentary.\n"
            "2. Keep the answer extremely concise, ideally 1-3 sentences or just the numeric value if requested.\n"
            "3. Rely ONLY on the provided candidate facts and context. Never invent details.\n"
            "4. Do not leave any placeholders, template variables, or brackets (e.g. do not output '[Insert Date]')."
        )

        user_prompt = (
            f"Question: {question}\n\n"
            f"Candidate profile facts:\n"
            f"{json.dumps(profile_facts, indent=2)}\n\n"
            f"Factual Intent Hint:\n{intent_hint}\n\n"
            f"Retrieved profile details:\n"
            f"{semantic_context}\n\n"
            f"Accurate Answer:"
        )

        try:
            answer = query_llm(system_prompt, user_prompt, json_mode=False).strip()
            # Clean up wrap quotes or markdown formatting
            answer = re.sub(r'^["\']|["\']$', '', answer).strip()
            
            # Simple validation rules
            if self.validate_answer(answer, question):
                return answer
        except Exception as e:
            logger.error(f"qa_agent: LLM generation failed: {e}")

        # Fallback to direct field output based on intent
        return self.get_direct_fallback(intent, profile_facts)

    def validate_answer(self, answer: str, question: str) -> bool:
        """Validates that the answer contains no placeholder indicators."""
        if not answer:
            return False
        # Reject answers containing brackets or common placeholder words
        placeholders = ["[", "]", "{", "}", "insert", "candidate name", "placeholder", "todo"]
        if any(p in answer.lower() for p in placeholders):
            logger.warning(f"qa_agent: Answer validation failed (placeholder detected): {answer}")
            return False
        return True

    def get_direct_fallback(self, intent: str, facts: Dict[str, Any]) -> str:
        """Returns direct profile values if LLM parsing/validation fails."""
        mapping = {
            "notice_period": facts["notice_period"] or "Immediate",
            "current_ctc": facts["current_ctc"] or "Not specified",
            "expected_ctc": facts["expected_ctc"] or "Negotiable",
            "current_company": facts["current_company"] or "None",
            "visa_status": facts["visa_status"] or "No sponsorship required",
            "github": facts["github"],
            "portfolio": facts["portfolio"],
            "linkedin": facts["linkedin"],
        }
        fallback = mapping.get(intent)
        if not fallback:
            # Fallback for experience
            if "experience" in intent:
                return f"{facts['total_experience']} years"
            return "Yes"
        return fallback
