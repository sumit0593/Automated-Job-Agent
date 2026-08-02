"""
Core job models — single source of truth for all job states, types, and failure reasons.
Every module imports from here. Never define job-related types elsewhere.
"""

from enum import Enum
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field
import uuid


# ─── Job Type ──────────────────────────────────────────────────────────────────
class JobType(str, Enum):
    """
    Routing decision made BEFORE any apply attempt.

    EASY_APPLY    → Naukri one-click apply. No external redirect.
    EXTERNAL_SITE → Redirects to company site. Full form fill required.
    FORM_BASED    → Multi-step Naukri form with custom questions.
    SKIP          → Blacklisted company / already applied / irrelevant.
    UNKNOWN       → Type detection failed. Route to failed tab immediately.
    """
    EASY_APPLY    = "easy_apply"
    EXTERNAL_SITE = "external_site"
    FORM_BASED    = "form_based"
    SKIP          = "skip"
    UNKNOWN       = "unknown"


# ─── Job Status ────────────────────────────────────────────────────────────────
class JobStatus(str, Enum):
    """
    Lifecycle: PENDING → IN_PROGRESS → APPLIED | FAILED | SKIPPED
    APPLIED is only set after CONFIRMED submission (not just button click).
    """
    PENDING     = "pending"
    IN_PROGRESS = "in_progress"
    APPLIED     = "applied"       # ← confirmed only
    FAILED      = "failed"
    SKIPPED     = "skipped"


# ─── Failure Reasons ───────────────────────────────────────────────────────────
class FailureReason(str, Enum):
    """
    Granular failure codes. Shown in the Failed tab.
    Agent MUST set one of these — never fail silently.
    """
    CAPTCHA_BLOCKED         = "captcha_blocked"
    SESSION_EXPIRED         = "session_expired"
    UNANSWERED_QUESTION     = "unanswered_question"    # profile data missing
    PROFILE_FIELD_MISSING   = "profile_field_missing"  # BM25 score below threshold
    EXTERNAL_SITE_TIMEOUT   = "external_site_timeout"
    EXTERNAL_SITE_ERROR     = "external_site_error"
    MODAL_DETECTION_FAILED  = "modal_detection_failed"
    ALREADY_APPLIED         = "already_applied"
    APPLY_BUTTON_NOT_FOUND  = "apply_button_not_found"
    FORM_SUBMIT_FAILED      = "form_submit_failed"
    CONFIRMATION_NOT_FOUND  = "confirmation_not_found"  # applied but unconfirmed
    SCRAPE_FAILED           = "scrape_failed"
    BLACKLISTED             = "blacklisted"
    UNKNOWN_JOB_TYPE        = "unknown_job_type"
    SCHEDULER_ERROR         = "scheduler_error"


# ─── Core Job Record ───────────────────────────────────────────────────────────
class JobRecord(BaseModel):
    id:              str         = Field(default_factory=lambda: str(uuid.uuid4()))
    job_id:          str         # platform job ID (Naukri job ID)
    title:           str
    company:         str
    url:             str
    platform:        str         = "naukri"
    job_type:        JobType     = JobType.UNKNOWN
    status:          JobStatus   = JobStatus.PENDING

    # Apply tracking
    apply_attempted_at:  Optional[datetime] = None
    applied_at:          Optional[datetime] = None     # set ONLY on confirmation
    screenshot_path:     Optional[str]      = None     # proof screenshot

    # Failure tracking
    failure_reason:  Optional[FailureReason] = None
    failure_detail:  Optional[str]           = None    # human-readable detail
    unanswered_questions: list[str]          = Field(default_factory=list)
    retry_count:     int                     = 0
    max_retries:     int                     = 2

    # Scheduler
    scheduled_at:    Optional[datetime] = None
    created_at:      datetime           = Field(default_factory=datetime.utcnow)
    updated_at:      datetime           = Field(default_factory=datetime.utcnow)

    class Config:
        use_enum_values = True


class JobSummary(BaseModel):
    """Lightweight model for tab listing. Never expose full record to UI list."""
    id:             str
    title:          str
    company:        str
    status:         JobStatus
    job_type:       JobType
    failure_reason: Optional[FailureReason] = None
    failure_detail: Optional[str]           = None
    applied_at:     Optional[datetime]      = None
    screenshot_path: Optional[str]          = None
