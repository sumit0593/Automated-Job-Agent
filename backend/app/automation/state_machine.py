import time
import logging
from datetime import datetime
from typing import Dict, Any, Optional, List
from sqlalchemy.orm import Session

from backend.app import models
from backend.app.database import SessionLocal
from backend.app.services.browser_manager import launch_persistent_browser, save_session_state
from backend.app.automation.browser.playwright_client import PlaywrightClient
from backend.app.automation.session.session_manager import needs_login, update_session
from backend.app.automation.portal_plugins.registry import get_portal_plugin
from backend.app.automation.ats.ats_router import get_ats_plugin, detect_ats
from backend.app.automation.review.human_review import pause_for_human_review_sync
from backend.app.automation.tracking.tracker import verify_application_success
from backend.app.automation.logging.logger import log_state_transition, add_screenshot_to_log, add_question_to_log
from backend.app.automation.classifier.app_classifier import classify_application_type

logger = logging.getLogger("uvicorn.error")

class ApplicationStateMachine:
    """
    Central Application State Machine governing the job application pipeline.
    Runs entirely within a background thread for Playwright thread-safety.
    """
    def __init__(
        self,
        app_id: int,
        user_profile: Dict[str, Any],
        headful: bool = True,
        enable_human_review: bool = True
    ):
        self.app_id = app_id
        self.user_profile = user_profile
        self.headful = headful
        self.enable_human_review = enable_human_review

    async def run(self) -> Dict[str, Any]:
        """Runs the state machine asynchronously by dispatching to a background thread."""
        import asyncio
        return await asyncio.to_thread(self._run_execution)

    def _run_execution(self) -> Dict[str, Any]:
        """Synchronous core execution running inside the background thread."""
        db = SessionLocal()
        app = db.query(models.Application).filter(models.Application.id == self.app_id).first()
        if not app:
            logger.error(f"StateMachine: Application {self.app_id} not found in DB.")
            db.close()
            return {"success": False, "error": "Application not found"}

        # Initialize status
        app.status = "applying"
        app.logs = "Application state machine initialized.\n"
        db.commit()

        log_state_transition(db, self.app_id, "START", "Starting job application pipeline.")

        pw = None
        context = None
        page = None
        client = None
        
        try:
            # 1. State: PORTAL_DETECTION
            log_state_transition(db, self.app_id, "PORTAL_DETECTION", "Analyzing target job board.")
            url = app.job.url
            portal_name = detect_ats(url)
            
            # 2. State: SESSION_VALIDATION
            log_state_transition(db, self.app_id, "SESSION_VALIDATION", f"Retrieving login credentials for portal '{portal_name}'.")
            cookies = None
            cred = db.query(models.UserCredential).filter(models.UserCredential.platform == portal_name).first()
            if cred and cred.session_cookies:
                cookies = cred.session_cookies

            # 3. Launch browser
            log_state_transition(db, self.app_id, "SESSION_VALIDATION", "Spinning up persistent browser context.")
            pw, context, page = launch_persistent_browser(
                platform=portal_name,
                headless=not self.headful
            )
            client = PlaywrightClient(page, portal_name)
            
            if cookies:
                try:
                    context.add_cookies(cookies)
                except Exception as ce:
                    logger.warning(f"Could not load cookies: {ce}")

            # 4. State: APPLICATION_TYPE
            log_state_transition(db, self.app_id, "APPLICATION_TYPE", "Navigating to job details and classifying application type.")
            page.goto(url, timeout=30000, wait_until="domcontentloaded")
            page.wait_for_timeout(2000)
            client.dismiss_popups()
            
            # Classify application type before clicking Apply
            app_class = classify_application_type(page, url)
            app.application_type = app_class["type"]
            db.commit()
            log_state_transition(
                db, 
                self.app_id, 
                "APPLICATION_TYPE", 
                f"Classified application type as [{app_class['type']}]: {app_class['details']}"
            )
            
            shot_path = client.capture_state_screenshot("job_details")
            if shot_path:
                add_screenshot_to_log(db, self.app_id, "APPLICATION_TYPE", shot_path)

            # Determine whether to use Portal Plugin or ATS Router directly
            portal_plugin = get_portal_plugin(portal_name)
            resume_path = app.tailored_resume_path if app.tailored_resume_path else app.resume.storage_path
            
            if portal_plugin and portal_name in ["linkedin", "naukri"]:
                log_state_transition(db, self.app_id, "APPLICATION_TYPE", f"Handing off execution to Portal Plugin: {portal_name}")
                
                # Check for "Already Applied" first
                if portal_name == "linkedin" and page.locator("span:has-text('Applied'), span:has-text('Already Applied')").count() > 0:
                    log_state_transition(db, self.app_id, "VERIFY_SUCCESS", "Application already submitted historically. Marking complete.")
                    app.status = "applied"
                    app.applied_at = datetime.utcnow()
                    db.commit()
                    return {"success": True, "already_applied": True}

                # Run portal application flow
                res = portal_plugin.apply_job(
                    page=page,
                    apply_url=url,
                    resume_path=resume_path,
                    user_profile=self.user_profile,
                    candidate_profile=app.resume.candidate_profile or {},
                    resume_id=app.resume_id
                )
                
                if res.get("needs_review") and self.enable_human_review:
                    # Capture current question answers
                    detected_questions = []
                    inputs = page.locator("input[type='text'], textarea")
                    for i in range(min(inputs.count(), 10)):
                        try:
                            inp = inputs.nth(i)
                            if inp.is_visible():
                                q_text = page.evaluate("(el) => el.closest('.form-group, .question')?.innerText || el.placeholder || el.name || 'Question'", inp)
                                detected_questions.append({
                                    "question": q_text.strip().replace("\n", " "),
                                    "answer": inp.input_value()
                                })
                        except Exception:
                            pass
                    
                    review_decision = pause_for_human_review_sync(
                        db, self.app_id, detected_questions, [], []
                    )
                    
                    if review_decision == "approve":
                        log_state_transition(db, self.app_id, "SUBMIT", "Resuming apply submit...")
                        submit_btn = page.locator("button:has-text('Submit application'), button:has-text('Submit')")
                        if submit_btn.count() > 0:
                            submit_btn.first.click()
                            page.wait_for_timeout(4000)
                            res = {"success": True}
                        else:
                            res = {"success": False, "error": "Submit button not found after review approval."}
                    elif review_decision == "reject":
                        app.status = "rejected"
                        db.commit()
                        return {"success": False, "error": "Rejected by user"}
                    else:
                        app.status = "failed"
                        db.commit()
                        return {"success": False, "error": "Skipped by user"}

                if res.get("success"):
                    log_state_transition(db, self.app_id, "VERIFY_SUCCESS", "Verifying application outcome.")
                    verification = verify_application_success(page, portal_name)
                    if verification["success"]:
                        log_state_transition(db, self.app_id, "STORE_RESULT", "Application successful. Logging proof.")
                        app.status = "applied"
                        app.applied_at = datetime.utcnow()
                        if verification["application_id"]:
                            app.logs += f"\nConfirmation Reference ID: {verification['application_id']}"
                    else:
                        log_state_transition(db, self.app_id, "STORE_RESULT", "Success confirmation not matched, but submit clicked.")
                        app.status = "applied"
                    db.commit()
                    return {"success": True}
                else:
                    raise Exception(res.get("error", "Portal apply failed."))

            else:
                # 5. State: ATS_DETECTION
                log_state_transition(db, self.app_id, "ATS_DETECTION", "Determining underlying ATS portal provider.")
                ats_name = detect_ats(url)
                log_state_transition(db, self.app_id, "ATS_DETECTION", f"Routed to ATS Adaptor: {ats_name}")
                
                ats_plugin = get_ats_plugin(url)
                
                # 6. State: RESUME_UPLOAD, 7. State: COVER_LETTER, 8. State: QUESTION_ANSWERING
                log_state_transition(db, self.app_id, "QUESTION_ANSWERING", "Filing application fields and uploading resume.")
                res = ats_plugin.fill_application(
                    page=page,
                    apply_url=url,
                    resume_path=resume_path,
                    user_profile=self.user_profile,
                    candidate_profile=app.resume.candidate_profile or {},
                    resume_id=app.resume_id
                )
                
                if res.get("needs_review") and self.enable_human_review:
                    detected_questions = []
                    inputs = page.locator("input[type='text'], textarea")
                    for i in range(min(inputs.count(), 10)):
                        try:
                            inp = inputs.nth(i)
                            if inp.is_visible():
                                q_text = page.evaluate("(el) => el.closest('.form-group, .question')?.innerText || el.placeholder || el.name || 'Question'", inp)
                                detected_questions.append({
                                    "question": q_text.strip().replace("\n", " "),
                                    "answer": inp.input_value()
                                })
                        except Exception:
                            pass
                    
                    review_decision = pause_for_human_review_sync(
                        db, self.app_id, detected_questions, [], []
                    )
                    
                    if review_decision == "approve":
                        log_state_transition(db, self.app_id, "SUBMIT", "Submitting application...")
                        submit_btn = page.locator("button:has-text('Submit'), button:has-text('Submit application'), input[type='submit']")
                        if submit_btn.count() > 0:
                            submit_btn.first.click()
                            page.wait_for_timeout(4000)
                            res = {"success": True}
                        else:
                            res = {"success": False, "error": "Submit button not found."}
                    elif review_decision == "reject":
                        app.status = "rejected"
                        db.commit()
                        return {"success": False, "error": "Rejected by user"}
                    else:
                        app.status = "failed"
                        db.commit()
                        return {"success": False, "error": "Skipped by user"}

                if res.get("success"):
                    log_state_transition(db, self.app_id, "VERIFY_SUCCESS", "Verifying application outcome.")
                    verification = verify_application_success(page, ats_name)
                    if verification["success"]:
                        log_state_transition(db, self.app_id, "STORE_RESULT", "Application submitted successfully!")
                        app.status = "applied"
                        app.applied_at = datetime.utcnow()
                    else:
                        log_state_transition(db, self.app_id, "STORE_RESULT", "Form filled. Please check the browser to submit manually if needed.")
                        app.status = "applied"
                    db.commit()
                    return {"success": True}
                else:
                    raise Exception(res.get("error", "ATS application fill failed."))

        except Exception as e:
            logger.error(f"StateMachine: Error running pipeline for app {self.app_id}: {e}")
            log_state_transition(db, self.app_id, "STORE_RESULT", f"Automation failed: {e}")
            
            # Error Recovery Backoff check
            if app.error_recovery_retries < 2:
                app.error_recovery_retries += 1
                db.commit()
                log_state_transition(db, self.app_id, "START", f"Retrying pipeline. Attempt {app.error_recovery_retries + 1}/3...")
                db.close()
                return self._run_execution()
                
            app.status = "failed"
            db.commit()
            return {"success": False, "error": str(e)}
            
        finally:
            if context and portal_name in ["linkedin", "naukri"]:
                try:
                    state_cookies = context.cookies()
                    update_session(db, portal_name, state_cookies)
                except Exception:
                    pass
            
            if context:
                try:
                    context.close()
                except Exception:
                    pass
            if pw:
                try:
                    pw.stop()
                except Exception:
                    pass
            db.close()
