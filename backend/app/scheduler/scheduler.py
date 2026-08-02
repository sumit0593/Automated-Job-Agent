"""
Scheduler — APScheduler-based cron engine for recurring automation tasks.

Supports:
  - Recurring job discovery scans (cron-based)
  - Batch application scheduling with rate limiting
  - Session refresh for browser cookies
  - One-time scheduled tasks (run at specific datetime)
  - Worker loop that processes the task queue

Uses APScheduler with SQLite job store for persistence across restarts.
No Redis dependency required for local development.
"""

import logging
import threading
import time
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, Callable, List
from dataclasses import dataclass

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.date import DateTrigger
from apscheduler.jobstores.memory import MemoryJobStore

from backend.app.scheduler.task_queue import (
    task_queue,
    TaskType,
    TaskPriority,
    TaskStatus,
)
from backend.app.scheduler.rate_limiter import rate_limiter

logger = logging.getLogger("uvicorn.error")


# ─────────────────────────────────────────────────────────────────────────────
# Task Executor Registry
# ─────────────────────────────────────────────────────────────────────────────

# Maps task types to their executor functions
# Each executor receives (payload: dict) and returns (result: dict)
_TASK_EXECUTORS: Dict[str, Callable] = {}


def register_executor(task_type: str):
    """Decorator to register a task executor function."""
    def decorator(func: Callable):
        _TASK_EXECUTORS[task_type] = func
        logger.info(f"Scheduler: Registered executor for task type '{task_type}'")
        return func
    return decorator


# ─────────────────────────────────────────────────────────────────────────────
# Built-in Task Executors
# ─────────────────────────────────────────────────────────────────────────────

