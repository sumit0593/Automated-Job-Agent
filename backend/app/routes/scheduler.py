"""
Scheduler API Routes — REST endpoints for managing scheduled tasks.

Endpoints:
  POST /api/schedule/discovery      — Add recurring job discovery scan
  POST /api/schedule/batch-apply    — Queue batch applications
  POST /api/schedule/session-refresh — Schedule session cookie refresh
  GET  /api/schedule/status         — View scheduler status + queue stats
  GET  /api/schedule/tasks          — List queued tasks
  GET  /api/schedule/tasks/{id}     — Get specific task details
  DELETE /api/schedule/{job_id}     — Cancel a scheduled recurring job
  DELETE /api/schedule/tasks/{id}   — Cancel a queued task
  GET  /api/schedule/rate-limits    — View rate limiter status
  POST /api/schedule/rate-limits/reset — Reset rate limit counters
"""

import logging
from typing import Optional, List
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.app.scheduler.scheduler import scheduler_manager
from backend.app.scheduler.task_queue import task_queue, TaskType, TaskPriority
from backend.app.scheduler.rate_limiter import rate_limiter

logger = logging.getLogger("uvicorn.error")

router = APIRouter(prefix="/schedule", tags=["Scheduler"])


# ─────────────────────────────────────────────────────────────────────────────
# Request Models
# ─────────────────────────────────────────────────────────────────────────────

class DiscoveryScheduleRequest(BaseModel):
    platform: Optional[str] = Field(None, description="Single job board or comma-separated list (e.g. 'naukri,linkedin')")
    platforms: Optional[List[str]] = Field(default_factory=list, description="List of job boards")
    keyword: str = Field(..., description="Search keyword (e.g., 'AI Engineer')")
    location: Optional[str] = Field("", description="Single location or comma-separated list (e.g. 'Remote, Noida')")
    locations: Optional[List[str]] = Field(default_factory=list, description="List of locations")
    cron_expression: str = Field(
        "0 9,18 * * 1-5",
        description="5-field cron expression (default: 9am & 6pm weekdays)"
    )
    max_jobs: int = Field(25, description="Maximum jobs per scan")
    auto_apply: bool = Field(False, description="Automatically submit applications for high-match jobs (Hands-Free)")
    min_match_score: int = Field(70, description="Minimum match percentage required for auto-apply (default: 70)")


class BatchApplyRequest(BaseModel):
    application_ids: List[int] = Field(..., description="List of application IDs to process")
    delay_minutes: int = Field(0, description="Minutes to wait before starting batch")


class SessionRefreshRequest(BaseModel):
    platform: str = Field(..., description="Platform to refresh session for")
    interval_hours: int = Field(6, description="Refresh interval in hours")


class EnqueueTaskRequest(BaseModel):
    task_type: str = Field(..., description="Task type from TaskType enum")
    payload: dict = Field(default_factory=dict, description="Task parameters")
    priority: str = Field("normal", description="Priority: urgent, high, normal, low, batch")
    scheduled_at: Optional[str] = Field(None, description="ISO datetime for delayed execution")


# ─────────────────────────────────────────────────────────────────────────────
# Scheduler Control Endpoints
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/start")
def start_scheduler():
    """Start the scheduler and queue worker."""
    scheduler_manager.start()
    return {"status": "started", "message": "Scheduler and queue worker are now running."}


@router.post("/stop")
def stop_scheduler():
    """Stop the scheduler and queue worker."""
    scheduler_manager.stop()
    return {"status": "stopped", "message": "Scheduler and queue worker have been stopped."}


@router.get("/status")
def get_scheduler_status():
    """Get comprehensive scheduler status including queue stats and rate limits."""
    return scheduler_manager.get_status()


