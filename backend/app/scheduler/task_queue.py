"""
Task Queue — SQLite-backed persistent job queue for asynchronous task execution.

Supports:
  - Task creation with priority levels (URGENT, HIGH, NORMAL, LOW, BATCH)
  - Deduplication by task type + payload hash
  - Retry with exponential backoff
  - Task status tracking (PENDING, RUNNING, COMPLETED, FAILED, CANCELLED)
  - Stale task cleanup

Uses the existing SQLite database to avoid adding Redis as a dependency
for local development. Can be upgraded to Redis/Celery for production.
"""

import json
import time
import hashlib
import logging
from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, Any, Optional, List
from sqlalchemy import Column, Integer, String, Text, Float, DateTime, text
from sqlalchemy.orm import Session

from backend.app.database import engine, Base, SessionLocal

logger = logging.getLogger("uvicorn.error")


# ─────────────────────────────────────────────────────────────────────────────
# Task Priority & Status Enums
# ─────────────────────────────────────────────────────────────────────────────

class TaskPriority(str, Enum):
    URGENT = "urgent"   # Execute immediately (e.g., session refresh)
    HIGH = "high"       # High priority (e.g., hot job application)
    NORMAL = "normal"   # Default priority
    LOW = "low"         # Background tasks (e.g., scraping)
    BATCH = "batch"     # Batch processing (e.g., bulk tailoring)


class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class TaskType(str, Enum):
    DISCOVERY_SCAN = "discovery_scan"       # Scrape jobs from a platform
    BATCH_APPLY = "batch_apply"             # Apply to a list of matched jobs
    SINGLE_APPLY = "single_apply"           # Apply to one specific job
    RESUME_TAILOR = "resume_tailor"         # Tailor resume for a job match
    SESSION_REFRESH = "session_refresh"     # Refresh browser cookies/sessions
    MATCH_PIPELINE = "match_pipeline"       # Run matching pipeline for a resume


# ─────────────────────────────────────────────────────────────────────────────
# SQLAlchemy Model for Task Queue
# ─────────────────────────────────────────────────────────────────────────────

class ScheduledTask(Base):
    """Persistent task record in the database."""
    __tablename__ = "scheduled_tasks"

    id = Column(Integer, primary_key=True, index=True)
    task_type = Column(String, index=True, nullable=False)
    priority = Column(String, default=TaskPriority.NORMAL.value, index=True)
    status = Column(String, default=TaskStatus.PENDING.value, index=True)
    payload = Column(Text, nullable=True)  # JSON serialized task parameters
    payload_hash = Column(String, nullable=True, index=True)  # For deduplication
    result = Column(Text, nullable=True)  # JSON serialized result
    error = Column(Text, nullable=True)
    retry_count = Column(Integer, default=0)
    max_retries = Column(Integer, default=3)
    scheduled_at = Column(DateTime, nullable=True)  # When to execute (None = ASAP)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class RecurringSchedule(Base):
    """Persistent recurring schedule rule (cron or interval)."""
    __tablename__ = "recurring_schedules"

    job_id = Column(String, primary_key=True, index=True)
    schedule_type = Column(String, nullable=False)  # "discovery" or "session_refresh"
    platform = Column(String, nullable=False)
    keyword = Column(String, nullable=True)
    location = Column(String, nullable=True)
    cron_expression = Column(String, nullable=True)
    interval_hours = Column(Integer, nullable=True)
    max_jobs = Column(Integer, default=25)
    auto_apply = Column(Integer, default=0)
    min_match_score = Column(Integer, default=70)
    enabled = Column(Integer, default=1)
    created_at = Column(DateTime, default=datetime.utcnow)


# Ensure tables exist
try:
    ScheduledTask.__table__.create(engine, checkfirst=True)
    RecurringSchedule.__table__.create(engine, checkfirst=True)
