import time
import hashlib
import logging
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session

from backend.app import models
from backend.app.services.vectorstore import vector_store
from backend.app.services.matching.normalizer import expand_skills, normalize_skill, categorize_seniority
from backend.app.services.matching.query_enhancer import generate_hyde_doc, decompose_query, classify_query_intent
from backend.app.services.matching.reranker import (
    compute_skill_overlap_score,
    compute_experience_match_score,
    compute_location_match_score,
    apply_mmr
)
from backend.app.services.matching.explainer import generate_match_explanation
from backend.app.services.matching.evaluator import compute_rag_metrics

logger = logging.getLogger("uvicorn.error")

from backend.app.services.cache_service import enterprise_cache

ALGORITHM_VERSION = "agentic_rag_v1.2"

class AgenticRAGEngine:
    """
    Production Agentic RAG Pipeline for Job Matching.
    Integrates Sub-Millisecond Redis Hot Cache, Database Cold Cache,
    Decoupled Embedding Hashes, SETNX Stampede Lock Protection,
    HyDE, Cross-Encoder Reranking, MMR Deduplication, and Grounded Explanations.
    """
    def __init__(self, confidence_threshold: float = 60.0, max_retries: int = 3):
        self.confidence_threshold = confidence_threshold
        self.max_retries = max_retries

    def run_matching_pipeline(
        self,
        resume: models.Resume,
        db: Session,
        limit: int = 20,
        min_score: float = 50.0
    ) -> Dict[str, Any]:
        start_time = time.time()
        
        resume_id = resume.id
        raw_text = resume.raw_text or "Empty Resume"
        skills = resume.parsed_skills or []
        experience = resume.parsed_experience or 0.0
        location = resume.parsed_location or "Unknown"

        # Decoupled Hashing
        resume_hash = enterprise_cache.compute_resume_hash(raw_text)
        resume_emb_hash = enterprise_cache.compute_resume_embedding_hash(raw_text, skills, experience)

        logger.info(f"AgenticRAG: Initiating matching pipeline for Resume #{resume_id} (min_score: {min_score}%)...")
        
        # 1. Hierarchical Hot/Cold Cache Lookup
        all_db_jobs = db.query(models.Job).all()
        cached_matches_map = {}
        uncached_job_ids = set()

        for job in all_db_jobs:
            j_hash = enterprise_cache.compute_job_hash(job.title, job.company, job.description)
            
            # Check Tier 1 (Redis Hot) & Tier 2 (DB Cold)
            match_payload, hit_type = enterprise_cache.get_match_result(
                resume_id=resume_id,
                job_id=job.id,
                resume_hash=resume_hash,
                resume_emb_hash=resume_emb_hash,
                job_hash=j_hash,
                db=db
            )

            if hit_type in ["redis_hot", "db_cold"]:
                cached_matches_map[job.id] = (job, match_payload)
            else:
                uncached_job_ids.add(job.id)

        cache_hit_count = len(cached_matches_map)
        logger.info(f"AgenticRAG Cache Status: {cache_hit_count} HIT(s), {len(uncached_job_ids)} MISS(es) out of {len(all_db_jobs)} total DB jobs.")

        newly_computed_matches = []
        query_intent = "Direct Semantic Search"
        hyde_doc = ""
        retrieval_attempts = 0
        confidence = 100.0 if cache_hit_count > 0 else 0.0

        # 2. Run Heavy AI Matching ONLY for Uncached Jobs
        if uncached_job_ids:
            logger.info(f"AgenticRAG: Executing AI RAG pipeline for {len(uncached_job_ids)} uncached job(s)...")
            query_intent = classify_query_intent(raw_text)
            hyde_doc = generate_hyde_doc(raw_text, skills)
            query_branches = decompose_query(raw_text, skills)
            
            retrieved_candidates = []
            for attempt in range(1, self.max_retries + 1):
                retrieval_attempts = attempt
                if attempt == 1:
                    candidates = vector_store.search_similar_jobs(resume_text=raw_text, resume_skills=skills, limit=100)
                elif attempt == 2:
                    candidates = vector_store.search_similar_jobs(resume_text=hyde_doc, resume_skills=skills, limit=100)
                else:
                    cand_map = {}
                    for q_branch in query_branches:
                        q_res = vector_store.search_similar_jobs(resume_text=q_branch, resume_skills=skills, limit=100)
                        for item in q_res:
                            cand_map[item["job_id"]] = item
                    candidates = list(cand_map.values())

                if candidates:
                    top_scores = [c.get("hybrid_score", 0.5) * 100.0 for c in candidates[:5]]
                    confidence = sum(top_scores) / len(top_scores)
                else:
                    confidence = 0.0

                if confidence >= self.confidence_threshold or attempt == self.max_retries:
                    retrieved_candidates = candidates
                    break

            # Filter candidates to only uncached jobs
            uncached_candidates = [c for c in retrieved_candidates if c["job_id"] in uncached_job_ids]
            
            # Fallback if vector store yields no uncached candidates
            if not uncached_candidates and uncached_job_ids:
                for j_id in uncached_job_ids:
                    uncached_candidates.append({
                        "job_id": j_id,
                        "dense_score": 0.5,
                        "overlap_score": 0.5,
                        "hybrid_score": 0.5
                    })

            # Compute Sub-Scores & BGE Reranking for uncached jobs
            candidates_to_rerank = []
            job_map = {}
            for cand in uncached_candidates:
                job = db.query(models.Job).filter(models.Job.id == cand["job_id"]).first()
                if not job:
                    continue

                job_map[job.id] = job
                job_skills = job.skills_required or []
                job_exp = job.experience_required or 0.0
                
                skill_score = compute_skill_overlap_score(skills, job_skills)
                exp_score = compute_experience_match_score(experience, job_exp)
                loc_score = compute_location_match_score(location, job.location or "")
                semantic_score = round(cand.get("dense_score", 0.5) * 100.0, 1)

                combined_score = (
                    (semantic_score * 0.40) +
                    (skill_score * 0.35) +
                    (exp_score * 0.15) +
                    (loc_score * 0.10)
                )

                candidates_to_rerank.append({
                    "job_id": job.id,
                    "title": job.title,
                    "company": job.company,
                    "description": job.description,
                    "location": job.location or "Unknown",
                    "skills_required": job_skills,
                    "experience_required": job_exp,
                    "dense_score": cand.get("dense_score", 0.5),
                    "sub_scores": {
                        "overall_score": combined_score,
                        "skill_score": skill_score,
                        "exp_score": exp_score,
                        "loc_score": loc_score,
                        "semantic_score": semantic_score
                    },
                    "combined_score": combined_score
                })

            if candidates_to_rerank:
                reranked = vector_store.rerank_jobs(
                    resume_text=raw_text,
                    jobs=candidates_to_rerank,
                    limit=len(candidates_to_rerank)
                )
                for item in reranked:
                    match_pct = float(item.get("match_percentage", 75))
                    sub = item["sub_scores"]
                    final_score = (
                        (match_pct * 0.45) +
                        (sub["semantic_score"] * 0.25) +
                        (sub["skill_score"] * 0.20) +
                        (sub["exp_score"] * 0.10)
                    )
                    sub["overall_score"] = round(min(100.0, max(15.0, final_score)), 1)
                    item["combined_score"] = sub["overall_score"]

                    # Store newly computed match in Hot & Cold Caches
                    job_obj = job_map[item["job_id"]]
                    j_hash = enterprise_cache.compute_job_hash(job_obj.title, job_obj.company, job_obj.description)
                    explanation = generate_match_explanation(
                        candidate_skills=skills,
                        candidate_exp=experience,
                        candidate_loc=location,
                        job_title=job_obj.title,
                        job_company=job_obj.company,
                        job_description=job_obj.description,
                        job_skills=job_obj.skills_required or [],
                        sub_scores=sub
                    )

                    match_payload = {
                        "match_percentage": sub["overall_score"],
                        "skill_score": sub["skill_score"],
                        "exp_score": sub["exp_score"],
                        "semantic_score": sub["semantic_score"],
                        "loc_score": sub["loc_score"],
                        "matching_skills": explanation["matching_skills"],
                        "missing_skills": explanation["missing_skills"],
                        "why_selected": explanation["why_selected"],
                        "resume_improvements": explanation["resume_improvements"],
                        "pipeline_meta": {"confidence": confidence}
                    }

                    # Enterprise Cache Save (Redis Hot + DB Cold)
                    enterprise_cache.set_match_result(
                        resume_id=resume_id,
                        job_id=job_obj.id,
                        resume_hash=resume_hash,
                        resume_emb_hash=resume_emb_hash,
                        job_hash=j_hash,
                        payload=match_payload,
                        db=db
                    )

                    cached_matches_map[job_obj.id] = (job_obj, match_payload)

        # 3. Assemble Final Matches from Hierarchical Hot/Cold Cache
        final_matches = []
        scores_for_eval = []

        for job_id, (job_obj, cache_payload) in cached_matches_map.items():
            match_score = cache_payload["match_percentage"]
            if match_score < min_score:
                continue

            app_type = "Unknown"
            url_l = (job_obj.url or "").lower()
            ats_domains = ["greenhouse.io", "lever.co", "myworkdayjobs.com", "ashbyhq.com", "icims.com", "smartrecruiters.com", "oraclecloud.com", "taleo.net", "bamboohr.com"]
            if any(d in url_l for d in ats_domains):
                app_type = "External Website"
            elif "linkedin.com" in url_l or "naukri.com" in url_l:
                app_type = "Easy Apply"
            else:
                app_type = "External Website"

            created_str = ""
            if hasattr(job_obj, "created_at") and job_obj.created_at:
                try:
                    created_str = job_obj.created_at.strftime("%Y-%m-%d")
                except Exception:
                    created_str = str(job_obj.created_at)

            # Ensure Application record exists in DB
            existing_app = db.query(models.Application).filter(
                models.Application.resume_id == resume_id,
                models.Application.job_id == job_obj.id
            ).first()

            if not existing_app:
                new_app = models.Application(
                    resume_id=resume_id,
                    job_id=job_obj.id,
                    status="matched",
                    match_score=match_score,
                    ats_type=app_type,
                    application_type=app_type
                )
                db.add(new_app)
                db.commit()
                db.refresh(new_app)
                app_id = new_app.id
                app_status = new_app.status
            else:
                app_id = existing_app.id
                app_status = existing_app.status

            scores_for_eval.append(match_score)

            final_matches.append({
                "job_id": job_obj.id,
                "application_id": app_id,
                "status": app_status,
                "title": job_obj.title,
                "company": job_obj.company,
                "location": job_obj.location or "Remote",
                "url": job_obj.url or "",
                "created_at": created_str,
                "description": job_obj.description or "",
                "skills_required": job_obj.skills_required or [],
                "match_percentage": int(round(match_score)),
                "application_type": app_type,
                "sub_scores": {
                    "skill_match_pct": int(round(cache_payload.get("skill_score", 0))),
                    "experience_match_pct": int(round(cache_payload.get("exp_score", 0))),
                    "semantic_similarity_pct": int(round(cache_payload.get("semantic_score", 0))),
                    "location_match_pct": int(round(cache_payload.get("loc_score", 0)))
                },
                "matching_skills": cache_payload.get("matching_skills", []),
                "missing_skills": cache_payload.get("missing_skills", []),
                "why_selected": cache_payload.get("why_selected", ""),
                "resume_improvements": cache_payload.get("resume_improvements", "")
            })

        # Sort matches by match percentage descending
        final_matches.sort(key=lambda x: x["match_percentage"], reverse=True)

        # 4. Maximum Marginal Relevance (MMR) Deduplication
        deduplicated_results = apply_mmr(final_matches, lambda_param=0.75, limit=limit)

        latency_ms = (time.time() - start_time) * 1000.0
        rag_metrics = compute_rag_metrics(
            retrieved_scores=scores_for_eval,
            latency_ms=latency_ms,
            retrieval_attempts=max(1, retrieval_attempts)
        )

        cache_metrics = enterprise_cache.get_metrics_summary()

        logger.info(
            f"AgenticRAG: Cache-First Matching finished in {latency_ms:.1f}ms "
            f"({cache_hit_count} cached, {len(uncached_job_ids)} new). Returned {len(deduplicated_results)} ranked matches."
        )

        return {
            "matches": deduplicated_results,
            "pipeline_meta": {
                "intent": query_intent,
                "hyde_generated": bool(hyde_doc),
                "retrieval_attempts": retrieval_attempts,
                "confidence_score": round(confidence, 1),
                "cache_hit_count": cache_hit_count,
                "newly_computed_count": len(uncached_job_ids),
                "cache_metrics": cache_metrics,
                "rag_metrics": rag_metrics
            }
        }

# Global engine instance
agentic_rag = AgenticRAGEngine()

