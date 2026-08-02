from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import Optional
from backend.app.database import get_db
from backend.app import models
from backend.app.services.scraper import search_jobs_on_web, discover_jobs_via_platform
from backend.app.services.vectorstore import vector_store
import logging

logger = logging.getLogger("uvicorn.error")
router = APIRouter(prefix="/jobs", tags=["Jobs"])

@router.post("/scrape")
async def scrape_jobs(
    query: str = Query(..., description="Company name (e.g. stripe) or job keyword (e.g. python)"),
    location: str = Query("", description="City or region filter"),
    platform: Optional[str] = Query(None, description="Optional platform: 'linkedin' or 'naukri'"),
    max_jobs: int = Query(100, description="Maximum number of jobs to fetch (default: 100)"),
    db: Session = Depends(get_db)
):
    """
    Triggers job scraper. If a platform is specified, uses persistent browser profile 
    with saved session to crawl. Otherwise, queries Greenhouse/Lever public boards directly.
    """
    scraped_list = []
    
    if platform:
        plat_name = platform.lower().strip()
        AUTHENTICATED_PLATFORMS = ["naukri", "linkedin", "wellfound", "workday"]

        if plat_name in AUTHENTICATED_PLATFORMS:
            cred = db.query(models.UserCredential).filter(models.UserCredential.platform == plat_name).first()
            if not cred or not cred.session_cookies:
                raise HTTPException(
                    status_code=400, 
                    detail=f"Active login session for '{platform}' not found. Please connect your {platform.capitalize()} account under Candidate Profile & Accounts (Tab 1) first."
                )

            import asyncio
            scraped_list = await asyncio.to_thread(
                discover_jobs_via_platform,
                platform=plat_name,
                cookies=cred.session_cookies,
                keyword=query,
                location=location,
                max_jobs=max_jobs,
            )
        else:
            # Public ATS / Public Web Board (No account login needed)
            scraped_list = search_jobs_on_web(query, location)
    else:
        scraped_list = search_jobs_on_web(query, location)
        
    if not scraped_list:
        return {
            "message": f"No job listings found for '{query}' on " + (platform if platform else "Greenhouse/Lever API"),
            "jobs": []
        }
    
    saved_jobs = []
    for item in scraped_list:
        # Check if job already exists in DB by url to avoid duplicates
        existing_job = db.query(models.Job).filter(models.Job.url == item["url"]).first()
        if existing_job:
            saved_jobs.append(existing_job)
            continue
            
        db_job = models.Job(
            title=item["title"],
            company=item["company"],
            description=item["description"],
            url=item["url"],
            location=item["location"],
            skills_required=item["skills_required"],
            experience_required=item.get("experience_required", 2.0)
        )
        
        db.add(db_job)
        db.commit()
        db.refresh(db_job)
        
        # Index in Qdrant
        try:
            vector_store.index_job(
                job_id=db_job.id,
                title=db_job.title,
                company=db_job.company,
                description=db_job.description,
                skills=db_job.skills_required
            )
        except Exception as e:
            logger.error(f"Vector indexing failed for job {db_job.id}: {e}")
            
        saved_jobs.append(db_job)
        
    return {
        "message": f"Successfully processed {len(scraped_list)} jobs",
        "jobs": saved_jobs
    }

@router.get("")
def list_jobs(db: Session = Depends(get_db)):
    """Lists all crawled jobs."""
    return db.query(models.Job).all()

@router.get("/{job_id}")
def get_job(job_id: int, db: Session = Depends(get_db)):
    """Retrieves a specific job."""
    job = db.query(models.Job).filter(models.Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job

@router.post("/clear")
def clear_database(db: Session = Depends(get_db)):
    """
    Clears all database tables (Jobs, Resumes, Applications),
    deletes physical files from storage, and resets Qdrant collections.
    """
    try:
        # Delete physical files from storage
        from pathlib import Path
        from backend.app.config import settings
        
        def clean_directory(dir_path: str):
            p = Path(dir_path)
            if p.exists() and p.is_dir():
                for item in p.iterdir():
                    if item.is_file():
                        try:
                            item.unlink()
                        except Exception as file_err:
                            logger.warning(f"Failed to delete storage file {item}: {file_err}")
                            
        clean_directory(settings.RESUMES_PATH)
        clean_directory(settings.TAILORED_RESUMES_PATH)

        # Delete database records
        db.query(models.Application).delete()
        db.query(models.MatchResultCache).delete()
        db.query(models.ScheduledTask).delete()
        db.query(models.Job).delete()
        db.query(models.Resume).delete()
        db.commit()
        
        # Reset Qdrant collections
        from qdrant_client.models import Distance, VectorParams
        from backend.app.config import settings
        
        for col_name in [settings.QDRANT_COLLECTION_JOBS, settings.QDRANT_COLLECTION_RESUMES]:
            if vector_store.client.collection_exists(col_name):
                vector_store.client.delete_collection(col_name)
                vector_store.client.create_collection(
                    collection_name=col_name,
                    vectors_config=VectorParams(size=1024, distance=Distance.COSINE)
                )
        return {"message": "Database and vector indexes cleared successfully!"}
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to clear database: {e}")
        raise HTTPException(status_code=500, detail=f"Database clear failed: {e}")
