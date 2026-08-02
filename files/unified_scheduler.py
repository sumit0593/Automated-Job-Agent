"""
Unified Scheduler — ONE scheduler, TWO jobs only.

WHY YOU HAD TOO MANY SCHEDULERS:
  Each feature (find jobs, apply, retry, cleanup) likely had its own
  APScheduler/cron instance. Over time these multiplied. They overlap,
  fire simultaneously, and double-apply or double-scrape.

FIX: Single AsyncIOScheduler with named, non-overlapping jobs.
  ┌─────────────────────────────────────────────────────────┐
  │  SCHEDULER (1 instance)                                 │
  │   ├── job: "discover"  → scrape Naukri, enqueue jobs    │
  │   ├── job: "apply"     → pop queue, route, apply        │
  │   └── job: "retry"     → re-queue failed jobs           │
  └─────────────────────────────────────────────────────────┘

SCHEDULER DOES NOT APPLY DIRECTLY.
  It enqueues job IDs. The apply engine processes the queue.
  This prevents double-apply on overlapping scheduler fires.
"""

import asyncio
import logging
from datetime import datetime
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.jobstores.memory import MemoryJobStore
from apscheduler.executors.asyncio import AsyncIOExecutor
from apscheduler.events import EVENT_JOB_ERROR, EVENT_JOB_EXECUTED

from jobs.models import JobStatus, FailureReason
from scraper.naukri_scraper import NaukriScraper
from jobs.router import JobRouter
from jobs.apply_engine import ApplyEngine

logger = logging.getLogger(__name__)


