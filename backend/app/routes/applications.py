from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from pydantic import BaseModel
from sqlalchemy.orm import Session
from backend.app.database import get_db
from backend.app import models
from backend.app.services.tailor import tailor_resume_for_job, generate_cover_letter, save_tailored_resume
from backend.app.services.critic import evaluate_resume_with_critic
from backend.app.services.scraper import automate_application_flow, detect_ats
import logging

logger = logging.getLogger("uvicorn.error")
router = APIRouter(prefix="/applications", tags=["Applications"])

class ApplyRequest(BaseModel):
    first_name: str
    last_name: str
    email: str
    headful: bool = True

@router.get("")
def list_applications(db: Session = Depends(get_db)):
    """Lists all active applications and matched statuses."""
    apps = db.query(models.Application).all()
    output = []
    for app in apps:
        output.append({
            "id": app.id,
            "resume_id": app.resume_id,
            "resume_filename": app.resume.filename if app.resume else "Unknown",
            "job_id": app.job_id,
            "job_title": app.job.title if app.job else "Unknown",
            "job_company": app.job.company if app.job else "Unknown",
            "status": app.status,
            "match_score": app.match_score,
            "ats_score": app.ats_score,
            "ats_type": app.ats_type,
            "tailored_resume_path": app.tailored_resume_path,
            "cover_letter": app.cover_letter,
            "applied_at": app.applied_at
        })
    return output

@router.get("/{app_id}")
def get_application(app_id: int, db: Session = Depends(get_db)):
    """Retrieves detailed info about a specific application."""
    app = db.query(models.Application).filter(models.Application.id == app_id).first()
    if not app:
        raise HTTPException(status_code=404, detail="Application not found")
        
    tailored_content = ""
    if app.tailored_resume_path:
        try:
            with open(app.tailored_resume_path, "r", encoding="utf-8") as f:
                tailored_content = f.read()
        except Exception as e:
            tailored_content = f"Error reading file: {e}"
            
    return {
        "id": app.id,
        "resume_id": app.resume_id,
        "resume_raw": app.resume.raw_text if app.resume else "",
        "job_id": app.job_id,
        "job_title": app.job.title if app.job else "",
        "job_company": app.job.company if app.job else "",
        "job_description": app.job.description if app.job else "",
        "status": app.status,
        "match_score": app.match_score,
        "ats_score": app.ats_score,
        "ats_critic_feedback": app.ats_critic_feedback,
        "ats_type": app.ats_type,
        "tailored_resume_path": app.tailored_resume_path,
        "tailored_content": tailored_content,
        "cover_letter": app.cover_letter,
        "applied_at": app.applied_at,
        "logs": app.logs
    }

@router.post("/{app_id}/tailor")
def tailor_application(app_id: int, db: Session = Depends(get_db)):
    """
    1. Triggers resume tailoring and cover letter generation.
    2. Runs the ATS Critic rating.
    3. Executes a corrective loop if score is under 50% (max 3 loops).
    4. Detects ATS type and saves results.
    """
    app = db.query(models.Application).filter(models.Application.id == app_id).first()
    if not app:
        raise HTTPException(status_code=404, detail="Application not found")
        
    resume = app.resume
    job = app.job
    
    if not resume or not job:
        raise HTTPException(status_code=400, detail="Missing linked resume or job details")
        
    try:
        # Detect ATS Type
        ats_name = detect_ats(job.url)
        app.ats_type = ats_name
        
        # Step 1: Initial Resume Tailoring
        logger.info(f"Generating initial resume tailoring for {job.title} at {job.company}...")
        tailored_resume = tailor_resume_for_job(
            resume_text=resume.raw_text,
            job_title=job.title,
            job_company=job.company,
            job_description=job.description
        )
        
        # Step 2: Critic Assessment
        critic_result = evaluate_resume_with_critic(tailored_resume, job.title, job.description)
        ats_score = critic_result.get("ats_score", 0)
        
        # Step 3: Corrective Loop (Up to 2 additional attempts)
        attempts = 1
        max_attempts = 3
        
        while ats_score < 50 and attempts < max_attempts:
            logger.info(f"ATS score {ats_score}% is below threshold. Executing corrective loop attempt {attempts + 1}...")
            
            missing_skills = ", ".join(critic_result.get("missing_keywords", []))
            correction_instruction = (
                f"IMPORTANT: The previous CV draft lacked the following keywords/skills required by the job: {missing_skills}. "
                "Incorporate these keywords naturally and highlight matching experience to satisfy ATS filters."
            )
            
            # Re-tailor using the original CV + correction instructions
            tailored_resume = tailor_resume_for_job(
                resume_text=resume.raw_text + f"\n\n[Correction Notes: {correction_instruction}]",
                job_title=job.title,
                job_company=job.company,
                job_description=job.description
            )
            
            # Re-evaluate
            critic_result = evaluate_resume_with_critic(tailored_resume, job.title, job.description)
            ats_score = critic_result.get("ats_score", 0)
            attempts += 1
            
        # Add metadata on final attempt
        critic_result["attempts_run"] = attempts
        
        # Step 4: Generate Cover Letter
        cover_letter = generate_cover_letter(
            resume_text=resume.raw_text,
            job_title=job.title,
            job_company=job.company,
            job_description=job.description
        )
        
        # Save tailored resume text
        saved_path = save_tailored_resume(resume.id, job.id, tailored_resume)
        
        # Update DB record
        app.tailored_resume_path = saved_path
        app.cover_letter = cover_letter
        app.ats_score = float(ats_score)
        app.ats_critic_feedback = critic_result
        app.status = "tailored"
        db.commit()
        db.refresh(app)
        
    except Exception as e:
        logger.error(f"Tailoring workflow failed: {e}")
        raise HTTPException(status_code=500, detail=f"Tailoring workflow failed: {e}")
        
    return {
        "status": app.status,
        "ats_score": app.ats_score,
        "ats_type": app.ats_type,
        "ats_critic_feedback": app.ats_critic_feedback,
        "tailored_resume_path": app.tailored_resume_path,
        "cover_letter": app.cover_letter
    }

