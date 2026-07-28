import logging
from typing import Dict, Any, List
from backend.app.services.vectorstore import vector_store
from backend.app.automation.candidate.semantic.chunker import chunk_candidate_profile

logger = logging.getLogger("uvicorn.error")

def index_candidate_semantic_profile(resume_id: int, profile: Dict[str, Any], raw_resume_text: str):
    """
    Chunks the structured Candidate Profile and indexes all sections in the Qdrant semantic profile collection.
    """
    try:
        logger.info(f"generator: Chunking candidate profile for resume ID {resume_id}...")
        chunks = chunk_candidate_profile(profile, raw_resume_text)
        
        logger.info(f"generator: Indexing {len(chunks)} profile chunks in Qdrant...")
        vector_store.index_profile_chunks(resume_id, chunks)
        logger.info("generator: Semantic profile indexing complete.")
    except Exception as e:
        logger.error(f"generator: Failed to index candidate semantic profile: {e}")
        raise e