class UnifiedScheduler:
    """
    Single scheduler instance. Must be initialized once at app startup.
    Import and call .start() from main.py — nowhere else.
    """

    _instance: "UnifiedScheduler | None" = None

    def __new__(cls, *args, **kwargs):
        # Enforce singleton — prevents accidental double-scheduler
        if cls._instance is not None:
            logger.warning("UnifiedScheduler already exists. Returning existing instance.")
            return cls._instance
        cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self, db, config: dict):
        if hasattr(self, "_initialized"):
            return
        self._initialized = True

        self.db        = db
        self.config    = config
        self.scraper   = NaukriScraper(config)
        self.router    = JobRouter()
        self.engine    = ApplyEngine(db, config)

        # In-memory set to prevent double-enqueue between scheduler ticks
        self._in_progress_ids: set[str] = set()

        self.scheduler = AsyncIOScheduler(
            jobstores  = {"default": MemoryJobStore()},
            executors  = {"default": AsyncIOExecutor()},
            job_defaults = {
                "coalesce":    True,   # merge missed fires into one
                "max_instances": 1,    # CRITICAL: never run same job twice
                "misfire_grace_time": 60,
            },
        )

        self.scheduler.add_listener(self._on_job_event, EVENT_JOB_ERROR | EVENT_JOB_EXECUTED)

    # ─── Lifecycle ─────────────────────────────────────────────────────────────

    def start(self):
        """Call once from main.py lifespan. Not from routers or services."""
        discover_interval = self.config.get("discover_interval_minutes", 30)
        apply_interval    = self.config.get("apply_interval_minutes", 5)
        retry_interval    = self.config.get("retry_interval_minutes", 60)

        # Job 1: Discover new jobs (scrape + enqueue only, never apply)
        self.scheduler.add_job(
            self._discover_jobs,
            trigger  = "interval",
            minutes  = discover_interval,
            id       = "discover_jobs",
            name     = "Naukri Job Discovery",
            replace_existing = True,
        )

        # Job 2: Apply to queued jobs (dequeue + route + apply)
        self.scheduler.add_job(
            self._process_apply_queue,
            trigger  = "interval",
            minutes  = apply_interval,
            id       = "apply_jobs",
            name     = "Apply Queue Processor",
            replace_existing = True,
        )

        # Job 3: Retry eligible failed jobs
        self.scheduler.add_job(
            self._retry_failed_jobs,
            trigger  = "interval",
            minutes  = retry_interval,
            id       = "retry_jobs",
            name     = "Failed Job Retry",
            replace_existing = True,
        )

        self.scheduler.start()
        logger.info(
            f"Scheduler started | discover={discover_interval}m "
            f"| apply={apply_interval}m | retry={retry_interval}m"
        )

    def stop(self):
        self.scheduler.shutdown(wait=False)
        logger.info("Scheduler stopped.")

    # ─── Job 1: Discover ───────────────────────────────────────────────────────

    async def _discover_jobs(self):
        """
        ONLY discovers and enqueues. Does NOT apply.
        Writes JobRecord with status=PENDING to DB.
        Skips jobs already in DB (by platform job_id).
        """
        logger.info("[Discover] Starting job scrape...")
        try:
            raw_jobs = await self.scraper.fetch_job_listings()
            new_count = 0

            for raw in raw_jobs:
                exists = await self.db.jobs.find_one({"job_id": raw["job_id"]})
                if exists:
                    continue

                job_type = self.router.detect_type_from_listing(raw)

                record = {
                    "job_id":       raw["job_id"],
                    "title":        raw["title"],
                    "company":      raw["company"],
                    "url":          raw["url"],
                    "platform":     "naukri",
                    "job_type":     job_type.value,
                    "status":       JobStatus.PENDING.value,
                    "created_at":   datetime.utcnow(),
                    "updated_at":   datetime.utcnow(),
                    "retry_count":  0,
                }
                await self.db.jobs.insert_one(record)
                new_count += 1

            logger.info(f"[Discover] Enqueued {new_count} new jobs.")
        except Exception as e:
            logger.error(f"[Discover] Failed: {e}", exc_info=True)

    # ─── Job 2: Apply Queue ────────────────────────────────────────────────────

    async def _process_apply_queue(self):
        """
        Pops PENDING jobs. Routes by type. Applies. Writes result.
        max_instances=1 ensures this never overlaps itself.
        """
        logger.info("[Apply] Processing queue...")
        batch_size = self.config.get("apply_batch_size", 5)

        pending = await self.db.jobs.find(
            {"status": JobStatus.PENDING.value}
        ).limit(batch_size).to_list(batch_size)

        if not pending:
            logger.info("[Apply] Queue empty.")
            return

        for job_doc in pending:
            job_id = str(job_doc["_id"])
            if job_id in self._in_progress_ids:
                continue

            self._in_progress_ids.add(job_id)
            try:
                await self._apply_single(job_doc)
            finally:
                self._in_progress_ids.discard(job_id)

    async def _apply_single(self, job_doc: dict):
        """Route one job to the right handler and record outcome."""
        jid = str(job_doc["_id"])
        await self.db.jobs.update_one(
            {"_id": job_doc["_id"]},
            {"$set": {"status": JobStatus.IN_PROGRESS.value,
                      "apply_attempted_at": datetime.utcnow(),
                      "updated_at": datetime.utcnow()}}
        )

        result = await self.engine.apply(job_doc)

        update = {
            "status":     result.status.value,
            "updated_at": datetime.utcnow(),
        }
        if result.status == JobStatus.APPLIED:
            update["applied_at"]      = datetime.utcnow()
            update["screenshot_path"] = result.screenshot_path

        if result.status == JobStatus.FAILED:
            update["failure_reason"]       = result.failure_reason.value if result.failure_reason else None
            update["failure_detail"]       = result.failure_detail
            update["unanswered_questions"] = result.unanswered_questions

        await self.db.jobs.update_one({"_id": job_doc["_id"]}, {"$set": update})
        logger.info(f"[Apply] Job {jid} → {result.status.value}")

    # ─── Job 3: Retry ──────────────────────────────────────────────────────────

    async def _retry_failed_jobs(self):
        """
        Re-queues failed jobs that are retryable and haven't exceeded max_retries.
        Does NOT retry: CAPTCHA, already_applied, blacklisted, unknown_job_type.
        """
        NON_RETRYABLE = {
            FailureReason.CAPTCHA_BLOCKED.value,
            FailureReason.ALREADY_APPLIED.value,
            FailureReason.BLACKLISTED.value,
            FailureReason.UNKNOWN_JOB_TYPE.value,
            FailureReason.UNANSWERED_QUESTION.value,   # won't fix without profile update
            FailureReason.PROFILE_FIELD_MISSING.value,
        }

        candidates = await self.db.jobs.find({
            "status":       JobStatus.FAILED.value,
            "failure_reason": {"$nin": list(NON_RETRYABLE)},
            "$expr":        {"$lt": ["$retry_count", "$max_retries"]},
        }).to_list(20)

        for job in candidates:
            await self.db.jobs.update_one(
                {"_id": job["_id"]},
                {"$set":  {"status": JobStatus.PENDING.value, "updated_at": datetime.utcnow()},
                 "$inc":  {"retry_count": 1}}
            )
            logger.info(f"[Retry] Re-queued job {job['_id']}")

    # ─── Event Listener ────────────────────────────────────────────────────────

    def _on_job_event(self, event):
        if event.exception:
            logger.error(f"[Scheduler] Job {event.job_id} crashed: {event.exception}")
        else:
            logger.debug(f"[Scheduler] Job {event.job_id} completed OK")
