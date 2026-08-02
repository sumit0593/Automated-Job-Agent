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
BROWSER_PROFILES_DIR = STORAGE_DIR / "browser_profiles"
SCREENSHOTS_DIR = STORAGE_DIR / "screenshots"

# Ensure storage directories exist
for directory in [STORAGE_DIR, RESUMES_DIR, TAILORED_RESUMES_DIR, LOGS_DIR, BROWSER_PROFILES_DIR, SCREENSHOTS_DIR]:
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
    HF_TOKEN: str = os.getenv("HF_TOKEN", "")  # Hugging Face token for Inference API
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")  # Google Gemini API key
    GROK_API_KEY: str = os.getenv("GROK_API_KEY", "")  # xAI Grok API key
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")  # OpenAI API key
    OLLAMA_URL: str = os.getenv("OLLAMA_URL", "http://localhost:11434")  # Local Ollama server URL
    LLM_MODEL: str = "Qwen/Qwen2.5-72B-Instruct"  # High-performance serverless router model
    EMBEDDINGS_MODEL: str = "BAAI/bge-m3"
    RERANKER_MODEL: str = "BAAI/bge-reranker-large"
    
    # LLM Routing Strategy: "cost_optimized", "balanced", "quality_first", "local_only"
    LLM_ROUTING_STRATEGY: str = os.getenv("LLM_ROUTING_STRATEGY", "balanced")
    
    # Observability & Tracing (Langfuse & LangSmith)
    LANGFUSE_PUBLIC_KEY: str = os.getenv("LANGFUSE_PUBLIC_KEY", "")
    LANGFUSE_SECRET_KEY: str = os.getenv("LANGFUSE_SECRET_KEY", "")
    LANGFUSE_HOST: str = os.getenv("LANGFUSE_HOST", os.getenv("LANGFUSE_BASE_URL", "https://cloud.langfuse.com"))
    LANGFUSE_BASE_URL: str = os.getenv("LANGFUSE_BASE_URL", os.getenv("LANGFUSE_HOST", "https://cloud.langfuse.com"))
    LANGSMITH_API_KEY: str = os.getenv("LANGSMITH_API_KEY", "")
    LANGSMITH_PROJECT: str = os.getenv("LANGSMITH_PROJECT", "Automated-Job-Agent")

    # Redis Hot Cache Settings
    REDIS_URL: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    
    # Model & Pipeline Versioning
    EMBEDDING_VERSION: str = "bge-m3-v1"
    RERANKER_VERSION: str = "bge-reranker-v1"
    PIPELINE_VERSION: str = "agentic-rag-v1.2"

    # Storage Settings
    STORAGE_PATH: str = str(STORAGE_DIR)
    RESUMES_PATH: str = str(RESUMES_DIR)
    TAILORED_RESUMES_PATH: str = str(TAILORED_RESUMES_DIR)
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

settings = Settings()
