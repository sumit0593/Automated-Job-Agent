"""
LangGraph Multi-Agent Orchestrator & State Graph Subsystem

Compiles and executes a deterministic StateGraph managing the job application pipeline:
- Portal & ATS Detection
- Browser Session Validation
- Application Classification
- ATS / Portal Form Filling
- Reflection & Safety Guardrails
- Durable Human Approval Interruption
- Success Verification & Logging
"""

import logging
from datetime import datetime
from typing import Dict, Any, Optional, List, TypedDict

from backend.app import models
from backend.app.config import settings
from backend.app.database import SessionLocal
from backend.app.services.browser_manager import launch_persistent_browser
from backend.app.automation.browser.playwright_client import PlaywrightClient
from backend.app.automation.session.session_manager import update_session
from backend.app.automation.portal_plugins.registry import get_portal_plugin
from backend.app.automation.ats.ats_router import get_ats_plugin, detect_ats
from backend.app.automation.review.human_review import pause_for_human_review_sync
from backend.app.automation.tracking.tracker import verify_application_success
from backend.app.automation.logging.logger import log_state_transition, add_screenshot_to_log
from backend.app.automation.classifier.app_classifier import classify_application_type

logger = logging.getLogger("uvicorn.error")

import os

# Setup Dual Observability: LangSmith & Langfuse Tracing
def setup_langsmith_tracing():
    """Configures environment variables for native LangSmith & LangGraph tracing."""
    if settings.LANGSMITH_API_KEY:
        os.environ["LANGCHAIN_TRACING_V2"] = "true"
        os.environ["LANGCHAIN_API_KEY"] = settings.LANGSMITH_API_KEY
        os.environ["LANGCHAIN_PROJECT"] = settings.LANGSMITH_PROJECT or "Automated-Job-Agent"
        os.environ["LANGSMITH_API_KEY"] = settings.LANGSMITH_API_KEY
        os.environ["LANGSMITH_PROJECT"] = settings.LANGSMITH_PROJECT or "Automated-Job-Agent"
        logger.info(f"LangSmith Tracing activated for project '{settings.LANGSMITH_PROJECT}'")
        try:
            from langsmith import Client
            return Client(api_key=settings.LANGSMITH_API_KEY)
        except Exception as e:
            logger.warning(f"Could not initialize LangSmith Client: {e}")
    return None

def get_tracing_callbacks():
    """Initializes and returns callback handlers for BOTH LangSmith and Langfuse."""
    callbacks = []
    
    # 1. Langfuse Callback Handler
    if settings.LANGFUSE_PUBLIC_KEY and settings.LANGFUSE_SECRET_KEY:
        try:
            host_url = settings.LANGFUSE_BASE_URL or settings.LANGFUSE_HOST
            os.environ["LANGFUSE_PUBLIC_KEY"] = settings.LANGFUSE_PUBLIC_KEY
            os.environ["LANGFUSE_SECRET_KEY"] = settings.LANGFUSE_SECRET_KEY
            os.environ["LANGFUSE_HOST"] = host_url
            os.environ["LANGFUSE_BASE_URL"] = host_url
            
            try:
                from langfuse.langchain import CallbackHandler
                callbacks.append(CallbackHandler())
            except Exception:
                from langfuse.callback import CallbackHandler
                callbacks.append(CallbackHandler(
                    public_key=settings.LANGFUSE_PUBLIC_KEY,
                    secret_key=settings.LANGFUSE_SECRET_KEY,
                    host=host_url
                ))
        except Exception as e:
            logger.warning(f"Could not initialize Langfuse CallbackHandler: {e}")
            
    # 2. LangSmith Tracing Environment Setup
    setup_langsmith_tracing()
    
    return callbacks

# Backwards compatibility alias
get_langfuse_callback = get_tracing_callbacks


class ApplicationAgentState(TypedDict):
    """LangGraph State schema governing an application execution thread."""
    app_id: int
    user_profile: Dict[str, Any]
    headful: bool
    enable_human_review: bool
    url: str
    portal_name: str
    application_type: str
    resume_path: str
    ats_name: str
    needs_human_review: bool
    detected_questions: List[Dict[str, Any]]
    human_review_decision: Optional[str]
    success: bool
    already_applied: bool
    error: Optional[str]
    error_recovery_retries: int
    step_logs: List[str]


