import json
import logging
from pathlib import Path
from typing import Dict, Any, Optional
from sqlalchemy.orm import Session
from backend.app import models

logger = logging.getLogger("uvicorn.error")

DEFAULT_PROFILE_PATH = Path("candidate_profile.json")

def load_candidate_profile_from_db(db: Session, resume_id: int) -> Optional[Dict[str, Any]]:
    """Loads the structured candidate profile from the database for a specific resume."""
    resume = db.query(models.Resume).filter(models.Resume.id == resume_id).first()
    if resume and resume.candidate_profile:
        return resume.candidate_profile
    return None

def save_candidate_profile_to_db(db: Session, resume_id: int, profile: Dict[str, Any]):
    """Saves the structured candidate profile to the database for a specific resume."""
    resume = db.query(models.Resume).filter(models.Resume.id == resume_id).first()
    if resume:
        resume.candidate_profile = profile
        db.commit()
        logger.info(f"Candidate profile saved to DB for resume ID {resume_id}")
    else:
        logger.warning(f"Resume ID {resume_id} not found in DB when saving candidate profile.")

def load_candidate_profile_from_file(file_path: Path = DEFAULT_PROFILE_PATH) -> Dict[str, Any]:
    """Loads the candidate profile from a local JSON file."""
    if file_path.exists():
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Failed to load candidate profile from file: {e}")
    return {}

def save_candidate_profile_to_file(profile: Dict[str, Any], file_path: Path = DEFAULT_PROFILE_PATH):
    """Saves the candidate profile to a local JSON file."""
    try:
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(profile, f, indent=2, ensure_ascii=False)
        logger.info(f"Candidate profile saved to local file: {file_path}")
    except Exception as e:
        logger.error(f"Failed to save candidate profile to file: {e}")
