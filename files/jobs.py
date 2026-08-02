"""
Job Tabs API — Pending / Completed / Failed / Skipped

TAB RULES (enforced at DB query level, not just UI):
  COMPLETED tab = status == "applied" AND applied_at IS NOT NULL
                  (only jobs with confirmed apply timestamp)
  FAILED tab    = status == "failed"
                  Includes failure_reason, failure_detail, unanswered_questions
  PENDING tab   = status in ["pending", "in_progress"]
  SKIPPED tab   = status == "skipped"

The frontend must NOT decide what "completed" means.
The API enforces it — a job with status=applied but no applied_at is excluded.
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from motor.motor_asyncio import AsyncIOMotorDatabase
from datetime import datetime
from typing import Optional

from jobs.models import JobStatus, JobSummary, FailureReason

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


def get_db():
    # Replace with your actual DB dependency
    from main import app
    return app.state.db


# ─── Completed Tab ────────────────────────────────────────────────────────────

@router.get("/completed", response_model=list[JobSummary])
async def get_completed_jobs(
    page:  int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """
    ONLY jobs with status=applied AND applied_at IS NOT NULL.
    Never shows "probably applied" or "submit clicked" jobs.
    """
    skip = (page - 1) * limit
    cursor = db.jobs.find(
        {
            "status":     JobStatus.APPLIED.value,
            "applied_at": {"$ne": None, "$exists": True},
        },
        {"_id": 0}
    ).sort("applied_at", -1).skip(skip).limit(limit)

    jobs = await cursor.to_list(limit)
    return [JobSummary(**j) for j in jobs]


# ─── Failed Tab ───────────────────────────────────────────────────────────────

@router.get("/failed", response_model=list[dict])
async def get_failed_jobs(
    page:           int                    = Query(1, ge=1),
    limit:          int                    = Query(20, ge=1, le=100),
    failure_reason: Optional[FailureReason] = Query(None),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """
    Failed jobs with full failure context.
    Filterable by failure_reason for debugging.
    Retryable failures show a retry button flag.
    """
    skip  = (page - 1) * limit
    query = {"status": JobStatus.FAILED.value}
    if failure_reason:
        query["failure_reason"] = failure_reason.value

    NON_RETRYABLE = {
        FailureReason.CAPTCHA_BLOCKED.value,
        FailureReason.ALREADY_APPLIED.value,
        FailureReason.BLACKLISTED.value,
        FailureReason.UNANSWERED_QUESTION.value,
    }

    cursor = db.jobs.find(query, {"_id": 0}).sort("updated_at", -1).skip(skip).limit(limit)
    jobs = await cursor.to_list(limit)

    result = []
    for j in jobs:
        result.append({
            **j,
            "is_retryable": (
                j.get("failure_reason") not in NON_RETRYABLE
                and j.get("retry_count", 0) < j.get("max_retries", 2)
            ),
        })
    return result


# ─── Pending Tab ─────────────────────────────────────────────────────────────

@router.get("/pending", response_model=list[JobSummary])
async def get_pending_jobs(
    page:  int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    skip = (page - 1) * limit
    cursor = db.jobs.find(
        {"status": {"$in": [JobStatus.PENDING.value, JobStatus.IN_PROGRESS.value]}},
        {"_id": 0}
    ).sort("created_at", -1).skip(skip).limit(limit)

    jobs = await cursor.to_list(limit)
    return [JobSummary(**j) for j in jobs]


# ─── Skipped Tab ─────────────────────────────────────────────────────────────

@router.get("/skipped", response_model=list[JobSummary])
async def get_skipped_jobs(
    page:  int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    skip = (page - 1) * limit
    cursor = db.jobs.find(
        {"status": JobStatus.SKIPPED.value},
        {"_id": 0}
    ).sort("updated_at", -1).skip(skip).limit(limit)

    jobs = await cursor.to_list(limit)
    return [JobSummary(**j) for j in jobs]


# ─── Stats (for dashboard header) ────────────────────────────────────────────

@router.get("/stats")
async def get_job_stats(db: AsyncIOMotorDatabase = Depends(get_db)):
    """Counts per tab. Used by frontend for badge numbers."""
    pipeline = [
        {"$group": {"_id": "$status", "count": {"$sum": 1}}},
    ]
    results = await db.jobs.aggregate(pipeline).to_list(10)
    stats = {r["_id"]: r["count"] for r in results}

    return {
        "pending":   stats.get(JobStatus.PENDING.value, 0)
                   + stats.get(JobStatus.IN_PROGRESS.value, 0),
        "completed": stats.get(JobStatus.APPLIED.value, 0),
        "failed":    stats.get(JobStatus.FAILED.value, 0),
        "skipped":   stats.get(JobStatus.SKIPPED.value, 0),
        "total":     sum(stats.values()),
    }


# ─── Manual Retry ─────────────────────────────────────────────────────────────

@router.post("/failed/{job_id}/retry")
async def retry_failed_job(job_id: str, db: AsyncIOMotorDatabase = Depends(get_db)):
    """
    Manual retry from UI. Only allowed for retryable failures.
    Does NOT retry UNANSWERED_QUESTION — profile must be updated first.
    """
    NON_RETRYABLE = {
        FailureReason.UNANSWERED_QUESTION.value,
        FailureReason.PROFILE_FIELD_MISSING.value,
        FailureReason.CAPTCHA_BLOCKED.value,
        FailureReason.ALREADY_APPLIED.value,
        FailureReason.BLACKLISTED.value,
    }

    job = await db.jobs.find_one({"job_id": job_id})
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if job.get("failure_reason") in NON_RETRYABLE:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot retry: {job['failure_reason']}. "
                   f"Update your profile then retry."
        )

    if job.get("retry_count", 0) >= job.get("max_retries", 2):
        raise HTTPException(status_code=400, detail="Max retries exceeded")

    await db.jobs.update_one(
        {"job_id": job_id},
        {
            "$set": {"status": JobStatus.PENDING.value, "updated_at": datetime.utcnow()},
            "$inc": {"retry_count": 1},
            "$unset": {"failure_reason": "", "failure_detail": ""},
        }
    )
    return {"message": "Job re-queued for retry", "job_id": job_id}
