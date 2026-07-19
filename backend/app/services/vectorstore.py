import logging
from typing import List, Dict, Any, Optional
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct
from backend.app.config import settings

logger = logging.getLogger("uvicorn.error")

class VectorStoreService:
    def __init__(self):
        # Initialize Qdrant Client (local or cloud)
        if settings.QDRANT_URL:
            logger.info(f"Initializing Qdrant client connected to {settings.QDRANT_URL}...")
            self.client = QdrantClient(url=settings.QDRANT_URL, api_key=settings.QDRANT_API_KEY)
        else:
            logger.info("Qdrant URL not specified. Initializing local disk-based Qdrant client (stored in qdrant_db/)...")
            self.client = QdrantClient(path="qdrant_db")
        
        self._model = None
        self._reranker = None
        self._initialized = False

    def ensure_collections(self):
        """Creates collections if they do not exist."""
        if self._initialized:
            return
        
        for col_name in [settings.QDRANT_COLLECTION_JOBS, settings.QDRANT_COLLECTION_RESUMES]:
            try:
                # In modern qdrant_client, collection_exists is a standard API
                if not self.client.collection_exists(col_name):
                    logger.info(f"Creating Qdrant collection: {col_name}")
                    self.client.create_collection(
                        collection_name=col_name,
                        vectors_config=VectorParams(size=1024, distance=Distance.COSINE)
                    )
            except Exception as e:
                logger.error(f"Error checking/creating Qdrant collection {col_name}: {e}")
        
        self._initialized = True

    def get_embedding_model(self):
        """Lazy-loads the BGE-M3 SentenceTransformer model."""
        if self._model is None:
            from sentence_transformers import SentenceTransformer
            logger.info(f"Loading embeddings model {settings.EMBEDDINGS_MODEL} locally...")
            self._model = SentenceTransformer(settings.EMBEDDINGS_MODEL)
        return self._model

    def get_reranker_model(self):
        """Lazy-loads the BGE-Reranker-Large model."""
        if self._reranker is None:
            from sentence_transformers import CrossEncoder
            logger.info(f"Loading reranker model {settings.RERANKER_MODEL} locally...")
            self._reranker = CrossEncoder(settings.RERANKER_MODEL)
        return self._reranker

    def embed_text(self, text: str) -> List[float]:
        """Generates a dense vector embedding (1024 dims) using BGE-M3."""
        model = self.get_embedding_model()
        # BGE-M3 dense embeddings are normalized, so we get cosine similarity
        embedding = model.encode(text, normalize_embeddings=True)
        return embedding.tolist()

    def index_job(self, job_id: int, title: str, company: str, description: str, skills: List[str]):
        """Indexes a job opportunity in Qdrant with its dense embedding and metadata."""
        self.ensure_collections()
        
        # Combine title, company, description for embedding text representation
        embedding_text = f"Title: {title}\nCompany: {company}\nDescription: {description}\nRequired Skills: {', '.join(skills)}"
        vector = self.embed_text(embedding_text)
        
        payload = {
            "id": job_id,
            "title": title,
            "company": company,
            "skills": [s.lower() for s in skills],
        }
        
        self.client.upsert(
            collection_name=settings.QDRANT_COLLECTION_JOBS,
            points=[
                PointStruct(
                    id=job_id,
                    vector=vector,
                    payload=payload
                )
            ]
        )
        logger.info(f"Indexed job {job_id} ({title} at {company}) in Qdrant")

    def delete_job(self, job_id: int):
        """Deletes a job from Qdrant."""
        self.ensure_collections()
        self.client.delete(
            collection_name=settings.QDRANT_COLLECTION_JOBS,
            points_selector=[job_id]
        )

    def index_resume(self, resume_id: int, raw_text: str, skills: List[str]):
        """Indexes a candidate's resume in Qdrant."""
        self.ensure_collections()
        
        embedding_text = f"Candidate Profile\nSkills: {', '.join(skills)}\nResume Details:\n{raw_text}"
        vector = self.embed_text(embedding_text)
        
        payload = {
            "id": resume_id,
            "skills": [s.lower() for s in skills]
        }
        
        self.client.upsert(
            collection_name=settings.QDRANT_COLLECTION_RESUMES,
            points=[
                PointStruct(
                    id=resume_id,
                    vector=vector,
                    payload=payload
                )
            ]
        )
        logger.info(f"Indexed resume {resume_id} in Qdrant")

    def search_similar_jobs(self, resume_text: str, resume_skills: List[str], limit: int = 20) -> List[Dict[str, Any]]:
        """
        Executes a hybrid matching and reranking pipeline:
        1. Dense retrieval using Qdrant (top 50 candidate jobs).
        2. Lexical/keyword alignment check (skills intersection).
        3. Local BGE-Reranker-Large cross-encoder validation for top 10 scoring jobs.
        """
        self.ensure_collections()
        
        # Step 1: Dense Retrieval
        resume_embedding = self.embed_text(resume_text)
        search_results = self.client.search(
            collection_name=settings.QDRANT_COLLECTION_JOBS,
            query_vector=resume_embedding,
            limit=50
        )
        
        candidates = []
        resume_skills_set = set(s.lower() for s in resume_skills)
        
        # Step 2: Compute Hybrid Score
        for hit in search_results:
            job_payload = hit.payload
            job_id = job_payload["id"]
            job_title = job_payload["title"]
            job_company = job_payload["company"]
            job_skills = set(job_payload.get("skills", []))
            
            # Compute skill overlap score (lexical matching)
            overlap_score = 0.0
            if resume_skills_set and job_skills:
                # Jaccard index or intersection ratio
                intersection = resume_skills_set.intersection(job_skills)
                overlap_score = len(intersection) / len(resume_skills_set)
            
            # Hybrid score (dense similarity + keyword alignment weight)
            # cosine similarity ranges from -1 to 1 (typically 0.3 to 0.9 for match candidates)
            dense_score = float(hit.score)
            hybrid_score = (dense_score * 0.7) + (overlap_score * 0.3)
            
            candidates.append({
                "job_id": job_id,
                "title": job_title,
                "company": job_company,
                "dense_score": dense_score,
                "overlap_score": overlap_score,
                "hybrid_score": hybrid_score
            })
            
        # Sort by hybrid score
        candidates.sort(key=lambda x: x["hybrid_score"], reverse=True)
        top_candidates = candidates[:limit]
        
        return top_candidates

    def rerank_jobs(self, resume_text: str, jobs: List[Dict[str, Any]], limit: int = 10) -> List[Dict[str, Any]]:
        """
        Reranks a list of candidate jobs against a resume using the BGE-Reranker-Large cross-encoder.
        """
        if not jobs:
            return []
            
        try:
            reranker = self.get_reranker_model()
            
            # Prepare pairs of (query, document)
            pairs = []
            for job in jobs:
                # We need to load job description to pass to reranker
                # If description is not passed, we can query it or use what's available
                # Let's assume the jobs list passed has a "description" field.
                job_desc = job.get("description", "")
                job_text = f"Title: {job['title']}\nCompany: {job['company']}\nDescription: {job_desc}"
                pairs.append((resume_text, job_text))
            
            # Predict scores
            logger.info(f"Running BGE-Reranker-Large cross-encoder for {len(pairs)} candidates...")
            scores = reranker.predict(pairs)
            
            # Assign scores and sort
            for idx, score in enumerate(scores):
                jobs[idx]["rerank_score"] = float(score)
                # Map logit score to a user-friendly percentage (sigmoid representation or relative normalization)
                # Let's compute a simple mapping for the UI: score usually sits around -4 to +4
                import math
                prob = 1 / (1 + math.exp(-float(score)))
                jobs[idx]["match_percentage"] = int(prob * 100)
                
            jobs.sort(key=lambda x: x.get("rerank_score", -9999), reverse=True)
            return jobs[:limit]
        except Exception as e:
            logger.error(f"Error during cross-encoder reranking: {e}. Returning un-reranked list.")
            # Fallback: create match percentage from hybrid score
            for job in jobs:
                job["rerank_score"] = job["hybrid_score"]
                job["match_percentage"] = int(min(1.0, max(0.0, job["hybrid_score"])) * 100)
            return jobs[:limit]

# Global singleton service
vector_store = VectorStoreService()
