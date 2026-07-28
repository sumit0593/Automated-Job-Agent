import json
import logging
from datetime import datetime
from sqlalchemy.orm import Session
from backend.app import models

logger = logging.getLogger("uvicorn.error")

def log_state_transition(db: Session, app_id: int, state_name: str, message: str):
    """Logs a state transition in the DB and terminal."""
    try:
        app = db.query(models.Application).filter(models.Application.id == app_id).first()
        if app:
            app.current_state = state_name
            timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
            log_line = f"[{timestamp}] State -> {state_name}: {message}\n"
            app.logs = (app.logs or "") + log_line
            db.commit()
            logger.info(f"App {app_id} State transition: {state_name} - {message}")
    except Exception as e:
        logger.error(f"Failed to log state transition for app {app_id}: {e}")

def add_screenshot_to_log(db: Session, app_id: int, state_name: str, path: str):
    """Appends a captured screenshot path to the application log."""
    try:
        app = db.query(models.Application).filter(models.Application.id == app_id).first()
        if app:
            current_log = app.screenshots_log or []
            current_log.append({
                "state": state_name,
                "path": path,
                "timestamp": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
            })
            app.screenshots_log = current_log
            db.commit()
            logger.info(f"App {app_id} Screenshot added: {state_name} -> {path}")
    except Exception as e:
        logger.error(f"Failed to save screenshot log for app {app_id}: {e}")

def add_question_to_log(db: Session, app_id: int, question: str, answer: str):
    """Appends an answered question to the application log."""
    try:
        app = db.query(models.Application).filter(models.Application.id == app_id).first()
        if app:
            current_log = app.questions_log or []
            current_log.append({
                "question": question,
                "answer": answer,
                "timestamp": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
            })
            app.questions_log = current_log
            db.commit()
    except Exception as e:
        logger.error(f"Failed to save question log for app {app_id}: {e}")