@router.post("/{app_id}/approve")
def approve_application(app_id: int, db: Session = Depends(get_db)):
    """Approves the tailored CV/Cover Letter, prepping it for submission."""
    app = db.query(models.Application).filter(models.Application.id == app_id).first()
    if not app:
        raise HTTPException(status_code=404, detail="Application not found")
        
    if app.status != "tailored":
        raise HTTPException(status_code=400, detail="Application must be tailored before it can be approved")
        
    app.status = "approved"
    db.commit()
    return {"status": app.status}

async def run_apply_automation(
    app_id: int,
    req_data: ApplyRequest,
    db_session: Session
):
    """Background task to execute Playwright apply sequence and write logs."""
    app = db_session.query(models.Application).filter(models.Application.id == app_id).first()
    if not app:
        return
        
    app.logs = "Application submission starting...\n"
    db_session.commit()
    
    resume_file = app.tailored_resume_path if app.tailored_resume_path else ""
    if not resume_file:
        import os
        import uuid
        from backend.app.config import settings
        temp_name = f"resume_original_{uuid.uuid4()}.txt"
        temp_path = os.path.join(settings.RESUMES_PATH, temp_name)
        with open(temp_path, "w", encoding="utf-8") as f:
            f.write(app.resume.raw_text)
        resume_file = temp_path
    # Detect platform from job URL to retrieve cookies
    cookies = None
    job_url_lower = app.job.url.lower() if app.job else ""
    platform = None
    if "naukri.com" in job_url_lower:
        platform = "naukri"
    elif "linkedin.com" in job_url_lower:
        platform = "linkedin"
        
    if platform:
        cred = db_session.query(models.UserCredential).filter(models.UserCredential.platform == platform).first()
        if cred and cred.session_cookies:
            cookies = cred.session_cookies

    import asyncio
    result = await asyncio.to_thread(
        automate_application_flow,
        apply_url=app.job.url,
        first_name=req_data.first_name,
        last_name=req_data.last_name,
        email=req_data.email,
        resume_path=resume_file,
        cover_letter=app.cover_letter or "",
        headful=req_data.headful,
        cookies=cookies
    )
    
    if result["success"]:
        app.status = "applied"
        app.applied_at = datetime.utcnow()
    else:
        app.status = "failed"
        
    app.logs = result.get("logs", "") + (f"\nError: {result['error']}" if "error" in result else "\nCompleted successfully.")
    db_session.commit()

@router.post("/{app_id}/apply")
def apply_application(
    app_id: int, 
    req_data: ApplyRequest, 
    background_tasks: BackgroundTasks, 
    db: Session = Depends(get_db)
):
    """Triggers Playwright to submit the application asynchronously in the background."""
    app = db.query(models.Application).filter(models.Application.id == app_id).first()
    if not app:
        raise HTTPException(status_code=404, detail="Application not found")
        
    background_tasks.add_task(
        run_apply_automation,
        app_id=app_id,
        req_data=req_data,
        db_session=db
    )
    
    app.status = "applying"
    db.commit()
    
    return {"message": "Application automation triggered successfully", "status": app.status}