# ─────────────────────────────────────────────────────────────────────────────
# Recurring Schedule Management
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/discovery")
def add_discovery_schedule(request: DiscoveryScheduleRequest):
    """
    Add recurring job discovery scan(s) across platforms and locations.
    
    Default cron: Runs at 9 AM and 6 PM on weekdays (Mon-Fri).
    """
    try:
        # Determine platforms list
        target_platforms = []
        if request.platforms:
            target_platforms = [p.strip().lower() for p in request.platforms if p.strip()]
        elif request.platform:
            target_platforms = [p.strip().lower() for p in request.platform.split(",") if p.strip()]
        if not target_platforms:
            target_platforms = ["linkedin"]

        # Determine locations list
        target_locations = []
        if request.locations:
            target_locations = [l.strip() for l in request.locations if l.strip()]
        elif request.location:
            target_locations = [l.strip() for l in request.location.split(",") if l.strip()]
        if not target_locations:
            target_locations = [""]

        created_jobs = []
        for p in target_platforms:
            for loc in target_locations:
                job_id = scheduler_manager.add_discovery_schedule(
                    platform=p,
                    keyword=request.keyword,
                    location=loc,
                    cron_expression=request.cron_expression,
                    max_jobs=request.max_jobs,
                    auto_apply=request.auto_apply,
                    min_match_score=request.min_match_score,
                )
                created_jobs.append({
                    "job_id": job_id,
                    "platform": p,
                    "location": loc,
                    "auto_apply": request.auto_apply,
                    "min_match_score": request.min_match_score,
                })

        return {
            "status": "scheduled",
            "count": len(created_jobs),
            "jobs": created_jobs,
            "cron": request.cron_expression,
            "keyword": request.keyword,
            "auto_apply": request.auto_apply,
            "min_match_score": request.min_match_score,
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/session-refresh")
def add_session_refresh(request: SessionRefreshRequest):
    """Schedule periodic browser session/cookie refresh."""
    job_id = scheduler_manager.add_session_refresh_schedule(
        platform=request.platform,
        interval_hours=request.interval_hours,
    )
    return {
        "status": "scheduled",
        "job_id": job_id,
        "platform": request.platform,
        "interval_hours": request.interval_hours,
    }


@router.delete("/schedules/all")
def clear_all_schedules():
    """Remove all recurring schedules from APScheduler and disable in DB."""
    count = scheduler_manager.remove_all_schedules()
    return {"status": "cleared", "count": count}


@router.delete("/{job_id}")
def remove_schedule(job_id: str):
    """Remove a recurring scheduled job by ID."""
    success = scheduler_manager.remove_schedule(job_id)
    if not success:
        raise HTTPException(status_code=404, detail=f"Schedule '{job_id}' not found.")
    return {"status": "removed", "job_id": job_id}


@router.get("/schedules")
def list_schedules():
    """List all active recurring schedules."""
    return {"schedules": scheduler_manager.list_schedules()}


# ─────────────────────────────────────────────────────────────────────────────
# Task Queue Endpoints
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/batch-apply")
def schedule_batch_apply(request: BatchApplyRequest):
    """Queue a batch of applications for sequential processing."""
    if not request.application_ids:
        raise HTTPException(status_code=400, detail="application_ids list is empty.")
    
    scheduler_manager.schedule_batch_apply(
        application_ids=request.application_ids,
        delay_minutes=request.delay_minutes,
    )
    return {
        "status": "queued",
        "application_count": len(request.application_ids),
        "delay_minutes": request.delay_minutes,
    }


@router.post("/tasks/enqueue")
def enqueue_task(request: EnqueueTaskRequest):
    """Manually enqueue a task into the processing queue."""
    try:
        task_type_enum = TaskType(request.task_type)
    except ValueError:
        valid = [t.value for t in TaskType]
        raise HTTPException(
            status_code=400,
            detail=f"Invalid task_type '{request.task_type}'. Valid: {valid}"
        )
    
    try:
        priority_enum = TaskPriority(request.priority)
    except ValueError:
        priority_enum = TaskPriority.NORMAL
    
    scheduled_at = None
    if request.scheduled_at:
        from datetime import datetime
        try:
            scheduled_at = datetime.fromisoformat(request.scheduled_at)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid scheduled_at format. Use ISO format: 2026-08-01T09:00:00"
            )
    
    task_id = task_queue.enqueue(
        task_type=task_type_enum,
        payload=request.payload,
        priority=priority_enum,
        scheduled_at=scheduled_at,
    )
    
    if task_id is None:
        return {"status": "deduplicated", "message": "Identical pending task already exists."}
    
    return {"status": "enqueued", "task_id": task_id}


@router.get("/tasks")
def list_tasks(
    status: Optional[str] = None,
    task_type: Optional[str] = None,
    limit: int = 50,
):
    """List queued tasks with optional filtering."""
    tasks = task_queue.list_tasks(status=status, task_type=task_type, limit=limit)
    return {"tasks": tasks, "total": len(tasks)}


@router.get("/tasks/{task_id}")
def get_task(task_id: int):
    """Get detailed information about a specific task."""
    task = task_queue.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found.")
    return task


@router.delete("/tasks/history")
def clear_task_history(include_all: bool = False):
    """Delete completed, failed, and cancelled task execution history."""
    count = task_queue.clear_history(include_all=include_all)
    return {"status": "cleared", "count": count}


@router.delete("/tasks/{task_id}")
def cancel_task(task_id: int):
    """Cancel a pending or running task."""
    success = task_queue.cancel(task_id)
    if not success:
        raise HTTPException(
            status_code=400,
            detail=f"Task {task_id} cannot be cancelled (may be completed or not found)."
        )
    return {"status": "cancelled", "task_id": task_id}


@router.get("/queue-stats")
def get_queue_stats():
    """Get task queue health metrics."""
    return task_queue.get_queue_stats()


# ─────────────────────────────────────────────────────────────────────────────
# Rate Limit Endpoints
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/rate-limits")
def get_rate_limits(platform: Optional[str] = None):
    """Get current rate limit status for all or a specific platform."""
    return rate_limiter.get_status(platform)


@router.post("/rate-limits/reset")
def reset_rate_limits(platform: Optional[str] = None):
    """Reset rate limit counters. If platform specified, resets only that platform."""
    rate_limiter.reset(platform)
    return {
        "status": "reset",
        "platform": platform or "all",
    }
