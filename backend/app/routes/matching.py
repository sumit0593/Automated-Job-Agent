from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from backend.app.database import get_db
from backend.app import models
from backend.app.services.vectorstore import vector_store
import logging

logger = logging.getLogger("uvicorn.error")
router = APIRouter(prefix="/matching", tags=["Matching"])

@router.get("/match")
def match_resume_to_jobs(
    resume_id: int = Query(..., description="ID of the resume to match"),
    limit: int = Query(10, description="Max matches to return"),
    db: Session = Depends(get_db)
):
    """
    Retrieves similar jobs for a resume using hybrid retrieval (Qdrant) and
    runs cross-encoder reranking (BGE-Reranker-Large) for top results.
    Creates or updates Application matching entries in the DB.
    """
    resume = db.query(models.Resume).filter(models.Resume.id == resume_id).first()
    if not resume:
        raise HTTPException(status_code=404, detail="Resume not found")
        
    # 1. Run Hybrid Search in Qdrant
    try:
        # Get list of top jobs from Qdrant sorted by hybrid score
        qdrant_candidates = vector_store.search_similar_jobs(
            resume_text=resume.raw_text,
            resume_skills=resume.parsed_skills or [],
            limit=20
        )
    except Exception as e:
        logger.error(f"Qdrant retrieval error: {e}")
        # DB-based fallback retrieval if Qdrant isn't fully ready
        db_jobs = db.query(models.Job).all()
        qdrant_candidates = []
        for j in db_jobs:
            qdrant_candidates.append({
                "job_id": j.id,
                "title": j.title,
                "company": j.company,
                "dense_score": 0.5,
                "overlap_score": 0.5,
                "hybrid_score": 0.5
            })

    if not qdrant_candidates:
        return {"matches": []}
        
    # 2. Fetch full descriptions from database to prepare for reranking
    candidates_to_rerank = []
    job_map = {}
    for cand in qdrant_candidates:
        job = db.query(models.Job).filter(models.Job.id == cand["job_id"]).first()
        if job:
            job_map[job.id] = job
            candidates_to_rerank.append({
                "job_id": job.id,
                "title": job.title,
                "company": job.company,
                "description": job.description,
                "dense_score": cand["dense_score"],
                "overlap_score": cand["overlap_score"],
                "hybrid_score": cand["hybrid_score"]
            })
            
    # 3. Apply Cross-Encoder Reranking
    reranked_results = vector_store.rerank_jobs(
        resume_text=resume.raw_text,
        jobs=candidates_to_rerank,
        limit=limit
    )
    
    # 4. Upsert matches in the Applications database table
    output = []
    for cand in reranked_results:
        job_id = cand["job_id"]
        job_obj = job_map[job_id]
        match_percentage = cand["match_percentage"]
        
        # Check if Application already exists
        app = db.query(models.Application).filter(
            models.Application.resume_id == resume.id,
            models.Application.job_id == job_id
        ).first()
        
        if not app:
            # Create a new "matched" entry
            app = models.Application(
                resume_id=resume.id,
                job_id=job_id,
                status="matched",
                match_score=float(match_percentage)
            )
            db.add(app)
        else:
            # Update match score
            app.match_score = float(match_percentage)
            
        db.commit()
        db.refresh(app)
        
        output.append({
            "application_id": app.id,
            "job_id": job_id,
            "title": job_obj.title,
            "company": job_obj.company,
            "location": job_obj.location,
            "match_percentage": match_percentage,
            "status": app.status
        })
        
    return {"matches": output}

@router.get("/debug")
def debug_qdrant(db: Session = Depends(get_db)):
    from backend.app.config import settings
    try:
        jobs_count = db.query(models.Job).count()
        resumes_count = db.query(models.Resume).count()
        
        jobs_collection_exists = vector_store.client.collection_exists(settings.QDRANT_COLLECTION_JOBS)
        resumes_collection_exists = vector_store.client.collection_exists(settings.QDRANT_COLLECTION_RESUMES)
        
        jobs_points = 0
        if jobs_collection_exists:
            jobs_points = vector_store.client.get_collection(settings.QDRANT_COLLECTION_JOBS).points_count
            
        resumes_points = 0
        if resumes_collection_exists:
            resumes_points = vector_store.client.get_collection(settings.QDRANT_COLLECTION_RESUMES).points_count
            
        points_info = []
        raw_search_count = 0
        raw_search_samples = []
        search_error = None
        qdrant_cands = []
        db_lookups = []
        reranked = []
        
        if jobs_collection_exists and jobs_points > 0:
            scroll_results = vector_store.client.scroll(
                collection_name=settings.QDRANT_COLLECTION_JOBS,
                limit=10,
                with_payload=True,
                with_vectors=False
            )[0]
            points_info = [
                {
                    "id": p.id,
                    "payload": p.payload
                }
                for p in scroll_results
            ]
            
            # Run raw search check
            if resumes_count > 0:
                try:
                    resume = db.query(models.Resume).first()
                    
                    # 1. Run search_similar_jobs
                    qdrant_cands = vector_store.search_similar_jobs(
                        resume_text=resume.raw_text,
                        resume_skills=resume.parsed_skills or [],
                        limit=20
                    )
                    
                    # 2. Lookup in SQLite
                    candidates_to_rerank = []
                    for cand in qdrant_cands:
                        job = db.query(models.Job).filter(models.Job.id == cand["job_id"]).first()
                        db_lookups.append({
                            "job_id": cand["job_id"],
                            "found_in_db": job is not None
                        })
                        if job:
                            candidates_to_rerank.append({
                                "job_id": job.id,
                                "title": job.title,
                                "company": job.company,
                                "description": job.description,
                                "dense_score": cand["dense_score"],
                                "overlap_score": cand["overlap_score"],
                                "hybrid_score": cand["hybrid_score"]
                            })
                            
                    # 3. Rerank
                    reranked = vector_store.rerank_jobs(
                        resume_text=resume.raw_text,
                        jobs=candidates_to_rerank,
                        limit=10
                    )
                except Exception as ex:
                    search_error = str(ex)
            
        return {
            "sqlite": {
                "jobs": jobs_count,
                "resumes": resumes_count
            },
            "qdrant": {
                "jobs_collection_exists": jobs_collection_exists,
                "jobs_points": jobs_points,
                "resumes_collection_exists": resumes_collection_exists,
                "resumes_points": resumes_points
            },
            "trace": {
                "qdrant_candidates": qdrant_cands,
                "db_lookups": db_lookups,
                "candidates_to_rerank_count": len(db_lookups) - sum(1 for x in db_lookups if not x["found_in_db"]),
                "reranked": reranked,
                "error": search_error
            },
            "jobs_points_sample": points_info
        }
    except Exception as e:
        return {"error": str(e)}
