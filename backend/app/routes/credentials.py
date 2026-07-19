from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks
from sqlalchemy.orm import Session
from datetime import datetime
from pydantic import BaseModel
from typing import List, Optional
from backend.app.database import get_db
from backend.app import models
from backend.app.services.encryption import encrypt_password, decrypt_password
from backend.app.services.scraper import login_to_platform
import logging

logger = logging.getLogger("uvicorn.error")
router = APIRouter(prefix="/credentials", tags=["Credentials"])

class CredentialRequest(BaseModel):
    platform: str  # "linkedin", "naukri", etc.
    username: str
    password: str

@router.get("")
def list_credentials(db: Session = Depends(get_db)):
    """Lists saved account platforms and usernames (passwords redacted)."""
    creds = db.query(models.UserCredential).all()
    return [
        {
            "id": c.id,
            "platform": c.platform,
            "username": c.username,
            "has_session": c.session_cookies is not None,
            "last_login_at": c.last_login_at
        }
        for c in creds
    ]

@router.post("")
def save_credential(req: CredentialRequest, db: Session = Depends(get_db)):
    """Saves or updates encrypted user account credentials."""
    platform_name = req.platform.lower().strip()
    
    # Encrypt password
    encrypted_pw = encrypt_password(req.password)
    
    # Check if exists
    cred = db.query(models.UserCredential).filter(models.UserCredential.platform == platform_name).first()
    if cred:
        cred.username = req.username
        cred.encrypted_password = encrypted_pw
        cred.session_cookies = None  # Reset session cookie to force re-test
        cred.last_login_at = None
    else:
        cred = models.UserCredential(
            platform=platform_name,
            username=req.username,
            encrypted_password=encrypted_pw
        )
        db.add(cred)
        
    db.commit()
    db.refresh(cred)
    
    return {
        "message": f"Credentials for {platform_name} successfully saved.",
        "platform": platform_name,
        "username": cred.username
    }

async def run_test_and_save_session(platform: str, username: str):
    """Background task to test login and save active session cookies."""
    from backend.app.database import SessionLocal
    db_session = SessionLocal()
    try:
        cred = db_session.query(models.UserCredential).filter(models.UserCredential.platform == platform).first()
        if not cred:
            return
            
        raw_password = decrypt_password(cred.encrypted_password)
        import asyncio
        cookies = await asyncio.to_thread(login_to_platform, platform, username, raw_password)
        
        # Reload cred inside session to be sure it's active
        cred = db_session.query(models.UserCredential).filter(models.UserCredential.platform == platform).first()
        if cred and cookies:
            # Save session cookies
            cred.session_cookies = cookies
            cred.last_login_at = datetime.utcnow()
            db_session.commit()
            logger.info(f"Background session check for {platform} succeeded. Cookies saved.")
        else:
            logger.warning(f"Failed to save session for {platform}: No cookies returned or credentials removed.")
    except Exception as e:
        logger.error(f"Background session check for {platform} failed: {e}")
        # Mark as failed by removing cookies
        try:
            cred = db_session.query(models.UserCredential).filter(models.UserCredential.platform == platform).first()
            if cred:
                cred.session_cookies = None
                db_session.commit()
        except Exception:
            pass
    finally:
        db_session.close()

@router.post("/{platform}/test")
def test_credential_connection(
    platform: str, 
    background_tasks: BackgroundTasks, 
    db: Session = Depends(get_db)
):
    """
    Triggers a background Playwright browser session that logs into the job board,
    authenticates cookies, and saves session credentials.
    """
    platform_name = platform.lower().strip()
    cred = db.query(models.UserCredential).filter(models.UserCredential.platform == platform_name).first()
    
    if not cred:
        raise HTTPException(status_code=404, detail=f"No credentials saved for {platform_name}")
        
    # Queue login verification task
    background_tasks.add_task(
        run_test_and_save_session,
        platform=platform_name,
        username=cred.username
    )
    
    return {"message": f"Verification process triggered in background. Please complete OTP/MFA in the open browser if prompted."}

@router.delete("/{platform}")
def delete_credential(platform: str, db: Session = Depends(get_db)):
    """Deletes credentials for a specific account."""
    platform_name = platform.lower().strip()
    cred = db.query(models.UserCredential).filter(models.UserCredential.platform == platform_name).first()
    if not cred:
        raise HTTPException(status_code=404, detail="Credentials not found")
        
    db.delete(cred)
    db.commit()
    return {"message": f"Credentials for {platform_name} deleted successfully"}
