"""
5-Layer Memory Architecture — Question Classifier & Resolver

Routes each recruiter/form question through a layered memory system:

  Layer 1: PROCEDURAL MEMORY  — Deterministic rules from UserProfile (DB)
  Layer 2: SEMANTIC MEMORY    — AnswerBank (DB) with fuzzy keyword matching
  Layer 3: EPISODIC MEMORY    — Past application Q&A from Application logs
  Layer 4: SHORT-TERM MEMORY  — Session-scoped context (current job info)
  Layer 5: LONG-TERM / LLM    — Generative reasoning + auto-save to AnswerBank

Each layer is tried in order. The first layer to produce a confident
answer (confidence >= threshold) short-circuits and returns.
"""

import re
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime

logger = logging.getLogger("uvicorn.error")

DEFAULT_PROFILE = {
    "name": "",
    "email": "",
    "country_code": "+91",
    "phone": "",
    "pan_number": "",
    "date_of_birth": "",
    "last_working_day": "",
    "experience_years": 0.0,
    "current_ctc": "",
    "expected_ctc": "",
    "notice_period": "",
    "current_location": "",
    "preferred_locations": [],
    "skills": [],
    "linkedin_url": "",
    "github_url": "",
    "portfolio_url": "",
    "work_authorization": "",
    "willing_to_relocate": "",
    "remote_preference": ""
}

DEFAULT_ANSWER_BANK = {
    "why_join": "",
    "strengths": "",
    "career_goal": "",
    "why_leaving": ""
}


# ─────────────────────────────────────────────────────────────────────────────
# Layer 1: Procedural Memory — Deterministic Profile Rules
# ─────────────────────────────────────────────────────────────────────────────

# Pattern → profile field mapping (ordered by specificity)
PROCEDURAL_RULES = [
    # Notice period
    {
        "keywords": ["notice period", "notice", "how soon can you start", "availability", "join date", "joining date", "start date"],
        "field": "notice_period",
        "source": "Procedural Memory (Notice Period)",
    },
    # Expected CTC / Salary
    {
        "keywords": ["expected salary", "expected ctc", "salary expectation", "desired salary", "desired ctc", "expected compensation"],
        "field": "expected_ctc",
        "source": "Procedural Memory (Expected CTC)",
    },
    # Current CTC / Salary
    {
        "keywords": ["current salary", "current ctc", "present ctc", "existing salary", "present salary"],
        "field": "current_ctc",
        "source": "Procedural Memory (Current CTC)",
    },
    # Location
    {
        "keywords": ["preferred location", "location preference", "where are you located", "current location", "current city"],
        "field": "preferred_locations",
        "format_fn": lambda val: ", ".join(val) if isinstance(val, list) else str(val),
        "source": "Procedural Memory (Preferred Locations)",
    },
    # Experience
    {
        "keywords": ["years of experience", "total experience", "how many years", "work experience", "professional experience"],
        "field": "experience_years",
        "format_fn": lambda val: f"{val} years",
        "source": "Procedural Memory (Experience Years)",
    },
    # Name
    {
        "keywords": ["your name", "full name", "candidate name", "first name", "last name"],
        "field": "name",
        "source": "Procedural Memory (Name)",
    },
    # Email
    {
        "keywords": ["email", "email address", "email id", "e-mail"],
        "field": "email",
        "source": "Procedural Memory (Email)",
    },
    # Country code
    {
        "keywords": ["country code", "dialing code", "dial code", "isd code"],
        "field": "country_code",
        "source": "Procedural Memory (Country Code)",
    },
    # Phone
    {
        "keywords": ["phone", "mobile", "contact number", "phone number", "mobile number"],
        "field": "phone",
        "format_fn": lambda val: val if str(val).startswith("+") else f"+91 {val}",
        "source": "Procedural Memory (Phone)",
    },
    # Relocation
    {
        "keywords": ["willing to relocate", "relocate", "relocation"],
        "field": "willing_to_relocate",
        "source": "Procedural Memory (Relocation)",
    },
    # Work authorization
    {
        "keywords": ["work authorization", "authorized to work", "visa status", "work permit"],
        "field": "work_authorization",
        "source": "Procedural Memory (Work Authorization)",
    },
    # Remote preference
    {
        "keywords": ["remote", "work from home", "wfh", "hybrid", "onsite preference"],
        "field": "remote_preference",
        "source": "Procedural Memory (Remote Preference)",
    },
    # PAN Number
    {
        "keywords": ["pan number", "pan no", "pan card", "tax id", "tax identification"],
        "field": "pan_number",
        "source": "Procedural Memory (PAN Number)",
    },
    # Date of Birth / DOB
    {
        "keywords": ["date of birth", "dob", "birth date", "born on"],
        "field": "date_of_birth",
        "source": "Procedural Memory (Date of Birth)",
    },
    # Last Working Day / LWD
    {
        "keywords": ["last working day", "lwd", "last day of working", "relieving date", "last day"],
        "field": "last_working_day",
        "source": "Procedural Memory (Last Working Day)",
    },
    # LinkedIn
    {
        "keywords": ["linkedin", "linkedin profile", "linkedin url"],
        "field": "linkedin_url",
        "source": "Procedural Memory (LinkedIn URL)",
    },
    # GitHub
    {
        "keywords": ["github", "github profile", "github url"],
        "field": "github_url",
        "source": "Procedural Memory (GitHub URL)",
    },
    # Portfolio / Website
    {
        "keywords": ["portfolio", "website", "personal website", "portfolio url"],
        "field": "portfolio_url",
        "source": "Procedural Memory (Portfolio URL)",
    },
]


