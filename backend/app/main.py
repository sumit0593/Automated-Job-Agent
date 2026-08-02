import sys
import asyncio
import warnings

# Suppress noisy Pydantic, Transformers, and FutureWarning warnings
warnings.filterwarnings("ignore", category=UserWarning, module="pydantic")
warnings.filterwarnings("ignore", category=UserWarning, module="transformers")
warnings.filterwarnings("ignore", category=FutureWarning)

if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

import logging
# Mute verbose logger noise from third-party libraries
logging.getLogger("docling").setLevel(logging.ERROR)
logging.getLogger("sentence_transformers").setLevel(logging.WARNING)
logging.getLogger("transformers").setLevel(logging.ERROR)

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from backend.app.config import settings
from backend.app.database import engine, Base
from backend.app.routes import resumes, jobs, matching, applications, credentials, profile
from backend.app.routes import scheduler as scheduler_routes
from backend.app.services.vectorstore import vector_store
from backend.app.services.llm_router import llm_router
from backend.app.services.llm_providers import get_available_providers

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("uvicorn.error")

# Create database tables & handle lightweight schema migrations
try:
    logger.info("Initializing database schemas...")
    Base.metadata.create_all(bind=engine)
    with engine.connect() as conn:
        from sqlalchemy import text
        try:
            conn.execute(text("ALTER TABLE applications ADD COLUMN application_type VARCHAR DEFAULT 'Unknown'"))
            conn.commit()
            logger.info("Added missing 'application_type' column to applications table.")
        except Exception:
            pass  # Column already exists
        try:
            conn.execute(text("ALTER TABLE user_profiles ADD COLUMN country_code VARCHAR DEFAULT '+91'"))
            conn.commit()
            logger.info("Added missing 'country_code' column to user_profiles table.")
        except Exception:
            pass  # Column already exists
        for col, col_type in [
            ("pan_number", "VARCHAR DEFAULT ''"),
            ("date_of_birth", "VARCHAR DEFAULT ''"),
            ("last_working_day", "VARCHAR DEFAULT ''"),
            ("skills", "TEXT DEFAULT '[]'"),
            ("linkedin_url", "VARCHAR DEFAULT ''"),
            ("github_url", "VARCHAR DEFAULT ''"),
            ("portfolio_url", "VARCHAR DEFAULT ''")
        ]:
            try:
                conn.execute(text(f"ALTER TABLE user_profiles ADD COLUMN {col} {col_type}"))
                conn.commit()
                logger.info(f"Added missing '{col}' column to user_profiles table.")
            except Exception:
                pass
        try:
            conn.execute(text("ALTER TABLE recurring_schedules ADD COLUMN auto_apply INTEGER DEFAULT 0"))
            conn.commit()
            logger.info("Added missing 'auto_apply' column to recurring_schedules table.")
        except Exception:
            pass  # Column already exists
        try:
            conn.execute(text("ALTER TABLE recurring_schedules ADD COLUMN min_match_score INTEGER DEFAULT 70"))
            conn.commit()
            logger.info("Added missing 'min_match_score' column to recurring_schedules table.")
        except Exception:
            pass  # Column already exists
        for col, col_type in [
            ("resume_embedding_hash", "VARCHAR DEFAULT ''"),
            ("embedding_version", "VARCHAR DEFAULT 'bge-m3-v1'"),
            ("reranker_version", "VARCHAR DEFAULT 'bge-reranker-v1'"),
            ("pipeline_version", "VARCHAR DEFAULT 'agentic-rag-v1.2'")
        ]:
            try:
                conn.execute(text(f"ALTER TABLE match_result_cache ADD COLUMN {col} {col_type}"))
                conn.commit()
                logger.info(f"Added missing '{col}' column to match_result_cache table.")
            except Exception:
                pass
except Exception as e:
    logger.critical(f"Database table initialization failed: {e}")

# Initialize FastAPI App
app = FastAPI(
    title=settings.PROJECT_NAME,
    description="Backend services for the Automated Job Agent open-source stack",
    version="1.0.0"
)

# CORS middleware configuration (required for React Vite frontend connectivity)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Adjust for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routes
app.include_router(resumes.router, prefix="/api")
app.include_router(jobs.router, prefix="/api")
app.include_router(matching.router, prefix="/api")
app.include_router(applications.router, prefix="/api")
app.include_router(credentials.router, prefix="/api")
app.include_router(profile.router)
app.include_router(scheduler_routes.router, prefix="/api")

@app.on_event("startup")
def startup_event():
    logger.info("Starting up Automated Job Agent APIs...")
    try:
        vector_store.ensure_collections()
        logger.info("Qdrant collections initialized and verified.")
    except Exception as e:
        logger.warning(f"Could not initialize Qdrant collections on startup (will retry on-demand): {e}")
    
    # Log available LLM providers
    providers = get_available_providers()
    available = [k for k, v in providers.items() if v]
    logger.info(f"LLM Providers available: {available}")
    logger.info(f"LLM Routing Strategy: {settings.LLM_ROUTING_STRATEGY}")
    
    # Start scheduler (queue worker only — recurring jobs added via API)
    try:
        from backend.app.scheduler.scheduler import scheduler_manager
        scheduler_manager.start()
        logger.info("Scheduler and queue worker started.")
    except Exception as e:
        logger.warning(f"Scheduler startup failed (non-fatal): {e}")

@app.on_event("shutdown")
def shutdown_event():
    logger.info("Shutting down Automated Job Agent...")
    try:
        from backend.app.scheduler.scheduler import scheduler_manager
        scheduler_manager.stop()
    except Exception:
        pass

@app.get("/api/health")
def health_check():
    """Simple API health check endpoint."""
    return {
        "status": "healthy",
        "project": settings.PROJECT_NAME,
        "database": settings.DATABASE_URL.split("://")[0]
    }

@app.get("/api/llm/providers")
def llm_providers():
    """Returns which LLM providers are currently available."""
    return get_available_providers()

@app.get("/api/llm/status")
def llm_status():
    """Returns LLM router status including cost tracking."""
    return {
        "routing_strategy": llm_router.strategy,
        "providers": get_available_providers(),
        "cost_tracking": llm_router.get_cost_summary(),
    }