@register_executor(TaskType.DISCOVERY_SCAN.value)
def execute_discovery_scan(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Executes a job discovery scan for a platform + keyword combo.
    Enqueues via the scraper service.
    """
    platform = payload.get("platform", "linkedin")
    keyword = payload.get("keyword", "")
    location = payload.get("location", "")
    max_jobs = payload.get("max_jobs", 25)
    
    logger.info(
        f"Executor[discovery_scan]: Running scan on '{platform}' "
        f"for '{keyword}' in '{location}' (max {max_jobs} jobs)"
    )
    
    try:
        from backend.app.services.scraper import discover_jobs_via_platform, search_jobs_on_web
        from backend.app.database import SessionLocal
        from backend.app import models
        
        db = SessionLocal()
        jobs = []
        try:
            if platform:
                cred = db.query(models.UserCredential).filter(models.UserCredential.platform == platform.lower()).first()
                cookies = cred.session_cookies if (cred and cred.session_cookies) else None
                jobs = discover_jobs_via_platform(
                    platform=platform.lower(),
                    cookies=cookies,
                    keyword=keyword,
                    location=location,
                    max_jobs=max_jobs,
                )
            else:
                jobs = search_jobs_on_web(keyword, location)
                
            # Save scraped jobs into DB & Qdrant vector store
            if jobs:
                from backend.app.services.vectorstore import vector_store
                for item in jobs:
                    raw_url = item.get("url", "").strip()
                    if not raw_url:
                        continue
                    # Normalize URL by removing query tracking params and trailing slash
                    job_url = raw_url.split('?')[0].rstrip('/')
                    title = item.get("title", "Unknown Role").strip()
                    company = item.get("company", "Unknown Company").strip()

                    # Deduplicate by URL or title + company combination
                    existing = db.query(models.Job).filter(
                        (models.Job.url == job_url) | 
                        ((models.Job.title == title) & (models.Job.company == company))
                    ).first()

                    if not existing:
                        skills = item.get("skills_required", item.get("skills", []))
                        db_job = models.Job(
                            title=item.get("title", "Unknown Role"),
                            company=item.get("company", "Unknown Company"),
                            location=item.get("location", location),
                            description=item.get("description", "No description provided."),
                            url=job_url,
                            skills_required=skills if isinstance(skills, list) else [],
                            experience_required=item.get("experience_required", 2.0),
                        )
                        db.add(db_job)
                        db.commit()
                        db.refresh(db_job)
                        
                        # Index in Qdrant Vector DB for instant matching
                        try:
                            vector_store.index_job(
                                job_id=db_job.id,
                                title=db_job.title,
                                company=db_job.company,
                                description=db_job.description,
                                skills=db_job.skills_required,
                            )
                        except Exception as ve:
                            logger.warning(f"Executor[discovery_scan]: Qdrant indexing warning: {ve}")

            # Optional: Hands-Free Auto-Apply to high-match jobs
            auto_apply = payload.get("auto_apply", False)
            min_match_score = payload.get("min_match_score", 70)
            auto_applied_count = 0

            if auto_apply and jobs:
                try:
                    resume = db.query(models.Resume).order_by(models.Resume.created_at.desc()).first()
                    if resume:
                        from backend.app.services.matching.agentic_rag import agentic_rag
                        match_res = agentic_rag.run_matching_pipeline(resume, db)
                        high_matches = [
                            m for m in match_res.get("matches", [])
                            if m.get("match_percentage", 0) >= min_match_score and m.get("application_id")
                        ]
                        if high_matches:
                            app_ids = [m["application_id"] for m in high_matches]
                            logger.info(f"Executor[discovery_scan]: Auto-applying to {len(app_ids)} high-match jobs (score >= {min_match_score}%)")
                            from backend.app.scheduler.scheduler import scheduler_manager
                            scheduler_manager.schedule_batch_apply(
                                application_ids=app_ids,
                                delay_minutes=0,
                            )
                            auto_applied_count = len(app_ids)
                except Exception as auto_err:
                    logger.error(f"Executor[discovery_scan]: Auto-apply pipeline error: {auto_err}")

        finally:
            db.close()
            
        return {
            "jobs_found": len(jobs) if jobs else 0,
            "platform": platform,
            "keyword": keyword,
            "auto_applied_count": auto_applied_count,
        }
    except Exception as e:
        logger.error(f"Executor[discovery_scan]: Error: {e}")
        return {"jobs_found": 0, "error": str(e)}


@register_executor(TaskType.SESSION_REFRESH.value)
def execute_session_refresh(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Refreshes browser cookies for a platform."""
    platform = payload.get("platform", "linkedin")
    logger.info(f"Executor[session_refresh]: Refreshing session for '{platform}'")
    
    try:
        from backend.app.services.browser_manager import launch_persistent_browser
        pw, context, page = launch_persistent_browser(
            platform=platform, headless=True
        )
        
        # Navigate to platform homepage to trigger cookie refresh
        url_map = {
            "linkedin": "https://www.linkedin.com",
            "naukri": "https://www.naukri.com",
        }
        homepage = url_map.get(platform, "")
        if homepage:
            page.goto(homepage, timeout=15000)
            page.wait_for_timeout(3000)
            cookies = context.cookies()
            
            # Save cookies to DB
            from backend.app.automation.session.session_manager import update_session
            from backend.app.database import SessionLocal
            db = SessionLocal()
            try:
                update_session(db, platform, cookies)
            finally:
                db.close()
        
        context.close()
        pw.stop()
        
        return {"platform": platform, "refreshed": True}
    except Exception as e:
        logger.error(f"Executor[session_refresh]: Error: {e}")
        return {"platform": platform, "refreshed": False, "error": str(e)}


@register_executor(TaskType.MATCH_PIPELINE.value)
def execute_match_pipeline(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Runs the Agentic RAG matching pipeline for a resume."""
    resume_id = payload.get("resume_id")
    if not resume_id:
        return {"error": "resume_id required"}
    
    logger.info(f"Executor[match_pipeline]: Running matching for resume {resume_id}")
    
    try:
        from backend.app.database import SessionLocal
        from backend.app import models
        from backend.app.services.matching.agentic_rag import agentic_rag
        
        db = SessionLocal()
        try:
            resume = db.query(models.Resume).filter(
                models.Resume.id == resume_id
            ).first()
            if not resume:
                return {"error": f"Resume {resume_id} not found"}
            
            result = agentic_rag.run_matching_pipeline(resume, db)
            return {
                "resume_id": resume_id,
                "matches_found": len(result.get("matches", [])),
            }
        finally:
            db.close()
    except Exception as e:
        logger.error(f"Executor[match_pipeline]: Error: {e}")
        return {"error": str(e)}


@register_executor(TaskType.SINGLE_APPLY.value)
def execute_single_apply(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Executes automation flow for a single application ID.
    Reads candidate profile data (name, email, phone) from UserProfile DB table.
    """
    application_id = payload.get("application_id")
    if not application_id:
        return {"error": "application_id required"}
    
    logger.info(f"Executor[single_apply]: Starting auto-apply task for Application #{application_id}")
    
    try:
        from backend.app.database import SessionLocal
        from backend.app import models
        from backend.app.routes.applications import run_apply_automation, ApplyRequest
        import asyncio

        db = SessionLocal()
        try:
            app = db.query(models.Application).filter(models.Application.id == application_id).first()
            if not app:
                return {"error": f"Application {application_id} not found"}
            
            # Fetch UserProfile for contact info
            profile = db.query(models.UserProfile).first()
            full_name = profile.name if profile and profile.name else "Candidate"
            name_parts = full_name.strip().split()
            first_name = name_parts[0] if name_parts else "Candidate"
            last_name = " ".join(name_parts[1:]) if len(name_parts) > 1 else ""
            email = profile.email if profile and profile.email else "candidate@example.com"
            phone = profile.phone if profile and profile.phone else ""

            req_data = ApplyRequest(
                first_name=first_name,
                last_name=last_name,
                email=email,
                phone=phone,
                headful=payload.get("headful", False)
            )

            # Run application automation flow
            asyncio.run(run_apply_automation(application_id, req_data))
            
            db.refresh(app)
            return {"application_id": application_id, "status": app.status, "logs": app.logs}
        finally:
            db.close()
    except Exception as e:
        logger.error(f"Executor[single_apply]: Application {application_id} failed: {e}")
        return {"error": str(e)}


@register_executor(TaskType.BATCH_APPLY.value)
def execute_batch_apply(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Executes single_apply across each application_id in payload."""
    app_ids = payload.get("application_ids", [])
    logger.info(f"Executor[batch_apply]: Processing batch of {len(app_ids)} application IDs")
    results = []
    for app_id in app_ids:
        res = execute_single_apply({"application_id": app_id, "headful": payload.get("headful", False)})
        results.append(res)
    return {"processed": len(results), "details": results}


# ─────────────────────────────────────────────────────────────────────────────
# Queue Worker — Processes tasks from the queue
# ─────────────────────────────────────────────────────────────────────────────

class QueueWorker:
    """
    Background worker that polls the task queue and executes tasks.
    Respects rate limits and priority ordering.
    """
    
    def __init__(self, poll_interval: int = 10):
        self.poll_interval = poll_interval
        self._running = False
        self._thread: Optional[threading.Thread] = None
    
    def start(self):
        """Start the queue worker in a background thread."""
        if self._running:
            return
        
        self._running = True
        self._thread = threading.Thread(target=self._worker_loop, daemon=True)
        self._thread.start()
        logger.info(f"QueueWorker: Started (poll interval: {self.poll_interval}s)")
    
    def stop(self):
        """Stop the queue worker."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)
        logger.info("QueueWorker: Stopped")
    
    def _worker_loop(self):
        """Main polling loop — dequeues and executes tasks."""
        while self._running:
            try:
                # Clean up stale tasks periodically
                task_queue.cleanup_stale(stale_minutes=30)
                
                # Dequeue next task
                task = task_queue.dequeue()
                if not task:
                    time.sleep(self.poll_interval)
                    continue
                
                task_type = task.task_type
                executor = _TASK_EXECUTORS.get(task_type)
                
                if not executor:
                    logger.warning(
                        f"QueueWorker: No executor registered for "
                        f"task type '{task_type}'. Skipping task {task.id}."
                    )
                    task_queue.mark_failed(
                        task.id, f"No executor for task type '{task_type}'"
                    )
                    continue
                
                # Check rate limits for platform-specific tasks
                import json
                payload = json.loads(task.payload) if task.payload else {}
                platform = payload.get("platform", "")
                
                if platform:
                    can_proceed, wait_secs, reason = rate_limiter.check(platform)
                    if not can_proceed:
                        logger.info(
                            f"QueueWorker: Rate limited for task {task.id}. "
                            f"{reason}. Rescheduling."
                        )
                        # Reschedule after the wait period
                        from datetime import datetime, timedelta
                        task_queue.mark_failed(task.id, f"Rate limited: {reason}")
                        continue
                
                # Execute the task
                logger.info(
                    f"QueueWorker: Executing task {task.id} "
                    f"type='{task_type}' priority='{task.priority}'"
                )
                task_queue.mark_running(task.id)
                
                try:
                    result = executor(payload)
                    task_queue.mark_completed(task.id, result)
                    
                    # Record rate limit usage if platform-specific
                    if platform:
                        rate_limiter.record(platform)
                
                except Exception as e:
                    logger.error(
                        f"QueueWorker: Task {task.id} execution failed: {e}"
                    )
                    task_queue.mark_failed(task.id, str(e))
                
            except Exception as e:
                logger.error(f"QueueWorker: Loop error: {e}")
                time.sleep(self.poll_interval)


# ─────────────────────────────────────────────────────────────────────────────
# Scheduler Manager — Manages recurring cron jobs + queue worker
# ─────────────────────────────────────────────────────────────────────────────

class SchedulerManager:
    """
    Central scheduler managing both:
      1. APScheduler cron jobs (recurring discovery, session refresh)
      2. Queue worker (processes on-demand task queue)
    
    Usage:
        scheduler = SchedulerManager()
        scheduler.start()
        
        # Add recurring job discovery
        scheduler.add_discovery_schedule(
            platform="linkedin",
            keyword="AI Engineer",
            cron_expression="0 9,18 * * 1-5",  # 9am & 6pm weekdays
        )
        
        # One-time batch apply
        scheduler.schedule_batch_apply(
            application_ids=[1, 2, 3],
            delay_minutes=5,
        )
    """
    
    def __init__(self):
        self._scheduler = BackgroundScheduler(
            jobstores={"default": MemoryJobStore()},
            job_defaults={
                "coalesce": True,       # Merge missed runs into one
                "max_instances": 2,     # Max concurrent instances per job
                "misfire_grace_time": 300,  # 5 min grace for missed triggers
            },
        )
        self._worker = QueueWorker(poll_interval=10)
        self._running = False
    
    def start(self):
        """Start the scheduler and queue worker, reloading persisted schedules."""
        if self._running:
            return
        
        from apscheduler.schedulers.base import STATE_STOPPED
        if getattr(self._scheduler, "state", None) == STATE_STOPPED:
            self._scheduler = BackgroundScheduler(
                jobstores={"default": MemoryJobStore()},
                job_defaults={
                    "coalesce": True,
                    "max_instances": 2,
                    "misfire_grace_time": 300,
                },
            )
        
        if not self._scheduler.running:
            self._scheduler.start()
            
        if not getattr(self._worker, "_running", False):
            self._worker = QueueWorker(poll_interval=10)
            self._worker.start()
            
        self._running = True
        
        # Load persisted schedules from SQLite DB
        self._load_persisted_schedules()
        logger.info("SchedulerManager: Started (APScheduler + QueueWorker)")
    
    def _load_persisted_schedules(self):
        """Reload recurring schedule rules from SQLite DB on startup."""
        try:
            from backend.app.database import SessionLocal
            from backend.app.scheduler.task_queue import RecurringSchedule
            
            db = SessionLocal()
            try:
                schedules = db.query(RecurringSchedule).filter(RecurringSchedule.enabled == 1).all()
                for s in schedules:
                    if s.schedule_type == "discovery":
                        self._register_discovery_job(
                            job_id=s.job_id,
                            platform=s.platform,
                            keyword=s.keyword or "",
                            location=s.location or "",
                            cron_expression=s.cron_expression or "0 9,18 * * 1-5",
                            max_jobs=s.max_jobs or 25,
                            auto_apply=bool(s.auto_apply),
                            min_match_score=s.min_match_score or 70,
                        )
                    elif s.schedule_type == "session_refresh":
                        self._register_session_refresh_job(
                            job_id=s.job_id,
                            platform=s.platform,
                            interval_hours=s.interval_hours or 6,
                        )
                if schedules:
                    logger.info(f"SchedulerManager: Reloaded {len(schedules)} persisted schedules from database.")
            finally:
                db.close()
        except Exception as e:
            logger.warning(f"SchedulerManager: Could not reload persisted schedules: {e}")

    def _register_discovery_job(
        self,
        job_id: str,
        platform: str,
        keyword: str,
        location: str,
        cron_expression: str,
        max_jobs: int,
        auto_apply: bool = False,
        min_match_score: int = 70,
    ):
        """Internal helper to register discovery job in APScheduler."""
        def _enqueue_discovery():
            task_queue.enqueue(
                task_type=TaskType.DISCOVERY_SCAN,
                payload={
                    "platform": platform,
                    "keyword": keyword,
                    "location": location,
                    "max_jobs": max_jobs,
                    "auto_apply": auto_apply,
                    "min_match_score": min_match_score,
                },
                priority=TaskPriority.NORMAL,
            )
        
        parts = cron_expression.split()
        if len(parts) == 5:
            trigger = CronTrigger(
                minute=parts[0], hour=parts[1], day=parts[2], month=parts[3], day_of_week=parts[4]
            )
            self._scheduler.add_job(
                _enqueue_discovery, trigger=trigger, id=job_id, replace_existing=True, name=f"Discovery: {platform} - {keyword}"
            )

    def _register_session_refresh_job(self, job_id: str, platform: str, interval_hours: int):
        """Internal helper to register session refresh job in APScheduler."""
        def _enqueue_refresh():
            task_queue.enqueue(
                task_type=TaskType.SESSION_REFRESH,
                payload={"platform": platform},
                priority=TaskPriority.HIGH,
            )
        
        self._scheduler.add_job(
            _enqueue_refresh, trigger=IntervalTrigger(hours=interval_hours), id=job_id, replace_existing=True, name=f"Session Refresh: {platform}"
        )
    
    def stop(self):
        """Shutdown scheduler and worker gracefully."""
        self._scheduler.shutdown(wait=False)
        self._worker.stop()
        self._running = False
        logger.info("SchedulerManager: Stopped")
    
    @property
    def is_running(self) -> bool:
        return self._running
    
    # ── Recurring Discovery Schedules ──
    
    def add_discovery_schedule(
        self,
        platform: str,
        keyword: str,
        location: str = "",
        cron_expression: str = "0 9,18 * * 1-5",
        max_jobs: int = 25,
        auto_apply: bool = False,
        min_match_score: int = 70,
        job_id: Optional[str] = None,
    ) -> str:
        """Add a recurring job discovery scan and persist to DB."""
        clean_kw = keyword.replace(" ", "_").lower()
        clean_loc = f"_{location.replace(' ', '_').replace(',', '_').lower()}" if location.strip() else ""
        _job_id = job_id or f"discovery_{platform}_{clean_kw}{clean_loc}"
        
        # 1. Register in APScheduler
        self._register_discovery_job(
            job_id=_job_id,
            platform=platform,
            keyword=keyword,
            location=location,
            cron_expression=cron_expression,
            max_jobs=max_jobs,
            auto_apply=auto_apply,
            min_match_score=min_match_score,
        )
        
        # 2. Persist to DB
        try:
            from backend.app.database import SessionLocal
            from backend.app.scheduler.task_queue import RecurringSchedule
            
            db = SessionLocal()
            try:
                existing = db.query(RecurringSchedule).filter(RecurringSchedule.job_id == _job_id).first()
                if not existing:
                    rec = RecurringSchedule(
                        job_id=_job_id,
                        schedule_type="discovery",
                        platform=platform,
                        keyword=keyword,
                        location=location,
                        cron_expression=cron_expression,
                        max_jobs=max_jobs,
                        auto_apply=1 if auto_apply else 0,
                        min_match_score=min_match_score,
                    )
                    db.add(rec)
                else:
                    existing.cron_expression = cron_expression
                    existing.max_jobs = max_jobs
                    existing.auto_apply = 1 if auto_apply else 0
                    existing.min_match_score = min_match_score
                    existing.enabled = 1
                db.commit()
            finally:
                db.close()
        except Exception as e:
            logger.warning(f"SchedulerManager: Could not persist schedule to DB: {e}")
        
        logger.info(
            f"SchedulerManager: Added and persisted discovery schedule '{_job_id}' "
            f"cron='{cron_expression}' platform='{platform}' keyword='{keyword}' auto_apply={auto_apply}"
        )
        return _job_id
    
    # ── Session Refresh Schedules ──
    
    def add_session_refresh_schedule(
        self,
        platform: str,
        interval_hours: int = 6,
    ) -> str:
        """Schedule periodic session/cookie refresh and persist to DB."""
        job_id = f"session_refresh_{platform}"
        
        self._register_session_refresh_job(
            job_id=job_id,
            platform=platform,
            interval_hours=interval_hours,
        )
        
        # Persist to DB
        try:
            from backend.app.database import SessionLocal
            from backend.app.scheduler.task_queue import RecurringSchedule
            
            db = SessionLocal()
            try:
                existing = db.query(RecurringSchedule).filter(RecurringSchedule.job_id == job_id).first()
                if not existing:
                    rec = RecurringSchedule(
                        job_id=job_id,
                        schedule_type="session_refresh",
                        platform=platform,
                        interval_hours=interval_hours,
                    )
                    db.add(rec)
                else:
                    existing.interval_hours = interval_hours
                    existing.enabled = 1
                db.commit()
            finally:
                db.close()
        except Exception as e:
            logger.warning(f"SchedulerManager: Could not persist session refresh to DB: {e}")
        
        logger.info(
            f"SchedulerManager: Added and persisted session refresh for '{platform}' "
            f"every {interval_hours}h"
        )
        return job_id
    
    # ── One-time Batch Apply ──
    
    def schedule_batch_apply(
        self,
        application_ids: List[int],
        delay_minutes: int = 0,
    ):
        """
        Queue a batch of application IDs for sequential processing.
        Each application is enqueued as a separate task with staggered scheduling.
        """
        base_time = datetime.utcnow() + timedelta(minutes=delay_minutes)
        
        for idx, app_id in enumerate(application_ids):
            # Stagger by 3 minutes between applications
            scheduled_at = base_time + timedelta(minutes=idx * 3)
            
            task_queue.enqueue(
                task_type=TaskType.SINGLE_APPLY,
                payload={"application_id": app_id},
                priority=TaskPriority.NORMAL,
                scheduled_at=scheduled_at,
                deduplicate=True,
            )
        
        logger.info(
            f"SchedulerManager: Scheduled batch apply for "
            f"{len(application_ids)} applications "
            f"(starting in {delay_minutes}min, staggered 3min apart)"
        )
    
    # ── Job Management ──
    
    def remove_schedule(self, job_id: str) -> bool:
        """Remove a scheduled recurring job and disable in DB."""
        try:
            self._scheduler.remove_job(job_id)
            
            # Disable in DB so it doesn't reload on restart
            try:
                from backend.app.database import SessionLocal
                from backend.app.scheduler.task_queue import RecurringSchedule
                
                db = SessionLocal()
                try:
                    rec = db.query(RecurringSchedule).filter(RecurringSchedule.job_id == job_id).first()
                    if rec:
                        rec.enabled = 0
                        db.commit()
                finally:
                    db.close()
            except Exception as db_err:
                logger.warning(f"SchedulerManager: Removed from APScheduler but DB disable failed: {db_err}")
            
            logger.info(f"SchedulerManager: Removed schedule '{job_id}'")
            return True
        except Exception:
            return False

    def remove_all_schedules(self) -> int:
        """Remove all recurring schedules from APScheduler and disable in DB."""
        try:
            jobs = self._scheduler.get_jobs()
            count = len(jobs)
            self._scheduler.remove_all_jobs()
            
            # Disable all in DB
            try:
                from backend.app.database import SessionLocal
                from backend.app.scheduler.task_queue import RecurringSchedule
                
                db = SessionLocal()
                try:
                    db.query(RecurringSchedule).update({RecurringSchedule.enabled: 0})
                    db.commit()
                finally:
                    db.close()
            except Exception as db_err:
                logger.warning(f"SchedulerManager: Removed all jobs from APScheduler but DB update failed: {db_err}")
                
            logger.info(f"SchedulerManager: Removed all {count} schedules.")
            return count
        except Exception as e:
            logger.error(f"SchedulerManager: remove_all_schedules failed: {e}")
            return 0
    
    def list_schedules(self) -> List[Dict[str, Any]]:
        """List all active scheduled jobs."""
        try:
            jobs = self._scheduler.get_jobs()
            res = []
            for job in jobs:
                next_run = getattr(job, "next_run_time", None)
                res.append({
                    "id": job.id,
                    "name": job.name,
                    "next_run": str(next_run) if next_run else None,
                    "trigger": str(job.trigger),
                })
            return res
        except Exception as e:
            logger.warning(f"SchedulerManager: Could not list jobs: {e}")
            return []
    
    def get_status(self) -> Dict[str, Any]:
        """Get overall scheduler status."""
        return {
            "running": self._running,
            "scheduled_jobs": len(self._scheduler.get_jobs()),
            "schedules": self.list_schedules(),
            "queue_stats": task_queue.get_queue_stats(),
            "rate_limits": rate_limiter.get_status(),
        }


# ─────────────────────────────────────────────────────────────────────────────
# Global Singleton
# ─────────────────────────────────────────────────────────────────────────────

scheduler_manager = SchedulerManager()