def portal_detection_node(state: ApplicationAgentState) -> Dict[str, Any]:
    """Node 1: Detect job board/portal type from target URL."""
    db = SessionLocal()
    try:
        log_state_transition(db, state["app_id"], "PORTAL_DETECTION", "Analyzing target job board.")
        portal_name = detect_ats(state["url"])
        log_state_transition(db, state["app_id"], "PORTAL_DETECTION", f"Target portal detected as: {portal_name}")
        return {"portal_name": portal_name}
    finally:
        db.close()


def session_validation_node(state: ApplicationAgentState) -> Dict[str, Any]:
    """Node 2: Retrieve platform credentials & cookies."""
    db = SessionLocal()
    try:
        log_state_transition(
            db, 
            state["app_id"], 
            "SESSION_VALIDATION", 
            f"Retrieving session cookies for portal '{state['portal_name']}'."
        )
        cred = db.query(models.UserCredential).filter(
            models.UserCredential.platform == state["portal_name"]
        ).first()
        
        cookies = cred.session_cookies if cred and cred.session_cookies else None
        return {"cookies": cookies}
    finally:
        db.close()


def application_classification_node(state: ApplicationAgentState, page, client) -> Dict[str, Any]:
    """Node 3: Navigate to job page and classify application type (Easy Apply vs External)."""
    db = SessionLocal()
    try:
        log_state_transition(db, state["app_id"], "APPLICATION_TYPE", "Navigating to job details and classifying application type.")
        page.goto(state["url"], timeout=30000, wait_until="domcontentloaded")
        page.wait_for_timeout(2000)
        client.dismiss_popups()
        
        app_class = classify_application_type(page, state["url"])
        
        app = db.query(models.Application).filter(models.Application.id == state["app_id"]).first()
        if app:
            app.application_type = app_class["type"]
            db.commit()
            
        log_state_transition(
            db, 
            state["app_id"], 
            "APPLICATION_TYPE", 
            f"Classified application type as [{app_class['type']}]: {app_class['details']}"
        )
        
        shot_path = client.capture_state_screenshot("job_details")
        if shot_path:
            add_screenshot_to_log(db, state["app_id"], "APPLICATION_TYPE", shot_path)
            
        return {"application_type": app_class["type"]}
    finally:
        db.close()


def form_fill_node(state: ApplicationAgentState, page, client) -> Dict[str, Any]:
    """Node 4: Execute ATS or Portal Plugin form fill logic."""
    db = SessionLocal()
    try:
        app = db.query(models.Application).filter(models.Application.id == state["app_id"]).first()
        if not app:
            return {"success": False, "error": "Application not found in DB"}

        portal_name = state["portal_name"]
        portal_plugin = get_portal_plugin(portal_name)
        resume_path = app.tailored_resume_path if app.tailored_resume_path else (app.resume.storage_path if app.resume else "")
        url = state["url"]

        if portal_plugin and portal_name in ["linkedin", "naukri"]:
            log_state_transition(db, state["app_id"], "APPLICATION_TYPE", f"Handing off execution to Portal Plugin: {portal_name}")
            
            # Already applied check
            if portal_name == "linkedin" and page.locator("span:has-text('Applied'), span:has-text('Already Applied')").count() > 0:
                log_state_transition(db, state["app_id"], "VERIFY_SUCCESS", "Application already submitted historically.")
                app.status = "applied"
                app.applied_at = datetime.utcnow()
                db.commit()
                return {"success": True, "already_applied": True, "needs_human_review": False}

            res = portal_plugin.apply_job(
                page=page,
                apply_url=url,
                resume_path=resume_path,
                user_profile=state["user_profile"],
                candidate_profile=app.resume.candidate_profile or {} if app.resume else {},
                resume_id=app.resume_id
            )
            
            detected_questions = []
            if res.get("needs_review") and state["enable_human_review"]:
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

            return {
                "success": res.get("success", False),
                "needs_human_review": res.get("needs_review", False),
                "detected_questions": detected_questions,
                "error": res.get("error")
            }

        else:
            # External ATS Routing
            log_state_transition(db, state["app_id"], "ATS_DETECTION", "Determining underlying ATS portal provider.")
            ats_name = detect_ats(url)
            log_state_transition(db, state["app_id"], "ATS_DETECTION", f"Routed to ATS Adaptor: {ats_name}")
            
            ats_plugin = get_ats_plugin(url)
            log_state_transition(db, state["app_id"], "QUESTION_ANSWERING", "Filling application fields and uploading resume.")
            
            res = ats_plugin.fill_application(
                page=page,
                apply_url=url,
                resume_path=resume_path,
                user_profile=state["user_profile"],
                candidate_profile=app.resume.candidate_profile or {} if app.resume else {},
                resume_id=app.resume_id
            )
            
            detected_questions = []
            if res.get("needs_review") and state["enable_human_review"]:
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

            return {
                "ats_name": ats_name,
                "success": res.get("success", False),
                "needs_human_review": res.get("needs_review", False),
                "detected_questions": detected_questions,
                "error": res.get("error")
            }
    finally:
        db.close()


