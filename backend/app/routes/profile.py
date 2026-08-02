import json
import logging
from typing import Dict, Any, List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from backend.app.database import get_db
from backend.app.models import UserProfile, UserPreferences, AnswerBank
from backend.app.services.matching.question_classifier import DEFAULT_PROFILE, DEFAULT_ANSWER_BANK

logger = logging.getLogger("uvicorn.error")

router = APIRouter(prefix="/api/profile", tags=["Profile & Preferences"])

@router.get("/")
def get_user_profile(db: Session = Depends(get_db)):
    """Retrieve active candidate profile data."""
    profile = db.query(UserProfile).first()
    if not profile:
        profile = UserProfile()
        db.add(profile)
        db.commit()
        db.refresh(profile)
        
    return {
        "id": profile.id,
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
        "remote_preference": profile.remote_preference
    }

@router.put("/")
def update_user_profile(data: Dict[str, Any], db: Session = Depends(get_db)):
    """Update candidate profile data."""
    profile = db.query(UserProfile).first()
    if not profile:
        profile = UserProfile()
        db.add(profile)

    for field in ["name", "email", "country_code", "phone", "pan_number", "date_of_birth",
                  "last_working_day", "experience_years", "current_ctc", "expected_ctc", 
                  "notice_period", "current_location", "preferred_locations", "skills",
                  "linkedin_url", "github_url", "portfolio_url", "work_authorization",
                  "willing_to_relocate", "remote_preference"]:
        if field in data:
            setattr(profile, field, data[field])

    db.commit()
    db.refresh(profile)
    return {"success": True, "profile": profile}

@router.get("/preferences")
def get_user_preferences(db: Session = Depends(get_db)):
    """Retrieve job matching preferences."""
    pref = db.query(UserPreferences).first()
    if not pref:
        pref = UserPreferences()
        db.add(pref)
        db.commit()
        db.refresh(pref)
        
    return {
        "id": pref.id,
        "target_roles": pref.target_roles or ["AI Engineer", "GenAI Engineer", "Backend Engineer"],
        "minimum_salary": pref.minimum_salary or 700000,
        "employment_type": pref.employment_type or ["Full-time"],
        "preferred_companies": pref.preferred_companies or ["Microsoft", "Google", "OpenAI"]
    }

@router.put("/preferences")
def update_user_preferences(data: Dict[str, Any], db: Session = Depends(get_db)):
    """Update job matching preferences."""
    pref = db.query(UserPreferences).first()
    if not pref:
        pref = UserPreferences()
        db.add(pref)

    for field in ["target_roles", "minimum_salary", "employment_type", "preferred_companies"]:
        if field in data:
            setattr(pref, field, data[field])

    db.commit()
    db.refresh(pref)
    return {"success": True, "preferences": pref}

@router.get("/answers")
def get_answer_bank(db: Session = Depends(get_db)):
    """Retrieve all stored answers in the Answer Bank."""
    entries = db.query(AnswerBank).all()
    if not entries:
        # Populate defaults
        for key, val in DEFAULT_ANSWER_BANK.items():
            db.add(AnswerBank(question_key=key, question_pattern=key, stored_answer=val, category="general"))
        db.commit()
        entries = db.query(AnswerBank).all()

    result = {}
    for entry in entries:
        result[entry.question_key] = entry.stored_answer
    return {"answers": result}

@router.post("/answers")
def save_answer_entry(data: Dict[str, Any], db: Session = Depends(get_db)):
    """Add or update an answer in the Answer Bank."""
    question_key = data.get("question_key")
    stored_answer = data.get("stored_answer")
    if not question_key or not stored_answer:
        raise HTTPException(status_code=400, detail="question_key and stored_answer are required.")

    existing = db.query(AnswerBank).filter(AnswerBank.question_key == question_key).first()
    if existing:
        existing.stored_answer = stored_answer
    else:
        db.add(AnswerBank(question_key=question_key, question_pattern=question_key, stored_answer=stored_answer))

    db.commit()
    return {"success": True, "message": f"Answer for '{question_key}' saved."}

@router.get("/export")
def export_full_profile(db: Session = Depends(get_db)):
    """Export complete candidate configuration as JSON."""
    profile = get_user_profile(db)
    preferences = get_user_preferences(db)
    answers = get_answer_bank(db)
    
    return {
        "profile": profile,
        "preferences": preferences,
        "answers": answers["answers"]
    }

@router.post("/clear")
def clear_user_profile_and_answer_bank(db: Session = Depends(get_db)):
    """
    Safely resets/clears Candidate Profile (UserProfile) and Answer Bank (AnswerBank) records.
    """
    try:
        profile = db.query(UserProfile).first()
        if profile:
            profile.name = ""
            profile.email = ""
            profile.country_code = "+91"
            profile.phone = ""
            profile.pan_number = ""
            profile.date_of_birth = ""
            profile.last_working_day = ""
            profile.experience_years = 0.0
            profile.current_ctc = ""
            profile.expected_ctc = ""
            profile.notice_period = ""
            profile.current_location = ""
            profile.preferred_locations = []
            profile.skills = []
            profile.linkedin_url = ""
            profile.github_url = ""
            profile.portfolio_url = ""
            profile.work_authorization = ""
            profile.willing_to_relocate = ""
            profile.remote_preference = ""

        db.query(AnswerBank).delete()
        db.commit()

        return {
            "success": True,
            "message": "Candidate Profile and Answer Bank cleared successfully."
        }
    except Exception as e:
        db.rollback()
        logger.error(f"Error clearing profile: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to clear profile: {e}")