except Exception as e:
    logger.warning(f"TaskQueue: Could not create database tables: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# Task Queue Manager
# ─────────────────────────────────────────────────────────────────────────────

class TaskQueue:
    """
    SQLite-backed task queue for persistent async job processing.
    
    Usage:
        queue = TaskQueue()
        
        # Enqueue a task
        task_id = queue.enqueue(
            task_type=TaskType.DISCOVERY_SCAN,
            payload={"platform": "linkedin", "keyword": "AI Engineer"},
            priority=TaskPriority.NORMAL,
        )
        
        # Dequeue next task for processing
        task = queue.dequeue()
        if task:
            queue.mark_running(task.id)
            # ... process ...
            queue.mark_completed(task.id, result={"jobs_found": 15})
    """
    
    def enqueue(
        self,
        task_type: TaskType,
        payload: Optional[Dict[str, Any]] = None,
        priority: TaskPriority = TaskPriority.NORMAL,
        scheduled_at: Optional[datetime] = None,
        max_retries: int = 3,
        deduplicate: bool = True,
    ) -> Optional[int]:
        """
        Add a new task to the queue.
        
        Args:
            task_type: Type of task to execute
            payload: Task parameters (JSON-serializable)
            priority: Execution priority
            scheduled_at: When to execute (None = ASAP)
            max_retries: Maximum retry attempts
            deduplicate: If True, skip if identical pending task exists
        
        Returns:
            Task ID, or None if deduplicated.
        """
        db = SessionLocal()
        try:
            payload_json = json.dumps(payload or {}, sort_keys=True)
            payload_hash = hashlib.md5(
                f"{task_type.value}:{payload_json}".encode()
            ).hexdigest()
            
            # Deduplication check
            if deduplicate:
                existing = db.query(ScheduledTask).filter(
                    ScheduledTask.payload_hash == payload_hash,
                    ScheduledTask.status.in_([
                        TaskStatus.PENDING.value,
                        TaskStatus.RUNNING.value,
                    ])
                ).first()
                
                if existing:
                    logger.info(
                        f"TaskQueue: Skipping duplicate task "
                        f"type={task_type.value} (existing id={existing.id})"
                    )
                    return None
            
            task = ScheduledTask(
                task_type=task_type.value,
                priority=priority.value,
                status=TaskStatus.PENDING.value,
                payload=payload_json,
                payload_hash=payload_hash,
                max_retries=max_retries,
                scheduled_at=scheduled_at,
            )
            db.add(task)
            db.commit()
            db.refresh(task)
            
            logger.info(
                f"TaskQueue: Enqueued task id={task.id} type={task_type.value} "
                f"priority={priority.value} scheduled_at={scheduled_at or 'ASAP'}"
            )
            return task.id
        except Exception as e:
            db.rollback()
            logger.error(f"TaskQueue: Failed to enqueue task: {e}")
            return None
        finally:
            db.close()
    
    def dequeue(self) -> Optional[ScheduledTask]:
        """
        Fetch the next task to process.
        
        Priority order: URGENT > HIGH > NORMAL > LOW > BATCH
        Within same priority: oldest first (FIFO).
        Respects scheduled_at (skips future-scheduled tasks).
        """
        db = SessionLocal()
        try:
            now = datetime.utcnow()
            priority_order = {
                TaskPriority.URGENT.value: 0,
                TaskPriority.HIGH.value: 1,
                TaskPriority.NORMAL.value: 2,
                TaskPriority.LOW.value: 3,
                TaskPriority.BATCH.value: 4,
            }
            
            tasks = db.query(ScheduledTask).filter(
                ScheduledTask.status == TaskStatus.PENDING.value,
            ).all()
            
            # Filter: only tasks whose scheduled_at is in the past (or null)
            eligible = [
                t for t in tasks
                if t.scheduled_at is None or t.scheduled_at <= now
            ]
            
            if not eligible:
                return None
            
            # Sort by priority, then by created_at
            eligible.sort(
                key=lambda t: (
                    priority_order.get(t.priority, 99),
                    t.created_at or datetime.min,
                )
            )
            
            return eligible[0]
        except Exception as e:
            logger.error(f"TaskQueue: Dequeue failed: {e}")
            return None
        finally:
            db.close()
    
    def mark_running(self, task_id: int):
        """Mark a task as currently being processed."""
        db = SessionLocal()
        try:
            task = db.query(ScheduledTask).filter(ScheduledTask.id == task_id).first()
            if task:
                task.status = TaskStatus.RUNNING.value
                task.started_at = datetime.utcnow()
                db.commit()
        except Exception as e:
            db.rollback()
            logger.error(f"TaskQueue: mark_running failed for task {task_id}: {e}")
        finally:
            db.close()
    
    def mark_completed(self, task_id: int, result: Optional[Dict] = None):
        """Mark a task as successfully completed."""
        db = SessionLocal()
        try:
            task = db.query(ScheduledTask).filter(ScheduledTask.id == task_id).first()
            if task:
                task.status = TaskStatus.COMPLETED.value
                task.completed_at = datetime.utcnow()
                task.result = json.dumps(result or {})
                db.commit()
                logger.info(f"TaskQueue: Task {task_id} completed successfully.")
        except Exception as e:
            db.rollback()
            logger.error(f"TaskQueue: mark_completed failed for task {task_id}: {e}")
        finally:
            db.close()
    
    def mark_failed(self, task_id: int, error: str):
        """Mark a task as failed. Re-enqueues if retries remain."""
        db = SessionLocal()
        try:
            task = db.query(ScheduledTask).filter(ScheduledTask.id == task_id).first()
            if not task:
                return
            
            task.retry_count += 1
            task.error = error
            
            if task.retry_count < task.max_retries:
                # Exponential backoff: 30s, 120s, 480s
                backoff = 30 * (4 ** (task.retry_count - 1))
                task.status = TaskStatus.PENDING.value
                task.scheduled_at = datetime.utcnow() + timedelta(seconds=backoff)
                logger.info(
                    f"TaskQueue: Task {task_id} failed (attempt {task.retry_count}/"
                    f"{task.max_retries}). Retrying in {backoff}s."
                )
            else:
                task.status = TaskStatus.FAILED.value
                task.completed_at = datetime.utcnow()
                logger.error(
                    f"TaskQueue: Task {task_id} permanently failed after "
                    f"{task.max_retries} attempts. Error: {error}"
                )
            
            db.commit()
        except Exception as e:
            db.rollback()
            logger.error(f"TaskQueue: mark_failed error for task {task_id}: {e}")
        finally:
            db.close()
    
    def cancel(self, task_id: int) -> bool:
        """Cancel a pending or running task."""
        db = SessionLocal()
        try:
            task = db.query(ScheduledTask).filter(ScheduledTask.id == task_id).first()
            if task and task.status in [TaskStatus.PENDING.value, TaskStatus.RUNNING.value]:
                task.status = TaskStatus.CANCELLED.value
                task.completed_at = datetime.utcnow()
                db.commit()
                logger.info(f"TaskQueue: Task {task_id} cancelled.")
                return True
            return False
        except Exception as e:
            db.rollback()
            logger.error(f"TaskQueue: cancel failed for task {task_id}: {e}")
            return False
        finally:
            db.close()
    
    def get_task(self, task_id: int) -> Optional[Dict]:
        """Get task details by ID."""
        db = SessionLocal()
        try:
            task = db.query(ScheduledTask).filter(ScheduledTask.id == task_id).first()
            if not task:
                return None
            return {
                "id": task.id,
                "task_type": task.task_type,
                "priority": task.priority,
                "status": task.status,
                "payload": json.loads(task.payload) if task.payload else {},
                "result": json.loads(task.result) if task.result else None,
                "error": task.error,
                "retry_count": task.retry_count,
                "max_retries": task.max_retries,
                "scheduled_at": str(task.scheduled_at) if task.scheduled_at else None,
                "created_at": str(task.created_at),
                "started_at": str(task.started_at) if task.started_at else None,
                "completed_at": str(task.completed_at) if task.completed_at else None,
            }
        except Exception as e:
            logger.error(f"TaskQueue: get_task failed: {e}")
            return None
        finally:
            db.close()
    
    def list_tasks(
        self,
        status: Optional[str] = None,
        task_type: Optional[str] = None,
        limit: int = 50,
    ) -> List[Dict]:
        """List tasks with optional filtering."""
        db = SessionLocal()
        try:
            query = db.query(ScheduledTask)
            if status:
                query = query.filter(ScheduledTask.status == status)
            if task_type:
                query = query.filter(ScheduledTask.task_type == task_type)
            
            tasks = query.order_by(ScheduledTask.created_at.desc()).limit(limit).all()
            
            return [
                {
                    "id": t.id,
                    "task_type": t.task_type,
                    "priority": t.priority,
                    "status": t.status,
                    "retry_count": t.retry_count,
                    "created_at": str(t.created_at),
                    "scheduled_at": str(t.scheduled_at) if t.scheduled_at else None,
                    "error": t.error,
                }
                for t in tasks
            ]
        except Exception as e:
            logger.error(f"TaskQueue: list_tasks failed: {e}")
            return []
        finally:
            db.close()
    
    def clear_history(self, include_all: bool = False) -> int:
        """
        Delete completed, failed, and cancelled tasks from DB history.
        If include_all is True, deletes all tasks including pending.
        """
        db = SessionLocal()
        try:
            query = db.query(ScheduledTask)
            if not include_all:
                query = query.filter(
                    ScheduledTask.status.in_([
                        TaskStatus.COMPLETED.value,
                        TaskStatus.FAILED.value,
                        TaskStatus.CANCELLED.value,
                    ])
                )
            count = query.delete(synchronize_session=False)
            db.commit()
            logger.info(f"TaskQueue: Cleared {count} task execution records.")
            return count
        except Exception as e:
            db.rollback()
            logger.error(f"TaskQueue: clear_history failed: {e}")
            return 0
        finally:
            db.close()

    def cleanup_stale(self, stale_minutes: int = 30):
        """Mark stale RUNNING tasks (no progress) as FAILED for retry."""
        db = SessionLocal()
        try:
            cutoff = datetime.utcnow() - timedelta(minutes=stale_minutes)
            stale_tasks = db.query(ScheduledTask).filter(
                ScheduledTask.status == TaskStatus.RUNNING.value,
                ScheduledTask.started_at < cutoff,
            ).all()
            
            for task in stale_tasks:
                task.retry_count += 1
                if task.retry_count < task.max_retries:
                    task.status = TaskStatus.PENDING.value
                    task.error = f"Stale: no progress for {stale_minutes} minutes"
                else:
                    task.status = TaskStatus.FAILED.value
                    task.completed_at = datetime.utcnow()
                    task.error = f"Stale and max retries exhausted"
            
            if stale_tasks:
                db.commit()
                logger.info(f"TaskQueue: Cleaned up {len(stale_tasks)} stale tasks.")
        except Exception as e:
            db.rollback()
            logger.error(f"TaskQueue: cleanup_stale failed: {e}")
        finally:
            db.close()
    
    def get_queue_stats(self) -> Dict[str, Any]:
        """Get queue health metrics."""
        db = SessionLocal()
        try:
            total = db.query(ScheduledTask).count()
            pending = db.query(ScheduledTask).filter(
                ScheduledTask.status == TaskStatus.PENDING.value
            ).count()
            running = db.query(ScheduledTask).filter(
                ScheduledTask.status == TaskStatus.RUNNING.value
            ).count()
            completed = db.query(ScheduledTask).filter(
                ScheduledTask.status == TaskStatus.COMPLETED.value
            ).count()
            failed = db.query(ScheduledTask).filter(
                ScheduledTask.status == TaskStatus.FAILED.value
            ).count()
            
            return {
                "total": total,
                "pending": pending,
                "running": running,
                "completed": completed,
                "failed": failed,
                "health": "healthy" if running <= 5 else "busy",
            }
        except Exception as e:
            logger.error(f"TaskQueue: get_queue_stats failed: {e}")
            return {"error": str(e)}
        finally:
            db.close()


# ─────────────────────────────────────────────────────────────────────────────
# Global Singleton
# ─────────────────────────────────────────────────────────────────────────────

task_queue = TaskQueue()
