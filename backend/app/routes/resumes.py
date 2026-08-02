import shutil
from pathlib import Path
from fastapi import APIRouter, Depends, UploadFile, File, HTTPException
from sqlalchemy.orm import Session
from backend.app.database import get_db
from backend.app.config import settings
from backend.app import models
from backend.app.services.parser import extract_text_from_pdf, parse_resume_text_with_llm, extract_links
from backend.app.services.vectorstore import vector_store

router = APIRouter(prefix="/resumes", tags=["Resumes"])

@router.post("/upload")
def upload_resume(file: UploadFile = File(...), db: Session = Depends(get_db)):
    """
    Uploads a resume PDF, extracts text, parses structured attributes,
    saves to DB, and indexes into Qdrant.
    """
    if not file.filename.lower().endswith('.pdf'):
        raise HTTPException(status_code=400, detail="Only PDF files are supported.")
    
    # Generate unique storage filename
    import uuid
    unique_filename = f"{uuid.uuid4()}_{file.filename}"
    file_path = Path(settings.RESUMES_PATH) / unique_filename
    
    # Save PDF locally
    try:
        with file_path.open("wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save file: {e}")
        
    # Extract text and parse metadata
    try:
        raw_text = extract_text_from_pdf(str(file_path))
        if not raw_text:
            # Fallback text if empty
            raw_text = "Empty Resume PDF Document."
            
        parsed_profile = parse_resume_text_with_llm(raw_text)
    except Exception as e:
        # Cleanup file on error
        if file_path.exists():
            file_path.unlink()
        raise HTTPException(status_code=500, detail=f"Error parsing resume content: {e}")
        
    # Extract social URLs
    links = extract_links(raw_text)
    
    # Create DB entry
    db_resume = models.Resume(
        filename=file.filename,
        storage_path=str(file_path),
        raw_text=raw_text,
        parsed_skills=parsed_profile.get("skills", []),
        parsed_experience=parsed_profile.get("experience", 0.0),
        parsed_location=parsed_profile.get("location", "Unknown"),
        linkedin_url=links.get("linkedin"),
        github_url=links.get("github"),
        portfolio_url=links.get("portfolio")
    )
    
    db.add(db_resume)
    db.commit()
    db.refresh(db_resume)

    # Auto-populate candidate UserProfile & AnswerBank using Hybrid RAG Extractor
    try:
        from backend.app.services.matching.resume_rag_extractor import resume_rag_extractor
        extracted_data = resume_rag_extractor.extract_all(raw_text)
        ext_prof = extracted_data.get("profile", {})
        ext_ans = extracted_data.get("answers", {})

        user_prof = db.query(models.UserProfile).first()
        if not user_prof:
            user_prof = models.UserProfile()
            db.add(user_prof)

        for f_key in ["name", "email", "phone", "country_code", "pan_number", "date_of_birth",
                      "last_working_day", "experience_years", "current_ctc", "expected_ctc",
                      "notice_period", "current_location", "preferred_locations", "skills",
                      "linkedin_url", "github_url", "portfolio_url", "work_authorization",
                      "willing_to_relocate", "remote_preference"]:
            if ext_prof.get(f_key) is not None:
                setattr(user_prof, f_key, ext_prof[f_key])

        db.commit()

        # Update AnswerBank with grounded answers
        for q_key, answer in ext_ans.items():
            if answer:
                existing = db.query(models.AnswerBank).filter(models.AnswerBank.question_key == q_key).first()
                if existing:
                    existing.stored_answer = answer
                else:
                    db.add(models.AnswerBank(question_key=q_key, question_pattern=q_key, stored_answer=answer, category="rag_extracted"))
        db.commit()
        import logging
        logging.getLogger("uvicorn.error").info(f"Hybrid RAG Extractor successfully populated UserProfile & AnswerBank for {user_prof.name}")
    except Exception as prof_err:
        import logging
        logging.getLogger("uvicorn.error").warning(f"Could not run RAG extraction on upload: {prof_err}")
    
    # Index in Vector Store
    try:
        vector_store.index_resume(
            resume_id=db_resume.id,
            raw_text=raw_text,
            skills=parsed_profile.get("skills", [])
        )
    except Exception as e:
        # We don't fail the whole request if indexing fails (e.g. model downloads), but log it
        import logging
        logging.getLogger("uvicorn.error").error(f"Vector indexing failed for resume {db_resume.id}: {e}")
        
    return db_resume

