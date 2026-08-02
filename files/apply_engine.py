"""
Apply Engine — routes each job to the correct handler, verifies confirmation.

CRITICAL RULES:
  1. APPLIED status is set ONLY after a confirmation signal is detected.
     (e.g. "Application submitted", "You've applied", redirect to confirmation page)
  2. If confirmation is NOT detected → status = FAILED, reason = CONFIRMATION_NOT_FOUND
  3. If a form question can't be answered by profile → FAILED, reason = UNANSWERED_QUESTION
     The question is logged. Never guessed. Never skipped silently.
  4. Every failure must have a FailureReason + failure_detail string.
  5. Take a screenshot after every apply attempt (proof for Applied tab / debug for Failed tab).
"""

import asyncio
import logging
from dataclasses import dataclass, field
from pathlib import Path
from datetime import datetime

from playwright.async_api import async_playwright, Page, Browser

from jobs.models import JobType, JobStatus, FailureReason
from jobs.router import JobRouter
from search.hybrid_search import HybridSearcher

logger = logging.getLogger(__name__)

SCREENSHOT_DIR = Path("screenshots")
SCREENSHOT_DIR.mkdir(exist_ok=True)


@dataclass
class ApplyResult:
    status:               JobStatus
    failure_reason:       FailureReason | None = None
    failure_detail:       str | None           = None
    screenshot_path:      str | None           = None
    unanswered_questions: list[str]            = field(default_factory=list)


