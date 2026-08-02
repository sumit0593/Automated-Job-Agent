# Job Automation Agent — Architecture & Agent Guide

> **For AI agents, developers, and the scheduler system.**  
> This is the single source of truth for how the system works.

---

## System Overview

```
┌────────────────────────────────────────────────────────────────────────┐
│                      UNIFIED SCHEDULER (1 instance)                    │
│  ┌─────────────────┐  ┌──────────────────┐  ┌───────────────────────┐ │
│  │  discover_jobs  │  │  apply_jobs      │  │  retry_jobs           │ │
│  │  every 30 min   │  │  every 5 min     │  │  every 60 min         │ │
│  │  scrape only    │  │  apply only      │  │  re-queue retryables  │ │
│  └────────┬────────┘  └────────┬─────────┘  └───────────────────────┘ │
└───────────┼────────────────────┼────────────────────────────────────────┘
            │ writes PENDING     │ pops PENDING
            ▼                    ▼
     ┌──────────────┐    ┌───────────────────────────────────────────┐
     │   DB: jobs   │    │              APPLY ENGINE                 │
     │  (MongoDB)   │    │   1. Load page (Playwright)               │
     └──────────────┘    │   2. Router → detect job type            │
                         │   3. Route to handler                    │
                         │   4. Fill form (Hybrid Search)           │
                         │   5. Submit                               │
                         │   6. Verify confirmation                 │
                         │   7. Write status to DB                  │
                         └───────────────────────────────────────────┘
```

---

## Job Lifecycle

```
PENDING → IN_PROGRESS → APPLIED    (confirmed, shows in Completed tab)
                      → FAILED     (with reason, shows in Failed tab)
                      → SKIPPED    (blacklist / already applied)
```

**`APPLIED` status is set ONLY when a confirmation signal is detected on the page.**  
Clicking submit without confirmation → `FAILED` with reason `confirmation_not_found`.

---

## Job Type Routing

Every job is classified before any apply attempt:

| Type | Description | Handler |
|------|-------------|---------|
| `easy_apply` | Naukri one-click apply | `_handle_easy_apply` |
| `external_site` | Redirects to company site | `_handle_external_site` |
| `form_based` | Naukri form with custom Q&A | `_handle_form_based` |
| `skip` | Blacklisted / already applied | Mark `SKIPPED` immediately |
| `unknown` | Type detection failed | Mark `FAILED` → `unknown_job_type` |

**Detection order (priority):**
1. `already_applied` signal on page → `skip`
2. Company in blacklist → `skip`
3. "Apply on company site" text or external href → `external_site`
4. Custom form inputs in apply modal → `form_based`
5. "Easy Apply" / "Quick Apply" button → `easy_apply`
6. None found → `unknown`

---

## Hybrid Search — Profile Q&A

Used when filling external site forms or custom Q&A modals.

```
Question: "How many years of React experience?"
           │
           ├── BM25 (keyword match, weight=0.55)
           │     tokens: ["how", "many", "years", "react", "experience"]
           │
           └── Vector (semantic match, weight=0.45)
                 embedding similarity against profile corpus
                 │
                 ▼
           FUSED SCORE (weighted sum of normalized scores)
                 │
                 ├── score >= 0.35 → return answer
                 └── score <  0.35 → return None → UNANSWERED
```

**Critical rule:** If `answer_question()` returns `None`:
- Do NOT fill the field
- Do NOT guess or hallucinate
- Add question to `unanswered_questions` list on the job record
- Set job status to `FAILED` with reason `unanswered_question`

---

## Scheduler — Why Only One

**Problem:** Multiple scheduler instances cause:
- Same job applied twice (double-apply)
- Overlapping scrapes hitting Naukri rate limits
- Race conditions writing job status

**Solution:** Singleton `UnifiedScheduler` with `max_instances=1` per job.

```python
# WRONG — do not create multiple schedulers
scheduler1 = APScheduler()  # for finding
scheduler2 = APScheduler()  # for applying

# RIGHT — one instance, named jobs
scheduler = UnifiedScheduler(db, config)
# has: discover_jobs | apply_jobs | retry_jobs
```

**Scheduler responsibilities:**
- `discover_jobs` → scrape listings, write PENDING records. **Does not apply.**
- `apply_jobs`    → pop PENDING, route, apply, write result. **Does not discover.**
- `retry_jobs`    → re-queue retryable FAILED jobs.

---

## Failed Tab — What Goes There

| Failure Reason | Retryable | User Action Required |
|----------------|-----------|----------------------|
| `unanswered_question` | ❌ No | Update profile with missing fields |
| `profile_field_missing` | ❌ No | Update profile |
| `captcha_blocked` | ❌ No | Apply manually |
| `already_applied` | ❌ No | None |
| `blacklisted` | ❌ No | None |
| `session_expired` | ✅ Yes (after re-login) | Re-login to Naukri |
| `external_site_timeout` | ✅ Yes | None (auto-retry) |
| `external_site_error` | ✅ Yes | None (auto-retry) |
| `apply_button_not_found` | ✅ Yes | None (auto-retry) |
| `form_submit_failed` | ✅ Yes | None (auto-retry) |
| `confirmation_not_found` | ✅ Yes | Check Naukri manually |
| `modal_detection_failed` | ✅ Yes | None (auto-retry) |

