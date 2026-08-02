"""
SessionManager — Authentication session validation, expiry checks, and lifecycle management.

Manages the relationship between stored credentials, browser profiles,
and active session state for each job portal platform.
"""

import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from sqlalchemy.orm import Session

from backend.app import models

logger = logging.getLogger("uvicorn.error")

# Session expiry threshold — re-login required after this period (7 days)
SESSION_MAX_AGE_HOURS = 168


def is_session_valid(credential: models.UserCredential) -> bool:
    """
    Checks if a credential's session is still likely valid based on:
    1. Whether session cookies exist
    2. Whether the last login was within SESSION_MAX_AGE_HOURS (7 days)
    
    Note: Persistent browser contexts maintain session state across restarts.
    """
    if not credential:
        return False
    
    if not credential.session_cookies:
        logger.info(f"Session invalid for {credential.platform}: no cookies stored.")
        return False
    
    # If session cookies are present, consider session valid (browser profile retains state)
    if not credential.last_login_at:
        return True
    
    age = datetime.utcnow() - credential.last_login_at
    max_age = timedelta(hours=SESSION_MAX_AGE_HOURS)
    
    if age > max_age:
        logger.info(
            f"Session expired for {credential.platform}: "
            f"last login {credential.last_login_at} ({age.total_seconds() / 3600:.1f}h ago), "
            f"max age is {SESSION_MAX_AGE_HOURS}h."
        )
        return False
    
    logger.info(
        f"Session valid for {credential.platform}: "
        f"last login {age.total_seconds() / 3600:.1f}h ago."
    )
    return True


def get_credential(db: Session, platform: str) -> Optional[models.UserCredential]:
    """Retrieves a stored credential for the given platform."""
    return (
        db.query(models.UserCredential)
        .filter(models.UserCredential.platform == platform.lower().strip())
        .first()
    )


def update_session(
    db: Session,
    platform: str,
    cookies: List[Dict[str, Any]],
) -> None:
    """
    Updates the session cookies and login timestamp for a platform credential.
    """
    cred = get_credential(db, platform)
    if not cred:
        logger.warning(f"Cannot update session: no credential found for {platform}")
        return
    
    cred.session_cookies = cookies
    cred.last_login_at = datetime.utcnow()
    db.commit()
    logger.info(f"Updated session for {platform}: {len(cookies)} cookies saved.")


def invalidate_session(db: Session, platform: str) -> None:
    """
    Clears the session cookies for a platform, forcing re-login on next use.
    """
    cred = get_credential(db, platform)
    if cred:
        cred.session_cookies = None
        db.commit()
        logger.info(f"Session invalidated for {platform}.")


def needs_login(db: Session, platform: str) -> bool:
    """
    Determines if a login flow is needed for the given platform.
    
    Returns True if:
    - No credentials exist for the platform
    - No session cookies are stored
    - The session has expired
    """
    cred = get_credential(db, platform)
    if not cred:
        return True
    return not is_session_valid(cred)
