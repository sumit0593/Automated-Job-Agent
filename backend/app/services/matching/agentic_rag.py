import time
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

class AgenticRAGEngine:
    """
    Production Agentic RAG Pipeline for Job Matching.
    Integrates HyDE, Hybrid Search, Self-RAG/CRAG Corrective Loops,
    Cross-Encoder Reranking, MMR Deduplication, and Grounded Explanations.
    """
    def __init__(self, confidence_threshold: float = 60.0, max_retries: int = 3):
        self.confidence_threshold = confidence_threshold
        self.max_retries = max_retries

    def run_matching_pipeline(
        self,
        resume: models.Resume,
        db: Session,
        limit: int = 10,
        min_score: float = 50.0
    ) -> Dict[str, Any]:
        start_time = time.time()
        
        resume_id = resume.id
        raw_text = resume.raw_text or "Empty Resume"
        skills = resume.parsed_skills or []
        experience = resume.parsed_experience or 0.0
        location = resume.parsed_location or "Unknown"

        logger.info(f"AgenticRAG: Initiating matching pipeline for Resume {resume_id} (min_score: {min_score}%)...")
        
        # 1. LLM Query Enhancement & Intent Classification
        query_intent = classify_query_intent(raw_text)
        hyde_doc = generate_hyde_doc(raw_text, skills)
        query_branches = decompose_query(raw_text, skills)
        
        # 2. Corrective RAG (CRAG) Retrieval Loop
        retrieved_candidates = []
        retrieval_attempts = 0
        confidence = 0.0

        for attempt in range(1, self.max_retries + 1):
            retrieval_attempts = attempt
            logger.info(f"AgenticRAG: Executing Retrieval Attempt {attempt}/{self.max_retries}...")
            
            if attempt == 1:
                # Primary Dense + Hybrid Search using raw resume + skills
                candidates = vector_store.search_similar_jobs(
                    resume_text=raw_text,
                    resume_skills=skills,
                    limit=100
                )
            elif attempt == 2:
                # Corrective Retry 1: HyDE Hypothetical Job Description Search
                logger.info("CRAG: Confidence low on Attempt 1. Retrying with HyDE Query...")
                candidates = vector_store.search_similar_jobs(
                    resume_text=hyde_doc,
                    resume_skills=skills,
                    limit=100
                )
            else:
                # Corrective Retry 2: Multi-query ensemble search
                logger.info("CRAG: Retrying with Multi-query branch ensemble...")
                cand_map = {}
                for q_branch in query_branches:
                    q_res = vector_store.search_similar_jobs(
                        resume_text=q_branch,
                        resume_skills=skills,
                        limit=100
                    )
                    for item in q_res:
                        cand_map[item["job_id"]] = item
                candidates = list(cand_map.values())

            # Evaluate confidence of retrieved candidate pool
            if candidates:
                top_scores = [c.get("hybrid_score", 0.5) * 100.0 for c in candidates[:5]]
                confidence = sum(top_scores) / len(top_scores)
            else:
                confidence = 0.0

            logger.info(f"AgenticRAG Attempt {attempt}: Retrieval confidence score = {confidence:.1f}%")
            
            if confidence >= self.confidence_threshold or attempt == self.max_retries:
                retrieved_candidates = candidates
                break

        # Fallback to database jobs if vector store yields no points
        if not retrieved_candidates:
            logger.warning("AgenticRAG: Vector store empty or unreachable. Fetching candidates from SQLite DB.")
            db_jobs = db.query(models.Job).all()
            for j in db_jobs:
                retrieved_candidates.append({
                    "job_id": j.id,
                    "title": j.title,
                    "company": j.company,
                    "dense_score": 0.5,
                    "overlap_score": 0.5,
                    "hybrid_score": 0.5
                })

        # 3. Fetch Full Descriptions & Compute Structured Sub-Scores
        candidates_to_rerank = []
        job_map = {}
        for cand in retrieved_candidates:
            job = db.query(models.Job).filter(models.Job.id == cand["job_id"]).first()
            if not job:
                continue

            job_map[job.id] = job
            job_skills = job.skills_required or []
            job_exp = job.experience_required or 0.0
            
            # Compute granular sub-scores
            skill_score = compute_skill_overlap_score(skills, job_skills)
            exp_score = compute_experience_match_score(experience, job_exp)
            loc_score = compute_location_match_score(location, job.location or "")
            semantic_score = round(cand.get("dense_score", 0.5) * 100.0, 1)

            # Combined weighted score before Cross-Encoder
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
                "overlap_score": cand.get("overlap_score", 0.5),
                "hybrid_score": cand.get("hybrid_score", 0.5),
                "sub_scores": {
                    "overall_score": combined_score,
                    "skill_score": skill_score,
                    "exp_score": exp_score,
                    "loc_score": loc_score,
                    "semantic_score": semantic_score
                },
                "combined_score": combined_score
            })

        # 4. Cross-Encoder Reranking
        logger.info(f"AgenticRAG: Reranking {len(candidates_to_rerank)} candidates with BGE Cross-Encoder...")
        reranked_results = vector_store.rerank_jobs(
            resume_text=raw_text,
            jobs=candidates_to_rerank,
            limit=len(candidates_to_rerank)
        )

        # Update combined score with rerank probability and sub-scores
        for item in reranked_results:
            match_pct = float(item.get("match_percentage", 75))
            sub = item["sub_scores"]
            
            # Dynamic weighted score combining Cross-Encoder, Semantic Cosine, Skill Match, and Experience
            final_score = (
                (match_pct * 0.45) +
                (sub["semantic_score"] * 0.25) +
                (sub["skill_score"] * 0.20) +
                (sub["exp_score"] * 0.10)
            )
            sub["overall_score"] = round(min(100.0, max(15.0, final_score)), 1)
            item["combined_score"] = sub["overall_score"]

        # Sort candidate pool by final combined score
        reranked_results.sort(key=lambda x: x["combined_score"], reverse=True)

        # Filter results strictly by min_score threshold
        filtered_results = [r for r in reranked_results if r["combined_score"] >= min_score]

        # 5. Maximum Marginal Relevance (MMR) Deduplication
        deduplicated_results = apply_mmr(filtered_results, lambda_param=0.75, limit=limit)

        # 6. Generate Grounded Match Explanations
        final_matches = []
        scores_for_eval = []

        for cand in deduplicated_results:
            job_obj = job_map[cand["job_id"]]
            sub = cand["sub_scores"]

            # Determine application type
            app_type = "Unknown"
            url_l = (job_obj.url or "").lower()
            ats_domains = ["greenhouse.io", "lever.co", "myworkdayjobs.com", "ashbyhq.com", "icims.com", "smartrecruiters.com", "oraclecloud.com", "taleo.net", "bamboohr.com"]
            if any(d in url_l for d in ats_domains):
                app_type = "External Website"
            elif "linkedin.com" in url_l or "naukri.com" in url_l:
                app_type = "Easy Apply"
            else:
                app_type = "External Website"

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

            scores_for_eval.append(sub["overall_score"])

            # Formatted created date
            created_str = ""
            if hasattr(job_obj, "created_at") and job_obj.created_at:
                try:
                    created_str = job_obj.created_at.strftime("%Y-%m-%d")
                except Exception:
                    created_str = str(job_obj.created_at)

            final_matches.append({
                "job_id": cand["job_id"],
                "title": job_obj.title,
                "company": job_obj.company,
                "location": job_obj.location or "Remote",
                "url": job_obj.url or "",
                "created_at": created_str,
                "description": job_obj.description or "",
                "skills_required": job_obj.skills_required or [],
                "match_percentage": int(sub["overall_score"]),
                "application_type": app_type,
                "sub_scores": {
                    "skill_match_pct": int(sub["skill_score"]),
                    "experience_match_pct": int(sub["exp_score"]),
                    "semantic_similarity_pct": int(sub["semantic_score"]),
                    "location_match_pct": int(sub["loc_score"])
                },
                "matching_skills": explanation["matching_skills"],
                "missing_skills": explanation["missing_skills"],
                "why_selected": explanation["why_selected"],
                "resume_improvements": explanation["resume_improvements"]
            })

        # 7. Compute RAG Telemetry & Observability Metrics
        latency_ms = (time.time() - start_time) * 1000.0
        rag_metrics = compute_rag_metrics(
            retrieved_scores=scores_for_eval,
            latency_ms=latency_ms,
            retrieval_attempts=retrieval_attempts
        )

        logger.info(f"AgenticRAG: Pipeline finished in {latency_ms:.1f}ms. Returned {len(final_matches)} ranked jobs.")
        
        return {
            "matches": final_matches,
            "pipeline_meta": {
                "intent": query_intent,
                "hyde_generated": bool(hyde_doc),
                "retrieval_attempts": retrieval_attempts,
                "confidence_score": round(confidence, 1),
                "rag_metrics": rag_metrics
            }
        }

# Global engine instance
agentic_rag = AgenticRAGEngine()