class ApplyEngine:

    def __init__(self, db, config: dict):
        self.db     = db
        self.config = config
        self.router = JobRouter()

    async def apply(self, job_doc: dict) -> ApplyResult:
        """
        Entry point. Routes job to the right handler.
        Always returns ApplyResult — never raises.
        """
        profile = await self.db.profiles.find_one({"user_id": self.config["user_id"]})
        if not profile:
            return ApplyResult(
                status         = JobStatus.FAILED,
                failure_reason = FailureReason.PROFILE_FIELD_MISSING,
                failure_detail = "No profile found for user",
            )

        searcher = HybridSearcher(profile, embedder=self.config.get("embedder"))

        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=self.config.get("headless", True))
            context = await browser.new_context(
                user_agent    = self.config.get("user_agent", "Mozilla/5.0"),
                viewport      = {"width": 1280, "height": 800},
                storage_state = self.config.get("auth_storage_path"),  # saved session
            )
            page = await context.new_page()

            try:
                # Load job page
                await page.goto(job_doc["url"], wait_until="domcontentloaded", timeout=30000)
                await asyncio.sleep(1.5)

                html = await page.content()

                # Check already applied
                already_applied = await self._is_already_applied(page)
                if already_applied:
                    return ApplyResult(
                        status         = JobStatus.SKIPPED,
                        failure_reason = FailureReason.ALREADY_APPLIED,
                        failure_detail = "Already applied — detected on page load",
                        screenshot_path= await self._screenshot(page, job_doc["job_id"], "skipped"),
                    )

                # Resolve job type (definitive, from real page)
                decision = self.router.detect_type_from_html(html)
                job_type = decision.job_type

                # Update job_type in DB now that we know for sure
                await self.db.jobs.update_one(
                    {"job_id": job_doc["job_id"]},
                    {"$set": {"job_type": job_type.value}}
                )

                # Route to handler
                if job_type == JobType.EASY_APPLY:
                    result = await self._handle_easy_apply(page, job_doc)
                elif job_type == JobType.EXTERNAL_SITE:
                    result = await self._handle_external_site(page, job_doc, searcher)
                elif job_type == JobType.FORM_BASED:
                    result = await self._handle_form_based(page, job_doc, searcher)
                elif job_type == JobType.SKIP:
                    result = ApplyResult(status=JobStatus.SKIPPED, failure_reason=FailureReason.BLACKLISTED)
                else:
                    result = ApplyResult(
                        status         = JobStatus.FAILED,
                        failure_reason = FailureReason.UNKNOWN_JOB_TYPE,
                        failure_detail = f"Router decision: {decision.reason}",
                    )

                # Attach screenshot to every result
                if not result.screenshot_path:
                    result.screenshot_path = await self._screenshot(
                        page, job_doc["job_id"], result.status.value
                    )

                return result

            except Exception as e:
                logger.error(f"[ApplyEngine] Unhandled exception for {job_doc['job_id']}: {e}", exc_info=True)
                try:
                    ss = await self._screenshot(page, job_doc["job_id"], "error")
                except Exception:
                    ss = None
                return ApplyResult(
                    status         = JobStatus.FAILED,
                    failure_reason = FailureReason.UNKNOWN_JOB_TYPE,
                    failure_detail = str(e),
                    screenshot_path= ss,
                )
            finally:
                await browser.close()

    # ─── Handlers ────────────────────────────────────────────────────────────

    async def _handle_easy_apply(self, page: Page, job_doc: dict) -> ApplyResult:
        """Naukri one-click apply. Verifies confirmation text after click."""
        try:
            btn = await page.wait_for_selector(
                "button.apply-button, button[data-job-apply], "
                "button:text('Apply'), button:text('Easy Apply')",
                timeout=8000,
            )
            if not btn:
                return ApplyResult(
                    status         = JobStatus.FAILED,
                    failure_reason = FailureReason.APPLY_BUTTON_NOT_FOUND,
                    failure_detail = "Apply button not found on page",
                )

            await btn.click()
            await asyncio.sleep(2)

            confirmed = await self._check_confirmation(page)
            if confirmed:
                return ApplyResult(status=JobStatus.APPLIED)

            return ApplyResult(
                status         = JobStatus.FAILED,
                failure_reason = FailureReason.CONFIRMATION_NOT_FOUND,
                failure_detail = "Clicked apply but no confirmation signal found",
            )

        except Exception as e:
            return ApplyResult(
                status         = JobStatus.FAILED,
                failure_reason = FailureReason.FORM_SUBMIT_FAILED,
                failure_detail = str(e),
            )

    async def _handle_external_site(
        self, page: Page, job_doc: dict, searcher: HybridSearcher
    ) -> ApplyResult:
        """
        Clicks through to external site. Fills form using hybrid search.
        If any question is unanswered → FAILED (no guessing).
        """
        try:
            # Click through to external site
            ext_link = await page.wait_for_selector(
                "a.apply-button-naukri, a[data-url], a:text('Apply on company site')",
                timeout=8000,
            )
            if not ext_link:
                return ApplyResult(
                    status         = JobStatus.FAILED,
                    failure_reason = FailureReason.APPLY_BUTTON_NOT_FOUND,
                    failure_detail = "External apply link not found",
                )

            async with page.expect_popup() as popup_info:
                await ext_link.click()
            ext_page = await popup_info.value

            await ext_page.wait_for_load_state("domcontentloaded", timeout=20000)
            await asyncio.sleep(2)

            # Fill the external form using hybrid search
            fill_result = await self._fill_form(ext_page, searcher)
            if fill_result["unanswered"]:
                return ApplyResult(
                    status                = JobStatus.FAILED,
                    failure_reason        = FailureReason.UNANSWERED_QUESTION,
                    failure_detail        = f"Could not answer: {fill_result['unanswered']}",
                    unanswered_questions  = fill_result["unanswered"],
                    screenshot_path       = await self._screenshot(ext_page, job_doc["job_id"], "unanswered"),
                )

            # Submit
            await self._submit_form(ext_page)
            await asyncio.sleep(3)

            confirmed = await self._check_confirmation(ext_page)
            if confirmed:
                return ApplyResult(
                    status          = JobStatus.APPLIED,
                    screenshot_path = await self._screenshot(ext_page, job_doc["job_id"], "applied"),
                )

            return ApplyResult(
                status         = JobStatus.FAILED,
                failure_reason = FailureReason.CONFIRMATION_NOT_FOUND,
                failure_detail = "External form submitted but no confirmation",
                screenshot_path= await self._screenshot(ext_page, job_doc["job_id"], "no_confirm"),
            )

        except asyncio.TimeoutError:
            return ApplyResult(
                status         = JobStatus.FAILED,
                failure_reason = FailureReason.EXTERNAL_SITE_TIMEOUT,
                failure_detail = "External site timed out",
            )
        except Exception as e:
            return ApplyResult(
                status         = JobStatus.FAILED,
                failure_reason = FailureReason.EXTERNAL_SITE_ERROR,
                failure_detail = str(e),
            )

    async def _handle_form_based(
        self, page: Page, job_doc: dict, searcher: HybridSearcher
    ) -> ApplyResult:
        """Naukri multi-step form with custom questions."""
        try:
            # Open apply modal
            btn = await page.wait_for_selector(
                "button.apply-button, button:text('Apply')", timeout=8000
            )
            await btn.click()
            await asyncio.sleep(1.5)

            fill_result = await self._fill_form(page, searcher)
            if fill_result["unanswered"]:
                # Close modal, don't submit
                await self._dismiss_modal(page)
                return ApplyResult(
                    status                = JobStatus.FAILED,
                    failure_reason        = FailureReason.UNANSWERED_QUESTION,
                    failure_detail        = f"Unanswered: {fill_result['unanswered']}",
                    unanswered_questions  = fill_result["unanswered"],
                )

            await self._submit_form(page)
            await asyncio.sleep(2)

            if await self._check_confirmation(page):
                return ApplyResult(status=JobStatus.APPLIED)

            return ApplyResult(
                status         = JobStatus.FAILED,
                failure_reason = FailureReason.CONFIRMATION_NOT_FOUND,
                failure_detail = "Form submitted but no confirmation signal",
            )

        except Exception as e:
            return ApplyResult(
                status         = JobStatus.FAILED,
                failure_reason = FailureReason.FORM_SUBMIT_FAILED,
                failure_detail = str(e),
            )

    # ─── Form Filler ─────────────────────────────────────────────────────────

    async def _fill_form(self, page: Page, searcher: HybridSearcher) -> dict:
        """
        Finds all visible form inputs, answers each via hybrid search.
        Returns {"filled": [...], "unanswered": [...]}
        """
        filled      = []
        unanswered  = []

        inputs = await page.query_selector_all("input:visible, textarea:visible, select:visible")
        for el in inputs:
            input_type = await el.get_attribute("type") or "text"
            if input_type in ("hidden", "submit", "button"):
                continue

            # Get the question label
            label = await self._get_label(page, el)
            if not label:
                continue

            result = searcher.answer_question(label)
            if result is None:
                unanswered.append(label)
                logger.warning(f"[FormFiller] No answer for: '{label}'")
                continue

            try:
                tag = await el.evaluate("el => el.tagName.toLowerCase()")
                if tag == "select":
                    await el.select_option(label=result.answer)
                elif input_type == "checkbox":
                    should_check = result.answer.lower() in ("yes", "true", "1")
                    if should_check:
                        await el.check()
                else:
                    await el.fill(result.answer)
                filled.append(label)
            except Exception as e:
                logger.warning(f"[FormFiller] Could not fill '{label}': {e}")
                unanswered.append(label)

        return {"filled": filled, "unanswered": unanswered}

    async def _get_label(self, page: Page, el) -> str | None:
        """Extract question label for a form element."""
        # Try aria-label
        label = await el.get_attribute("aria-label")
        if label:
            return label.strip()
        # Try associated <label>
        el_id = await el.get_attribute("id")
        if el_id:
            label_el = await page.query_selector(f"label[for='{el_id}']")
            if label_el:
                return (await label_el.inner_text()).strip()
        # Try placeholder
        placeholder = await el.get_attribute("placeholder")
        if placeholder:
            return placeholder.strip()
        # Try name attribute
        name = await el.get_attribute("name")
        return name

    async def _submit_form(self, page: Page):
        submit = await page.query_selector(
            "button[type='submit'], input[type='submit'], "
            "button:text('Submit'), button:text('Apply')"
        )
        if submit:
            await submit.click()

    async def _dismiss_modal(self, page: Page):
        close = await page.query_selector(
            "button.close-modal, button[aria-label='Close'], button:text('Cancel')"
        )
        if close:
            await close.click()

    # ─── Verification ─────────────────────────────────────────────────────────

    async def _check_confirmation(self, page: Page) -> bool:
        """
        Looks for any signal that the application was successfully submitted.
        Returns True only on CONFIRMED signal. Never assumes success.
        """
        CONFIRMATION_SIGNALS = [
            "application submitted",
            "successfully applied",
            "you've applied",
            "you have applied",
            "thank you for applying",
            "application received",
            "your application has been sent",
        ]
        try:
            text = (await page.inner_text("body")).lower()
            return any(s in text for s in CONFIRMATION_SIGNALS)
        except Exception:
            return False

    async def _is_already_applied(self, page: Page) -> bool:
        APPLIED_SIGNALS = ["applied", "you have already applied", "application sent"]
        try:
            text = (await page.inner_text("body")).lower()
            return any(s in text for s in APPLIED_SIGNALS)
        except Exception:
            return False

    # ─── Screenshot ───────────────────────────────────────────────────────────

    async def _screenshot(self, page: Page, job_id: str, label: str) -> str | None:
        try:
            ts   = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
            path = str(SCREENSHOT_DIR / f"{job_id}_{label}_{ts}.png")
            await page.screenshot(path=path, full_page=True)
            return path
        except Exception as e:
            logger.warning(f"Screenshot failed: {e}")
            return None