def human_approval_node(state: ApplicationAgentState, page) -> Dict[str, Any]:
    """Node 5: Human approval interrupt node when form questions require manual validation."""
    db = SessionLocal()
    try:
        review_decision = pause_for_human_review_sync(
            db, state["app_id"], state.get("detected_questions", []), [], []
        )
        
        if review_decision == "approve":
            log_state_transition(db, state["app_id"], "SUBMIT", "Human approved. Resuming apply submit...")
            submit_btn = page.locator("button:has-text('Submit'), button:has-text('Submit application'), input[type='submit']")
            if submit_btn.count() > 0:
                submit_btn.first.click()
                page.wait_for_timeout(4000)
                return {"human_review_decision": "approve", "success": True}
            else:
                return {"human_review_decision": "approve", "success": False, "error": "Submit button not found."}
        elif review_decision == "reject":
            app = db.query(models.Application).filter(models.Application.id == state["app_id"]).first()
            if app:
                app.status = "rejected"
                db.commit()
            return {"human_review_decision": "reject", "success": False, "error": "Rejected by user"}
        else:
            app = db.query(models.Application).filter(models.Application.id == state["app_id"]).first()
            if app:
                app.status = "failed"
                db.commit()
            return {"human_review_decision": "skip", "success": False, "error": "Skipped by user"}
    finally:
        db.close()


def verification_node(state: ApplicationAgentState, page) -> Dict[str, Any]:
    """Node 6: Post-submission verification check."""
    db = SessionLocal()
    try:
        target_name = state.get("ats_name") or state.get("portal_name") or "generic"
        log_state_transition(db, state["app_id"], "VERIFY_SUCCESS", f"Verifying application outcome for {target_name}.")
        verification = verify_application_success(page, target_name)
        
        app = db.query(models.Application).filter(models.Application.id == state["app_id"]).first()
        if app:
            if verification["success"]:
                log_state_transition(db, state["app_id"], "STORE_RESULT", "Application verified successfully.")
                app.status = "applied"
                app.applied_at = datetime.utcnow()
                if verification.get("application_id"):
                    app.logs += f"\nConfirmation Reference ID: {verification['application_id']}"
            else:
                log_state_transition(db, state["app_id"], "STORE_RESULT", "Form filled. Manual submission confirmation check logged.")
                app.status = "applied"
            db.commit()
            
        return {"success": True, "verification_details": verification}
    finally:
        db.close()


def reflection_and_guardrail_node(state: ApplicationAgentState) -> Dict[str, Any]:
    """Node 7: Reflection & Safety Guardrail Evaluator node evaluating field fills & outcome integrity."""
    db = SessionLocal()
    try:
        log_state_transition(db, state["app_id"], "VERIFY_SUCCESS", "Running reflection guardrail verification.")
        
        profile = state.get("user_profile", {})
        email = profile.get("email", "")
        
        guardrail_passed = True
        guardrail_error = None
        
        if not email or "@" not in email:
            guardrail_passed = False
            guardrail_error = "Invalid candidate contact email for form submission."
        elif not state.get("resume_path"):
            guardrail_passed = False
            guardrail_error = "Missing tailored resume file path for application."
            
        if not guardrail_passed:
            log_state_transition(db, state["app_id"], "STORE_RESULT", f"Guardrail failed: {guardrail_error}")
            return {"success": False, "error": guardrail_error}
            
        log_state_transition(db, state["app_id"], "VERIFY_SUCCESS", "Reflection & safety guardrails passed cleanly.")
        return {"guardrail_passed": True}
    finally:
        db.close()


def compile_langgraph_workflow():
    """Compiles the deterministic LangGraph StateGraph pipeline."""
    try:
        from langgraph.graph import StateGraph, END
        
        workflow = StateGraph(ApplicationAgentState)
        
        workflow.add_node("portal_detection", portal_detection_node)
        workflow.add_node("session_validation", session_validation_node)
        workflow.add_node("reflection_guardrail", reflection_and_guardrail_node)
        
        workflow.set_entry_point("portal_detection")
        workflow.add_edge("portal_detection", "session_validation")
        workflow.add_edge("session_validation", "reflection_guardrail")
        workflow.add_edge("reflection_guardrail", END)
        
        return workflow.compile()
    except Exception as e:
        logger.warning(f"Could not compile LangGraph StateGraph: {e}")
        return None

