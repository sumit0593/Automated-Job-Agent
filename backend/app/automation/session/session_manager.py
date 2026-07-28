import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from sqlalchemy.orm import Session

from backend.app import models

logger = logging.getLogger("uvicorn.error")

# Session expiry threshold - 6 hours
SESSION_MAX_AGE_HOURS = 6

def is_session_valid(credential: models.UserCredential) -> bool:
    """
    Checks if a credential's session is still valid based on:
    1. Whether session cookies exist
    2. Whether the last login was within SESSION_MAX_AGE_HOURS
    """
    if not credential:
        return False
    
    if not credential.session_cookies:
        logger.info(f"Session invalid for {credential.platform}: no cookies stored.")
        return False
    
    if not credential.last_login_at:
        logger.info(f"Session invalid for {credential.platform}: no login timestamp.")
        return False
    
    age = datetime.utcnow() - credential.last_login_at
    max_age = timedelta(hours=SESSION_MAX_AGE_HOURS)
    
    if age > max_age:
        logger.info(f"Session expired for {credential.platform}: last login {age.total_seconds() / 3600:.1f}h ago.")
        return False
    
    return True

def get_credential(db: Session, platform: str) -> Optional[models.UserCredential]:
    """Retrieves stored credentials for a platform."""
    return (
        db.query(models.UserCredential)
        .filter(models.UserCredential.platform == platform.lower().strip())
        .first()
    )

def update_session(db: Session, platform: str, cookies: List[Dict[str, Any]]):
    """Saves session cookies and updates last login timestamp."""
    cred = get_credential(db, platform)
    if not cred:
        logger.warning(f"Cannot update session: no credentials found for {platform}")
        return
    
    cred.session_cookies = cookies
    cred.last_login_at = datetime.utcnow()
    db.commit()
    logger.info(f"Updated session for {platform}: {len(cookies)} cookies saved.")

def invalidate_session(db: Session, platform: str):
    """Clears the session cookies for a platform to trigger re-authentication."""
    cred = get_credential(db, platform)
    if cred:
        cred.session_cookies = None
        db.commit()
        logger.info(f"Session invalidated for {platform}.")

def needs_login(db: Session, platform: str) -> bool:
    """Checks if authentication is needed."""
    cred = get_credential(db, platform)
    if not cred:
        return True
    return not is_session_valid(cred)
