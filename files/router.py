"""
Job Type Router — classifies every job BEFORE attempting to apply.

Decision tree (in priority order):
  1. Blacklisted company?     → SKIP
  2. Already applied?         → SKIP
  3. Has "Apply on company site" button?   → EXTERNAL_SITE
  4. Has custom Q&A modal?    → FORM_BASED
  5. Has one-click apply?     → EASY_APPLY
  6. None matched?            → UNKNOWN (→ failed tab)

WHY THIS MATTERS:
  Without routing, the agent tries to click Naukri's apply button on an
  external site job, fails silently, and marks it as applied anyway.
  Routing ensures each job goes to the right handler with the right strategy.
"""

import re
import logging
from dataclasses import dataclass
from bs4 import BeautifulSoup

from jobs.models import JobType

logger = logging.getLogger(__name__)

# Companies to never apply to (e.g. fake listings, spam)
BLACKLIST: set[str] = {
    "xyz fake company",
    "spam recruiter ltd",
}

# CSS / text selectors for Naukri job page elements
SELECTORS = {
    "easy_apply_btn":    ["button.apply-button", "button[data-job-apply='easy']",
                          "button:contains('Apply')"],
    "external_site_btn": ["a.apply-button-naukri", "a[data-url]",
                          "a:contains('Apply on company site')",
                          "button:contains('Apply on company')"],
    "custom_questions":  ["div.custom-question", "section.job-questions",
                          "form.apply-form input[type!='hidden']"],
}

EXTERNAL_TEXT_SIGNALS = [
    "apply on company site",
    "apply on employer site",
    "visit company website",
    "external application",
]

EASY_APPLY_TEXT_SIGNALS = [
    "easy apply",
    "1-click apply",
    "quick apply",
    "naukri apply",
]


@dataclass
class RouterDecision:
    job_type:  JobType
    reason:    str


class JobRouter:
    """
    Stateless router. Call detect_type() with the page HTML
    or detect_type_from_listing() with raw listing dict.
    """

    # ─── From listing metadata (before page load) ───────────────────────────

    def detect_type_from_listing(self, raw: dict) -> JobType:
        """
        Fast detection from scrape metadata — no browser needed.
        Used by the scheduler during discovery phase.
        """
        company = (raw.get("company") or "").lower().strip()
        if company in BLACKLIST:
            return JobType.SKIP

        tags = [t.lower() for t in raw.get("tags", [])]
        title_lower = (raw.get("title") or "").lower()

        if any(s in tags for s in ["easy apply", "1-click"]):
            return JobType.EASY_APPLY
        if raw.get("apply_url") and raw["apply_url"] != raw.get("url"):
            return JobType.EXTERNAL_SITE
        if "questionnaire" in tags or "screening questions" in tags:
            return JobType.FORM_BASED

        return JobType.UNKNOWN  # will be resolved after page load

    # ─── From page HTML (after browser loads the page) ──────────────────────

    def detect_type_from_html(self, html: str, already_applied: bool = False) -> RouterDecision:
        """
        Definitive type detection from parsed page HTML.
        Call this AFTER the browser has loaded the full job page.
        """
        if already_applied:
            return RouterDecision(JobType.SKIP, "already_applied")

        soup = BeautifulSoup(html, "html.parser")
        page_text = soup.get_text(separator=" ").lower()

        # 1. Check blacklist via page company name
        company_el = soup.select_one("div.company-name, span.comp-name, a.comp-link")
        if company_el:
            company_name = company_el.get_text(strip=True).lower()
            if company_name in BLACKLIST:
                return RouterDecision(JobType.SKIP, f"blacklisted: {company_name}")

        # 2. External site signals (highest priority — can't apply via Naukri)
        if self._has_external_signal(soup, page_text):
            return RouterDecision(JobType.EXTERNAL_SITE, "external_apply_detected")

        # 3. Form-based (custom Q&A present)
        if self._has_custom_questions(soup):
            return RouterDecision(JobType.FORM_BASED, "custom_questions_detected")

        # 4. Easy apply
        if self._has_easy_apply(soup, page_text):
            return RouterDecision(JobType.EASY_APPLY, "easy_apply_button_detected")

        return RouterDecision(JobType.UNKNOWN, "no_apply_mechanism_found")

    # ─── Private Detectors ───────────────────────────────────────────────────

    def _has_external_signal(self, soup: BeautifulSoup, page_text: str) -> bool:
        # Text signal
        if any(s in page_text for s in EXTERNAL_TEXT_SIGNALS):
            return True
        # Link that points offsite
        for sel in SELECTORS["external_site_btn"]:
            try:
                el = soup.select_one(sel)
                if el:
                    href = el.get("href", "") or el.get("data-url", "")
                    if href and "naukri.com" not in href:
                        return True
            except Exception:
                pass
        return False

    def _has_custom_questions(self, soup: BeautifulSoup) -> bool:
        for sel in SELECTORS["custom_questions"]:
            try:
                if soup.select(sel):
                    return True
            except Exception:
                pass
        return False

    def _has_easy_apply(self, soup: BeautifulSoup, page_text: str) -> bool:
        if any(s in page_text for s in EASY_APPLY_TEXT_SIGNALS):
            return True
        for sel in SELECTORS["easy_apply_btn"]:
            try:
                if soup.select_one(sel):
                    return True
            except Exception:
                pass
        return False