def _query_procedural_memory(question: str, profile: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Layer 1: Procedural Memory — Pattern-match question against deterministic rules
    and resolve from the UserProfile record loaded from the database.
    """
    q_lower = question.lower().strip()

    for rule in PROCEDURAL_RULES:
        if any(kw in q_lower for kw in rule["keywords"]):
            raw_value = profile.get(rule["field"])
            if raw_value is None:
                continue

            format_fn = rule.get("format_fn", str)
            answer = format_fn(raw_value)

            return {
                "source": rule["source"],
                "answer": answer,
                "confidence": 1.0,
                "used_llm": False,
                "memory_layer": "procedural",
            }

    return None


# ─────────────────────────────────────────────────────────────────────────────
# Layer 2: Semantic Memory — AnswerBank (DB) with Fuzzy Keyword Matching
# ─────────────────────────────────────────────────────────────────────────────

# Mapping: question keyword patterns → AnswerBank question_key
SEMANTIC_PATTERNS = {
    "why_join": ["why join", "why work with us", "why do you want to join", "why interested", "motivation for applying"],
    "strengths": ["strength", "greatest strength", "key skills", "your strengths", "core competencies"],
    "career_goal": ["career goal", "where do you see yourself", "career aspiration", "five years", "long term goal"],
    "why_leaving": ["why leaving", "reason for leaving", "why change", "why looking for a new", "reason for change"],
}


def _query_semantic_memory(question: str, answer_bank_records: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """
    Layer 2: Semantic Memory — Look up the AnswerBank table for stored answers.
    Uses both:
      a) Hardcoded keyword patterns → question_key mapping
      b) Fuzzy matching against question_pattern column from DB
    """
    q_lower = question.lower().strip()

    # Build a lookup dict from DB records: question_key → stored_answer
    bank_by_key = {}
    bank_by_pattern = []
    for rec in answer_bank_records:
        key = rec.get("question_key", "")
        bank_by_key[key] = rec.get("stored_answer", "")
        pattern = rec.get("question_pattern", "")
        if pattern:
            bank_by_pattern.append((pattern.lower(), rec.get("stored_answer", ""), rec.get("category", "general")))

    # a) Try hardcoded semantic patterns → question_key
    for key, patterns in SEMANTIC_PATTERNS.items():
        if any(p in q_lower for p in patterns):
            if key in bank_by_key and bank_by_key[key]:
                return {
                    "source": f"Semantic Memory (AnswerBank: {key})",
                    "answer": bank_by_key[key],
                    "confidence": 1.0,
                    "used_llm": False,
                    "memory_layer": "semantic",
                }

    # b) Fuzzy match against question_pattern column from DB
    best_match = None
    best_overlap = 0
    q_words = set(re.findall(r'\w+', q_lower))

    for pattern, answer, category in bank_by_pattern:
        pattern_words = set(re.findall(r'\w+', pattern))
        if not pattern_words:
            continue
        overlap = len(q_words.intersection(pattern_words)) / len(pattern_words)
        if overlap > best_overlap and overlap >= 0.5:
            best_overlap = overlap
            best_match = (answer, category, pattern, overlap)

    if best_match:
        answer, category, matched_pattern, score = best_match
        return {
            "source": f"Semantic Memory (Fuzzy Match: '{matched_pattern}', score={score:.2f})",
            "answer": answer,
            "confidence": min(1.0, score + 0.3),
            "used_llm": False,
            "memory_layer": "semantic",
        }

    return None


# ─────────────────────────────────────────────────────────────────────────────
# Layer 3: Episodic Memory — Past Application Q&A History
# ─────────────────────────────────────────────────────────────────────────────

def _query_episodic_memory(question: str, past_logs: List[str]) -> Optional[Dict[str, Any]]:
    """
    Layer 3: Episodic Memory — Search through past application logs for
    previously answered questions and their responses.
    
    Scans Application.logs entries for patterns like:
      "Q: <question> → A: <answer>"
    """
    q_lower = question.lower().strip()
    q_words = set(re.findall(r'\w+', q_lower))

    if not q_words or not past_logs:
        return None

    for log_text in past_logs:
        if not log_text:
            continue
        # Look for Q&A patterns in logs
        qa_pattern = re.findall(r'Q:\s*(.+?)\s*(?:→|->|=>|A:)\s*(.+?)(?:\n|$)', log_text, re.IGNORECASE)
        for past_q, past_a in qa_pattern:
            past_q_words = set(re.findall(r'\w+', past_q.lower()))
            if not past_q_words:
                continue
            overlap = len(q_words.intersection(past_q_words)) / max(len(q_words), 1)
            if overlap >= 0.6 and past_a.strip():
                return {
                    "source": f"Episodic Memory (Past Q&A: '{past_q.strip()[:50]}...')",
                    "answer": past_a.strip(),
                    "confidence": 0.85,
                    "used_llm": False,
                    "memory_layer": "episodic",
                }

    return None


# ─────────────────────────────────────────────────────────────────────────────
# Layer 4: Short-Term Memory — Current Session Context
# ─────────────────────────────────────────────────────────────────────────────

def _query_short_term_memory(
    question: str,
    session_context: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    """
    Layer 4: Short-Term Memory — Uses current session context (job title,
    company, description) to provide context-aware answers.
    
    Handles company-specific questions like "Why [Company]?" by combining
    the user's generic motivation with the specific company context.
    """
    q_lower = question.lower().strip()
    company = session_context.get("company_name", "")
    job_title = session_context.get("job_title", "")

    # Previously answered questions in this session (avoid re-processing)
    session_cache = session_context.get("_answered_cache", {})
    cache_key = q_lower[:80]
    if cache_key in session_cache:
        return {
            "source": "Short-Term Memory (Session Cache)",
            "answer": session_cache[cache_key],
            "confidence": 1.0,
            "used_llm": False,
            "memory_layer": "short_term",
        }

    # Company-specific question detection (handled by LLM in Layer 5)
    # Return None to delegate to Layer 5 with enriched context
    return None


# ─────────────────────────────────────────────────────────────────────────────
# Layer 5: Long-Term Memory / LLM Reasoning — Generative with Auto-Save
# ─────────────────────────────────────────────────────────────────────────────

def _query_long_term_memory(
    question: str,
    profile: Dict[str, Any],
    session_context: Dict[str, Any],
    save_callback=None,
) -> Dict[str, Any]:
    """
    Layer 5: Long-Term Memory / LLM Reasoning — Generates an answer using
    the LLM Router and optionally saves it to the AnswerBank for future reuse.
    
    This layer is the final fallback. It always returns an answer.
    """
    from backend.app.services.llm import query_llm

    company = session_context.get("company_name", "")
    job_title = session_context.get("job_title", "")
    job_desc = session_context.get("job_description", "")
    q_lower = question.lower().strip()

    # Company-specific question
    if company and company.lower() in q_lower:
        logger.info(f"MemoryRouter[L5]: Generating company-specific answer for '{company}' via LLM...")
        system_prompt = "You are a professional candidate generating a tailored, company-specific answer for a job application."
        user_prompt = (
            f"Company: {company}\n"
            f"Job Title: {job_title}\n"
            f"Company Context: {job_desc[:500] if job_desc else 'Leading technology company'}\n"
            f"Candidate Profile: {profile}\n"
            f"Question: '{question}'\n"
            f"Provide a concise tailored 2-sentence response:"
        )
        source = f"Long-Term Memory (LLM: Company-Specific for {company})"
    else:
        # Generic dynamic reasoning
        logger.info(f"MemoryRouter[L5]: Generating novel answer via LLM for: '{question[:60]}...'")
        system_prompt = "Answer the recruiter question concisely and professionally based on the candidate's profile. Do not add any disclaimers."
        user_prompt = (
            f"Candidate Profile: {profile}\n"
            f"Job Title: {job_title}\n"
            f"Company: {company}\n"
            f"Question: '{question}'\n"
            f"Concise Answer:"
        )
        source = "Long-Term Memory (LLM Dynamic Reasoning)"

    try:
        llm_answer = query_llm(system_prompt, user_prompt, json_mode=False)
        answer = llm_answer.strip()

        # Auto-save to AnswerBank for future reuse (memory consolidation)
        if save_callback and answer and len(answer) > 5:
            try:
                save_callback(
                    question_pattern=question.strip(),
                    stored_answer=answer,
                    category="llm_generated",
                )
                logger.info(f"MemoryRouter[L5]: Auto-saved novel answer to AnswerBank for future reuse.")
            except Exception as save_err:
                logger.warning(f"MemoryRouter[L5]: Could not auto-save to AnswerBank: {save_err}")

        # Cache in short-term memory for this session
        cache = session_context.setdefault("_answered_cache", {})
        cache[q_lower[:80]] = answer

        return {
            "source": source,
            "answer": answer,
            "confidence": 0.90,
            "used_llm": True,
            "memory_layer": "long_term",
        }
    except Exception as e:
        logger.error(f"MemoryRouter[L5]: LLM reasoning error: {e}")
        # Absolute fallback
        fallback = f"Experienced professional with expertise in {', '.join(profile.get('preferred_locations', ['technology']))}."
        return {
            "source": "Long-Term Memory (Static Fallback)",
            "answer": fallback,
            "confidence": 0.50,
            "used_llm": False,
            "memory_layer": "long_term",
        }


# ─────────────────────────────────────────────────────────────────────────────
# Memory Router — Orchestrates All 5 Layers
# ─────────────────────────────────────────────────────────────────────────────

def _load_profile_from_db() -> Dict[str, Any]:
    """Loads the UserProfile from the database. Falls back to defaults if empty."""
    try:
        from backend.app.database import SessionLocal
        from backend.app import models

        db = SessionLocal()
        try:
            profile = db.query(models.UserProfile).first()
            if profile:
                return {
                    "name": profile.name,
                    "email": profile.email,
                    "country_code": getattr(profile, "country_code", "+91") or "+91",
                    "phone": profile.phone,
                    "pan_number": getattr(profile, "pan_number", "") or "",
                    "date_of_birth": getattr(profile, "date_of_birth", "") or "",
                    "last_working_day": getattr(profile, "last_working_day", "") or "",
                    "experience_years": profile.experience_years,
                    "current_ctc": profile.current_ctc,
                    "expected_ctc": profile.expected_ctc,
                    "notice_period": profile.notice_period,
                    "current_location": profile.current_location,
                    "preferred_locations": profile.preferred_locations or [],
                    "skills": getattr(profile, "skills", []) or [],
                    "linkedin_url": getattr(profile, "linkedin_url", "") or "",
                    "github_url": getattr(profile, "github_url", "") or "",
                    "portfolio_url": getattr(profile, "portfolio_url", "") or "",
                    "work_authorization": profile.work_authorization,
                    "willing_to_relocate": profile.willing_to_relocate,
                    "remote_preference": profile.remote_preference,
                }
        finally:
            db.close()
    except Exception as e:
        logger.warning(f"MemoryRouter: Could not load profile from DB: {e}")

    # Fallback defaults
    return DEFAULT_PROFILE.copy()


def _load_answer_bank_from_db() -> List[Dict[str, Any]]:
    """Loads all AnswerBank entries from the database."""
    try:
        from backend.app.database import SessionLocal
        from backend.app import models

        db = SessionLocal()
        try:
            entries = db.query(models.AnswerBank).all()
            return [
                {
                    "question_key": e.question_key,
                    "question_pattern": e.question_pattern,
                    "stored_answer": e.stored_answer,
                    "category": e.category,
                }
                for e in entries
            ]
        finally:
            db.close()
    except Exception as e:
        logger.warning(f"MemoryRouter: Could not load AnswerBank from DB: {e}")
        return []


def _load_past_application_logs() -> List[str]:
    """Loads recent application logs for episodic memory search."""
    try:
        from backend.app.database import SessionLocal
        from backend.app import models

        db = SessionLocal()
        try:
            apps = (
                db.query(models.Application)
                .filter(models.Application.logs.isnot(None))
                .order_by(models.Application.id.desc())
                .limit(20)
                .all()
            )
            return [app.logs for app in apps if app.logs]
        finally:
            db.close()
    except Exception as e:
        logger.warning(f"MemoryRouter: Could not load application logs: {e}")
        return []


def _make_save_callback():
    """Creates a callback to save novel LLM answers to AnswerBank."""
    def _save(question_pattern: str, stored_answer: str, category: str = "llm_generated"):
        from backend.app.database import SessionLocal
        from backend.app import models

        db = SessionLocal()
        try:
            # Generate a normalized question_key from the pattern
            q_key = re.sub(r'[^a-z0-9_]', '_', question_pattern.lower().strip()[:60])

            existing = db.query(models.AnswerBank).filter(
                models.AnswerBank.question_key == q_key
            ).first()

            if not existing:
                entry = models.AnswerBank(
                    question_key=q_key,
                    question_pattern=question_pattern.strip()[:200],
                    stored_answer=stored_answer,
                    category=category,
                )
                db.add(entry)
                db.commit()
        finally:
            db.close()

    return _save


def classify_and_resolve_question(
    question: str,
    user_profile: Dict[str, Any] = None,
    company_name: str = None,
    company_description: str = None,
    job_title: str = None,
    session_context: Dict[str, Any] = None,
) -> Dict[str, Any]:
    """
    Routes a recruiter/form question through the 5-layer memory architecture.
    
    Layers are tried in order (fastest → slowest, cheapest → most expensive):
      1. Procedural → deterministic profile field lookup
      2. Semantic   → AnswerBank keyword/fuzzy match
      3. Episodic   → past application Q&A history
      4. Short-Term → session cache (avoids re-processing)
      5. Long-Term  → LLM reasoning + auto-save for future reuse
    
    Args:
        question: The recruiter/form question text
        user_profile: Optional override profile dict (if None, loads from DB)
        company_name: Company name for context-aware answers
        company_description: Company description for LLM personalization
        job_title: Job title being applied to
        session_context: Mutable dict for short-term memory (reuse across questions in same session)
    
    Returns:
        Dict with keys: source, answer, confidence, used_llm, memory_layer
    """
    if session_context is None:
        session_context = {}

    # Inject context
    if company_name:
        session_context["company_name"] = company_name
    if company_description:
        session_context["job_description"] = company_description
    if job_title:
        session_context["job_title"] = job_title

    # Load profile from DB if not provided
    profile = user_profile or _load_profile_from_db()

    # ── Layer 1: Procedural Memory ──
    result = _query_procedural_memory(question, profile)
    if result:
        logger.info(f"MemoryRouter[L1 Procedural]: Resolved '{question[:40]}...' → {result['source']}")
        return result

    # ── Layer 2: Semantic Memory (AnswerBank) ──
    answer_bank = _load_answer_bank_from_db()
    result = _query_semantic_memory(question, answer_bank)
    if result:
        logger.info(f"MemoryRouter[L2 Semantic]: Resolved '{question[:40]}...' → {result['source']}")
        return result

    # ── Layer 3: Episodic Memory (Past Application Logs) ──
    past_logs = _load_past_application_logs()
    result = _query_episodic_memory(question, past_logs)
    if result:
        logger.info(f"MemoryRouter[L3 Episodic]: Resolved '{question[:40]}...' → {result['source']}")
        return result

    # ── Layer 4: Short-Term Memory (Session Cache) ──
    result = _query_short_term_memory(question, session_context)
    if result:
        logger.info(f"MemoryRouter[L4 ShortTerm]: Resolved '{question[:40]}...' → {result['source']}")
        return result

    # ── Layer 5: Long-Term Memory / LLM Reasoning ──
    save_callback = _make_save_callback()
    result = _query_long_term_memory(question, profile, session_context, save_callback)
    logger.info(f"MemoryRouter[L5 LongTerm]: Resolved '{question[:40]}...' → {result['source']}")
    return result
