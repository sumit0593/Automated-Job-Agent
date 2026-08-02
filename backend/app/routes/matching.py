from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from backend.app.database import get_db
from backend.app import models
from backend.app.services.vectorstore import vector_store
import logging

logger = logging.getLogger("uvicorn.error")
router = APIRouter(prefix="/matching", tags=["Matching"])

from backend.app.services.matching.agentic_rag import agentic_rag

@router.get("/match")
def match_resume_to_jobs(
    resume_id: int = Query(..., description="ID of the resume to match"),
    limit: int = Query(50, description="Max matches to return"),
    min_score: float = Query(50.0, description="Minimum match score threshold (0-100)"),
    db: Session = Depends(get_db)
):
    """
    Executes the Agentic RAG Retrieval & Reranking Pipeline:
    - HyDE & Query Enhancement
    - Hybrid Vector + BM25 Search
    - Self-RAG & Corrective RAG (CRAG) adaptive retries
    - Cross-Encoder Reranking + MMR Deduplication
    - Grounded match breakdown & RAG metrics evaluation
    """
    resume = db.query(models.Resume).filter(models.Resume.id == resume_id).first()
    if not resume:
        raise HTTPException(status_code=404, detail="Resume not found")
        
    rag_result = agentic_rag.run_matching_pipeline(
        resume=resume,
        db=db,
        limit=limit,
        min_score=min_score
    )

    matches = rag_result["matches"]
    
    # Upsert application records in SQLite database
    output = []
    for cand in matches:
        job_id = cand["job_id"]
        match_percentage = cand["match_percentage"]
        app_type = cand.get("application_type", "Unknown")

        app = db.query(models.Application).filter(
            models.Application.resume_id == resume.id,
            models.Application.job_id == job_id
        ).first()

        if not app:
            app = models.Application(
                resume_id=resume.id,
                job_id=job_id,
                status="matched",
                match_score=float(match_percentage),
                application_type=app_type
            )
            db.add(app)
        else:
            app.match_score = float(match_percentage)
            app.application_type = app_type

        db.commit()
        db.refresh(app)

        cand_output = dict(cand)
        cand_output["application_id"] = app.id
        cand_output["status"] = app.status
        output.append(cand_output)

    return {
        "matches": output,
        "pipeline_meta": rag_result.get("pipeline_meta", {})
    }

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

@router.post("/clear")
def clear_matched_applications(db: Session = Depends(get_db)):
    """Wipes all matched application records from database."""
    try:
        deleted = db.query(models.Application).delete()
        db.commit()
        return {"success": True, "deleted_count": deleted}
    except Exception as e:
        logger.error(f"Error clearing applications: {e}")
        return {"success": False, "error": str(e)}
