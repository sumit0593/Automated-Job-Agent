import logging
from typing import Dict, Any
from playwright.sync_api import Page

from backend.app.automation.ats.base_ats import BaseATS
from backend.app.automation.ats.ats_router import register_ats
from backend.app.automation.browser.playwright_client import PlaywrightClient
from backend.app.automation.question_engine.qa_agent import QuestionAnsweringAgent

logger = logging.getLogger("uvicorn.error")

@register_ats("generic")
class GenericATS(BaseATS):
    """
    Fallback Generic ATS operating as a Workflow Engine.
    Detects current page state (Login, Upload, Questions, Review, Confirmation)
    and executes appropriate actions sequentially.
    """
    def fill_application(
        self,
        page: Page,
        apply_url: str,
        resume_path: str,
        user_profile: Dict[str, Any],
        candidate_profile: Dict[str, Any],
        resume_id: int
    ) -> Dict[str, Any]:
        client = PlaywrightClient(page, "generic")
        qa_agent = QuestionAnsweringAgent()
        logs = []
        def log(msg): logger.info(msg); logs.append(msg)

        log(f"GenericATS: Loading url: {apply_url}...")
        try:
            page.goto(apply_url, timeout=30000, wait_until="domcontentloaded")
            page.wait_for_timeout(3000)
            client.dismiss_popups()

            # Execute Workflow loop (max 10 state transitions)
            current_state = "START"
            for step in range(10):
                client.dismiss_popups()
                page_type = self.detect_page_type(page)
                log(f"GenericATS Step {step + 1}: Detected page type: '{page_type}'")

                if page_type == "login":
                    log("GenericATS: Login screen detected. Awaiting authentication...")
                    # Capture screenshot and wait briefly for manual login
                    client.capture_state_screenshot("login_screen")
                    page.wait_for_timeout(5000)
                    
                elif page_type == "resume_upload":
                    log("GenericATS: Upload screen detected. Uploading resume...")
                    resume_input = page.locator("input[type='file']")
                    if resume_input.count() > 0:
                        resume_input.first.set_input_files(resume_path)
                        client.human_delay(2000, 3000)
                    else:
                        log("GenericATS: No file inputs visible on upload page.")

                elif page_type == "questions":
                    log("GenericATS: Form questionnaire detected. Prefilling fields...")
                    self.fill_questions(page, client, qa_agent, candidate_profile, resume_id, log)
                    client.capture_state_screenshot("questions_filled")
                    
                elif page_type == "review":
                    log("GenericATS: Review screen detected. Pausing for confirmation...")
                    client.capture_state_screenshot("review_screen")
                    # Try to submit or wait
                    submit_btn = page.locator("button:has-text('Submit'), button:has-text('Submit application'), input[type='submit']")
                    if submit_btn.count() > 0 and submit_btn.first.is_enabled():
                        log("GenericATS: Clicking submit...")
                        submit_btn.first.click()
                        page.wait_for_timeout(3000)
                    else:
                        break

                elif page_type == "confirmation":
                    log("GenericATS: Confirmation page detected. Application successful!")
                    client.capture_state_screenshot("confirmation")
                    return {"success": True, "logs": "\n".join(logs), "error": None}

                else:
                    # Unknown layout. Attempt generic form fill
                    log("GenericATS: Directing heuristic prefill on general page...")
                    self.fill_questions(page, client, qa_agent, candidate_profile, resume_id, log)
                    client.capture_state_screenshot("general_page_filled")
                    break
                
                # Check for redirect or loading delay
                page.wait_for_timeout(2000)

            # Verification of success
            confirm_indicators = ["thank you", "received", "submitted", "success", "confirmation"]
            page_text = page.inner_text("body").lower()
            if any(ind in page_text for ind in confirm_indicators):
                log("GenericATS: Post-process verification check passed.")
                return {"success": True, "logs": "\n".join(logs), "error": None}
                
            return {
                "success": False,
                "logs": "\n".join(logs),
                "error": "Generic ATS form prefilled. Human review needed before submitting.",
                "needs_review": True
            }

        except Exception as e:
            client.capture_state_screenshot("generic_ats_error")
            return {"success": False, "logs": "\n".join(logs), "error": str(e)}

    def detect_page_type(self, page: Page) -> str:
        """Analyzes active page elements to categorize page state."""
        url = page.url.lower()
        if "login" in url or "signin" in url:
            return "login"
            
        # Check confirmation indicators
        confirm_selectors = [
            "h1:has-text('Thank')", "h2:has-text('Thank')", "h3:has-text('Thank')",
            "div:has-text('Application Submitted')", "div:has-text('Success')"
        ]
        for sel in confirm_selectors:
            if page.locator(sel).count() > 0:
                return "confirmation"
                
        # Check upload page elements
        file_inputs = page.locator("input[type='file']")
        if file_inputs.count() > 0 and page.locator("input[type='text']").count() < 3:
            return "resume_upload"
            
        # Check review page indicators
        review_selectors = ["h1:has-text('Review')", "h2:has-text('Review')", "button:has-text('Submit application')"]
        for sel in review_selectors:
            if page.locator(sel).count() > 0:
                return "review"
                
        # Question fields
        if page.locator("input[type='text'], select, input[type='radio']").count() > 0:
            return "questions"
            
        return "general"

    def fill_questions(
        self,
        page: Page,
        client: PlaywrightClient,
        qa_agent: QuestionAnsweringAgent,
        candidate_profile: Dict[str, Any],
        resume_id: int,
        log
    ):
        """Standard question prefilling helpers for Generic ATS."""
        # Fill texts
        inputs = page.locator("input[type='text'], input[type='email'], input[type='tel'], textarea")
        for i in range(inputs.count()):
            try:
                inp = inputs.nth(i)
                if not inp.is_visible() or inp.input_value().strip():
                    continue
                
                label = page.evaluate(
                    "(el) => {"
                    "  let parent = el.closest('.form-group, .question, .field-wrapper, div');"
                    "  if (parent) {"
                    "    let lbl = parent.querySelector('label');"
                    "    if (lbl) return lbl.innerText;"
                    "  }"
                    "  return el.placeholder || el.name || '';"
                    "}", inp
                )
                
                answer = qa_agent.generate_answer(resume_id, label, candidate_profile)
                inp.fill(answer)
                log(f"GenericATS: Filled '{label[:30]}...' -> '{answer}'")
                page.wait_for_timeout(200)
            except Exception:
                pass
                
        # Selects
        selects = page.locator("select")
        for i in range(selects.count()):
            try:
                sel = selects.nth(i)
                if sel.is_visible() and not sel.input_value().strip():
                    label = page.evaluate(
                        "(el) => {"
                        "  let parent = el.closest('.form-group, .question, .field-wrapper');"
                        "  if (parent) {"
                        "    let lbl = parent.querySelector('label');"
                        "    if (lbl) return lbl.innerText;"
                        "  }"
                        "  return el.name || '';"
                        "}", sel
                    )
                    
                    answer = qa_agent.generate_answer(resume_id, label, candidate_profile)
                    
                    options = sel.locator("option")
                    matched_val = ""
                    for o_idx in range(options.count()):
                        val = options.nth(o_idx).get_attribute("value")
                        txt = options.nth(o_idx).inner_text().strip().lower()
                        if val and val.strip() and (answer.lower() in txt or txt in answer.lower()):
                            matched_val = val
                            break
                            
                    if matched_val:
                        sel.select_option(value=matched_val)
                        log(f"GenericATS: Selected dropdown for '{label[:30]}...' -> '{matched_val}'")
            except Exception:
                pass
