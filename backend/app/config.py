import os
from pathlib import Path
from pydantic_settings import BaseSettings
from dotenv import load_dotenv
load_dotenv()

# Base directories
BASE_DIR = Path(__file__).resolve().parent.parent.parent
STORAGE_DIR = BASE_DIR / "storage"
RESUMES_DIR = STORAGE_DIR / "resumes"
TAILORED_RESUMES_DIR = STORAGE_DIR / "tailored_resumes"
LOGS_DIR = STORAGE_DIR / "logs"

# Ensure storage directories exist
for directory in [STORAGE_DIR, RESUMES_DIR, TAILORED_RESUMES_DIR, LOGS_DIR]:
    directory.mkdir(parents=True, exist_ok=True)

class Settings(BaseSettings):
    # App Settings
    PROJECT_NAME: str = "Automated Job Agent API"
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    
    # Database Settings (PostgreSQL default, sqlite fallback)
    DATABASE_URL: str = "sqlite:///./job_agent.db"
    
    # Vector Database Settings
    # If QDRANT_URL is empty, we will use in-memory/disk-based local Qdrant database
    QDRANT_URL: str = ""
    QDRANT_API_KEY: str = ""
    QDRANT_COLLECTION_JOBS: str = "jobs"
    QDRANT_COLLECTION_RESUMES: str = "resumes"

    # print(os.getenv("HF_TOKEN"))
    
    # LLM & Embeddings Settings
    HF_TOKEN: str = os.getenv("HF_TOKEN")  # Hugging Face token for Inference API
    LLM_MODEL: str = "Qwen/Qwen2.5-72B-Instruct"  # High performance open source model
    EMBEDDINGS_MODEL: str = "BAAI/bge-m3"
    RERANKER_MODEL: str = "BAAI/bge-reranker-large"
    
    # Storage Settings
    STORAGE_PATH: str = str(STORAGE_DIR)
    RESUMES_PATH: str = str(RESUMES_DIR)
    TAILORED_RESUMES_PATH: str = str(TAILORED_RESUMES_DIR)
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

settings = Settings()