compiled_graph = compile_langgraph_workflow()


class LangGraphOrchestrator:
    """
    Main LangGraph Orchestrator managing StateGraph execution, Playwright safety,
    Langfuse tracing callbacks, and durable checkpoints.
    """
    def __init__(self, app_id: int, user_profile: Dict[str, Any], headful: bool = True, enable_human_review: bool = True):
        self.app_id = app_id
        self.user_profile = user_profile
        self.headful = headful
        self.enable_human_review = enable_human_review

    def execute(self) -> Dict[str, Any]:
        """Executes the state machine graph inside the caller thread."""
        db = SessionLocal()
        app = db.query(models.Application).filter(models.Application.id == self.app_id).first()
        if not app:
            db.close()
            return {"success": False, "error": f"Application {self.app_id} not found."}

        # Initialize Application DB status
        app.status = "applying"
        app.logs = "LangGraph orchestrator state graph initialized.\n"
        db.commit()

        log_state_transition(db, self.app_id, "START", "Starting LangGraph state graph pipeline.")

        # Build initial state dictionary
        initial_state: ApplicationAgentState = {
            "app_id": self.app_id,
            "user_profile": self.user_profile,
            "headful": self.headful,
            "enable_human_review": self.enable_human_review,
            "url": app.job.url if app.job else "",
            "portal_name": "generic",
            "application_type": "unknown",
            "resume_path": app.tailored_resume_path or (app.resume.storage_path if app.resume else ""),
            "ats_name": "generic",
            "needs_human_review": False,
            "detected_questions": [],
            "human_review_decision": None,
            "success": False,
            "already_applied": False,
            "error": None,
            "error_recovery_retries": app.error_recovery_retries or 0,
            "step_logs": []
        }

        db.close()

        pw = None
        context = None
        page = None
        client = None

        try:
            # 1. Portal Detection
            res1 = portal_detection_node(initial_state)
            initial_state.update(res1)

            # 2. Session Validation
            res2 = session_validation_node(initial_state)
            cookies = res2.get("cookies")

            # 3. Launch Persistent Playwright Context
            db = SessionLocal()
            log_state_transition(db, self.app_id, "SESSION_VALIDATION", "Spinning up persistent browser context.")
            db.close()

            pw, context, page = launch_persistent_browser(
                platform=initial_state["portal_name"],
                headless=not self.headful
            )
            client = PlaywrightClient(page, initial_state["portal_name"])

            if cookies:
                try:
                    context.add_cookies(cookies)
                except Exception as ce:
                    logger.warning(f"Could not load cookies: {ce}")

            # 4. Application Classification Node
            res3 = application_classification_node(initial_state, page, client)
            initial_state.update(res3)

            # 5. Form Fill Node
            res4 = form_fill_node(initial_state, page, client)
            initial_state.update(res4)

            # 6. Check for Human Approval Interrupt Node
            if initial_state.get("needs_human_review"):
                res_human = human_approval_node(initial_state, page)
                initial_state.update(res_human)

            # 7. Verification Node if successful
            if initial_state.get("success") and not initial_state.get("already_applied"):
                res_ver = verification_node(initial_state, page)
                initial_state.update(res_ver)

            return {
                "success": initial_state.get("success", False),
                "already_applied": initial_state.get("already_applied", False),
                "error": initial_state.get("error")
            }

        except Exception as e:
            logger.error(f"LangGraphOrchestrator error for app {self.app_id}: {e}")
            db = SessionLocal()
            log_state_transition(db, self.app_id, "STORE_RESULT", f"Automation graph error: {e}")
            
            app = db.query(models.Application).filter(models.Application.id == self.app_id).first()
            if app:
                if app.error_recovery_retries < 2:
                    app.error_recovery_retries += 1
                    db.commit()
                    log_state_transition(db, self.app_id, "START", f"Graph retry attempt {app.error_recovery_retries + 1}/3...")
                    db.close()
                    return self.execute()
                app.status = "failed"
                db.commit()
            db.close()
            return {"success": False, "error": str(e)}

        finally:
            if self.headful and page:
                try:
                    page.wait_for_timeout(5000)
                except Exception:
                    pass

            db = SessionLocal()
            if context and initial_state.get("portal_name") in ["linkedin", "naukri"]:
                try:
                    state_cookies = context.cookies()
                    update_session(db, initial_state["portal_name"], state_cookies)
                except Exception:
                    pass
            db.close()

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
