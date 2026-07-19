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
