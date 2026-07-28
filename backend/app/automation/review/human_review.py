import time
import logging
import asyncio
from typing import Dict, Any, Tuple, List
from sqlalchemy.orm import Session
from backend.app import models
from backend.app.automation.logging.logger import log_state_transition

logger = logging.getLogger("uvicorn.error")

async def pause_for_human_review(
    db: Session,
    app_id: int,
    detected_questions: List[Dict[str, Any]],
    missing_fields: List[str],
    warnings: List[str]
) -> str:
    """
    Pauses execution, saves current state to the DB, and enters an async polling loop
    waiting for human interaction (Approve, Edit, Reject, Skip).
    """
    log_state_transition(db, app_id, "REVIEW", "Pausing application for human review.")
    
    app = db.query(models.Application).filter(models.Application.id == app_id).first()
    if not app:
        raise ValueError(f"Application ID {app_id} not found.")
        
    app.status = "review_pending"
    app.questions_log = detected_questions
    db.commit()

    logger.info(f"Application {app_id} paused. Waiting for human approval via API...")
    
    timeout_seconds = 600
    start_time = time.time()
    
    while time.time() - start_time < timeout_seconds:
        db.refresh(app)
        if app.status == "approved" or app.status == "review_approved":
            log_state_transition(db, app_id, "REVIEW", "User approved application. Resuming...")
            return "approve"
        elif app.status == "rejected":
            log_state_transition(db, app_id, "REVIEW", "User rejected application. Aborting.")
            return "reject"
        elif app.status == "skipped":
            log_state_transition(db, app_id, "REVIEW", "User skipped application. Proceeding next.")
            return "skip"
            
        await asyncio.sleep(2)
        
    log_state_transition(db, app_id, "REVIEW", "Review window timed out. Defaulting to Skip.")
    app.status = "failed"
    db.commit()
    return "skip"


def pause_for_human_review_sync(
    db: Session,
    app_id: int,
    detected_questions: List[Dict[str, Any]],
    missing_fields: List[str] = None,
    warnings: List[str] = None
) -> str:
    """
    Synchronous version of pause_for_human_review for thread-safe execution in background threads.
    """
    log_state_transition(db, app_id, "REVIEW", "Pausing application for human review.")
    
    app = db.query(models.Application).filter(models.Application.id == app_id).first()
    if not app:
        raise ValueError(f"Application ID {app_id} not found.")
        
    app.status = "review_pending"
    app.questions_log = detected_questions
    db.commit()

    logger.info(f"Application {app_id} paused (sync). Waiting for human approval...")
    
    timeout_seconds = 600
    start_time = time.time()
    
    while time.time() - start_time < timeout_seconds:
        db.refresh(app)
        if app.status == "approved" or app.status == "review_approved":
            log_state_transition(db, app_id, "REVIEW", "User approved application (sync). Resuming...")
            return "approve"
        elif app.status == "rejected":
            log_state_transition(db, app_id, "REVIEW", "User rejected application (sync). Aborting.")
            return "reject"
        elif app.status == "skipped":
            log_state_transition(db, app_id, "REVIEW", "User skipped application (sync). Proceeding next.")
            return "skip"
            
        time.sleep(2)
        
    log_state_transition(db, app_id, "REVIEW", "Review window timed out (sync). Defaulting to Skip.")
    app.status = "failed"
    db.commit()
    return "skip"
