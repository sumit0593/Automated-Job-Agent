import sys
import asyncio

if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from backend.app.config import settings
from backend.app.database import engine, Base
from backend.app.routes import resumes, jobs, matching, applications, credentials, profile
from backend.app.services.vectorstore import vector_store

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

@app.on_event("startup")
def startup_event():
    logger.info("Starting up Automated Job Agent APIs...")
    try:
        vector_store.ensure_collections()
        logger.info("Qdrant collections initialized and verified.")
    except Exception as e:
        logger.warning(f"Could not initialize Qdrant collections on startup (will retry on-demand): {e}")

@app.get("/api/health")
def health_check():
    """Simple API health check endpoint."""
    return {
        "status": "healthy",
        "project": settings.PROJECT_NAME,
        "database": settings.DATABASE_URL.split("://")[0]
    }
