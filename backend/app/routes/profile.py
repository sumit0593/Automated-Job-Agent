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
        "phone": profile.phone,
        "experience_years": profile.experience_years,
        "current_ctc": profile.current_ctc,
        "expected_ctc": profile.expected_ctc,
        "notice_period": profile.notice_period,
        "current_location": profile.current_location,
        "preferred_locations": profile.preferred_locations or ["Noida", "Delhi", "Gurgaon", "Remote"],
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

    for field in ["name", "email", "phone", "experience_years", "current_ctc", "expected_ctc", 
                  "notice_period", "current_location", "preferred_locations", 
                  "work_authorization", "willing_to_relocate", "remote_preference"]:
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