---

## Completed Tab — What Shows There

**Strict rule:** Only jobs matching ALL conditions:
```
status == "applied"
AND applied_at IS NOT NULL
AND applied_at IS a valid datetime
```

Each completed job includes:
- Company, title, applied date
- Job type (easy/external/form)
- Screenshot proof path

---

## Scraper — BeautifulSoup4

**Why bs4 + lxml:**
- `html.parser` (stdlib) — no CSS selectors, slow
- `lxml` backend for bs4 — fastest HTML parser, full CSS selector support
- Playwright fallback — for JS-rendered pages or CAPTCHA interception

**Current usage:**
```python
soup = BeautifulSoup(html, "lxml")   # always use lxml backend
cards = soup.select("article.jobTuple")  # CSS selectors
```

**Anti-bot measures:**
- Random delay between requests (2–5 seconds)
- Rotating user agents
- Session/cookie reuse (Naukri auth)
- Playwright for pages that detect bot headers

---

## Agent Roles

| Agent | File | When Called |
|-------|------|-------------|
| `JOB_CLASSIFIER_AGENT` | `agents/prompts.py` | After page load, before routing |
| `FORM_ANSWER_AGENT` | `agents/prompts.py` | For each form field in external/form jobs |
| `APPLY_DECISION_AGENT` | `agents/prompts.py` | Before attempting apply (match scoring) |
| `FAILURE_ANALYST_AGENT` | `agents/prompts.py` | After failure, to generate UI message |
| `PROFILE_GAP_AGENT` | `agents/prompts.py` | To suggest what profile fields to add |

All agents return **structured JSON only**. No prose. No markdown. No assumptions.

---

## DB Schema — `jobs` Collection

```json
{
  "job_id":               "naukri-12345678",
  "title":                "Senior Software Engineer",
  "company":              "Acme Corp",
  "url":                  "https://naukri.com/job/...",
  "platform":             "naukri",
  "job_type":             "easy_apply | external_site | form_based | skip | unknown",
  "status":               "pending | in_progress | applied | failed | skipped",

  "apply_attempted_at":   "2024-01-15T10:30:00Z",
  "applied_at":           "2024-01-15T10:31:00Z",
  "screenshot_path":      "screenshots/12345678_applied_20240115_103100.png",

  "failure_reason":       "unanswered_question",
  "failure_detail":       "Could not answer: ['current CTC', 'notice period']",
  "unanswered_questions": ["current CTC", "notice period"],
  "retry_count":          1,
  "max_retries":          2,

  "scheduled_at":         "2024-01-15T10:00:00Z",
  "created_at":           "2024-01-15T09:45:00Z",
  "updated_at":           "2024-01-15T10:31:00Z"
}
```

---

## File Structure

```
job_agent/
├── scheduler/
│   └── unified_scheduler.py    ← ONE scheduler, THREE named jobs
├── jobs/
│   ├── models.py               ← JobType, JobStatus, FailureReason enums
│   ├── router.py               ← Job type detection from HTML
│   └── apply_engine.py         ← All apply handlers + confirmation check
├── search/
│   └── hybrid_search.py        ← BM25 + vector profile retrieval
├── scraper/
│   └── naukri_scraper.py       ← bs4 + lxml scraper with anti-bot
├── api/
│   └── routes/
│       └── jobs.py             ← /completed /failed /pending /skipped tabs
├── agents/
│   └── prompts.py              ← System prompts per agent role
└── docs/
    └── AGENT_README.md         ← This file
```

---

## Config Reference

```python
config = {
    "user_id":             "user_abc123",
    "naukri_cookies":      {"nauk_at": "...", "nauk_uid": "..."},
    "auth_storage_path":   "auth/naukri_session.json",
    "headless":            True,
    "user_agent":          "Mozilla/5.0 ...",
    "embedder":            None,   # SentenceTransformer instance or None
    "discover_interval_minutes": 30,
    "apply_interval_minutes":    5,
    "retry_interval_minutes":    60,
    "apply_batch_size":          5,
    "search_params": {
        "keyword":  "software engineer",
        "location": "bangalore",
        "exp":      "2-5",
        "k":        20,
    }
}
```

---

## Required Packages

```
fastapi
uvicorn
motor          # async MongoDB
playwright     # browser automation
httpx          # async HTTP
beautifulsoup4 # HTML parsing
lxml           # bs4 backend
rank-bm25      # BM25 search
apscheduler    # unified scheduler
pydantic       # data models
sentence-transformers  # vector embeddings (optional)
```