@router.get("")
def list_resumes(db: Session = Depends(get_db)):
    """Lists all uploaded resumes."""
    return db.query(models.Resume).all()

@router.get("/{resume_id}")
def get_resume(resume_id: int, db: Session = Depends(get_db)):
    """Retrieves details of a specific resume."""
    resume = db.query(models.Resume).filter(models.Resume.id == resume_id).first()
    if not resume:
        raise HTTPException(status_code=404, detail="Resume not found")
    return resume

@router.delete("/{resume_id}")
def delete_resume(resume_id: int, db: Session = Depends(get_db)):
    """Deletes a resume from DB and Qdrant."""
    resume = db.query(models.Resume).filter(models.Resume.id == resume_id).first()
    if not resume:
        raise HTTPException(status_code=404, detail="Resume not found")
        
    # Delete from Qdrant first, safely
    try:
        from qdrant_client.models import Filter, FieldCondition, MatchValue
        if vector_store.client.collection_exists(settings.QDRANT_COLLECTION_RESUMES):
            vector_store.client.delete(
                collection_name=settings.QDRANT_COLLECTION_RESUMES,
                points_selector=Filter(
                    must=[
                        FieldCondition(
                            key="id",
                            match=MatchValue(value=resume_id)
                        )
                    ]
                )
            )
    except Exception as q_err:
        import logging
        logging.getLogger("uvicorn.error").warning(f"Failed to delete resume {resume_id} from Qdrant: {q_err}")

    # Delete physical file from storage
    if resume.storage_path:
        try:
            p_file = Path(resume.storage_path)
            if p_file.exists():
                p_file.unlink()
        except Exception as f_err:
            import logging
            logging.getLogger("uvicorn.error").warning(f"Failed to delete physical resume file: {f_err}")

    try:
        db.delete(resume)
        db.commit()
    except Exception as db_err:
        db.rollback()
        import logging
        logging.getLogger("uvicorn.error").error(f"Failed to delete resume {resume_id} from database: {db_err}")
        raise HTTPException(status_code=500, detail=f"Database deletion failed: {db_err}")
        
    return {"message": "Resume deleted successfully"}

@router.post("/{resume_id}/extract-profile")
def extract_profile_from_resume_endpoint(resume_id: int, db: Session = Depends(get_db)):
    """Re-runs Hybrid RAG Extraction over the selected resume to populate UserProfile and AnswerBank."""
    resume = db.query(models.Resume).filter(models.Resume.id == resume_id).first()
    if not resume or not resume.raw_text:
        raise HTTPException(status_code=404, detail="Resume not found or contains no raw text")

    from backend.app.services.matching.resume_rag_extractor import resume_rag_extractor
    extracted_data = resume_rag_extractor.extract_all(resume.raw_text)
    ext_prof = extracted_data.get("profile", {})
    ext_ans = extracted_data.get("answers", {})

    user_prof = db.query(models.UserProfile).first()
    if not user_prof:
        user_prof = models.UserProfile()
        db.add(user_prof)

    for field in ["name", "email", "phone", "country_code", "pan_number", "date_of_birth",
                  "last_working_day", "experience_years", "current_ctc", "expected_ctc",
                  "notice_period", "current_location", "preferred_locations", "skills",
                  "linkedin_url", "github_url", "portfolio_url", "work_authorization",
                  "willing_to_relocate", "remote_preference"]:
        if ext_prof.get(field) is not None:
            setattr(user_prof, field, ext_prof[field])

    db.commit()
    db.refresh(user_prof)

    # Update AnswerBank
    for q_key, answer in ext_ans.items():
        if answer:
            existing = db.query(models.AnswerBank).filter(models.AnswerBank.question_key == q_key).first()
            if existing:
                existing.stored_answer = answer
            else:
                db.add(models.AnswerBank(question_key=q_key, question_pattern=q_key, stored_answer=answer, category="rag_extracted"))
    db.commit()

    return {
        "message": f"Successfully extracted profile & answer bank for {user_prof.name or 'Candidate'}",
        "profile": user_prof,
        "answers": ext_ans
    }
