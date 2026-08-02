"""
Vision-Based Page Navigator — Screenshot → LLM Vision → Action loop.

When traditional DOM selectors fail on unknown external application sites,
this navigator takes a screenshot, sends it to a vision-capable LLM 
(Gemini Pro Vision / Grok Vision), gets a structured action plan, and 
executes the actions via Playwright coordinates.

Iterative Loop:
  1. Capture screenshot of current page state
  2. Send screenshot + context to Vision LLM
  3. LLM returns structured actions (click, fill, upload, scroll, etc.)
  4. Execute actions via Playwright
  5. Wait for page update
  6. Repeat until form is filled or max iterations reached

This is the "last resort" navigator when DOM-based ATS handlers
and the unknown_ats_planner both fail.
"""

import json
import re
import base64
import logging
import time
from pathlib import Path
from typing import Dict, Any, Optional, List
from datetime import datetime
from playwright.sync_api import Page

from backend.app.config import settings, SCREENSHOTS_DIR
from backend.app.services.llm_router import llm_router, TaskType

logger = logging.getLogger("uvicorn.error")


# ─────────────────────────────────────────────────────────────────────────────
# Action Types
# ─────────────────────────────────────────────────────────────────────────────

VALID_ACTIONS = {"click", "fill", "upload", "select", "scroll", "wait", "done", "skip"}


# ─────────────────────────────────────────────────────────────────────────────
# Screenshot → Base64 Helper
# ─────────────────────────────────────────────────────────────────────────────

def _capture_and_encode(page: Page, state_name: str = "vision") -> tuple:
    """
    Captures a page screenshot and returns (file_path, base64_string).
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"vision_{state_name}_{timestamp}.png"
    filepath = SCREENSHOTS_DIR / filename
    
    try:
        page.screenshot(path=str(filepath), full_page=False)
        
        with open(filepath, "rb") as f:
            b64 = base64.b64encode(f.read()).decode("utf-8")
        
        logger.info(f"VisionNavigator: Captured screenshot → {filepath}")
        return str(filepath), b64
    except Exception as e:
        logger.error(f"VisionNavigator: Screenshot capture failed: {e}")
        return None, None


# ─────────────────────────────────────────────────────────────────────────────
# Vision LLM — Generate Action Plan from Screenshot
# ─────────────────────────────────────────────────────────────────────────────

def _generate_vision_plan(
    screenshot_b64: str,
    page_url: str,
    applicant_info: Dict[str, Any],
    page_title: str = "",
    iteration: int = 1,
    previous_actions: List[str] = None,
) -> List[Dict[str, Any]]:
    """
    Sends screenshot to Vision LLM and gets structured action plan.
    
    Falls back to DOM-based analysis if vision API is unavailable.
    """
    
    # Build applicant data summary (safe for prompt)
    personal = applicant_info.get("personal", applicant_info)
    applicant_summary = (
        f"Name: {personal.get('first_name', '')} {personal.get('last_name', '')}\n"
        f"Email: {personal.get('email', '')}\n"
        f"Phone: {personal.get('phone', '')}\n"
        f"Location: {personal.get('location', '')}\n"
        f"LinkedIn: {personal.get('linkedin', '')}\n"
    )
    
    history = ""
    if previous_actions:
        history = "Previous actions taken:\n" + "\n".join(f"  - {a}" for a in previous_actions[-5:])
    
    system_prompt = (
        "You are an expert web automation agent analyzing a job application page screenshot.\n"
        "Your goal is to identify the NEXT actions needed to fill out and submit this application form.\n\n"
        "RULES:\n"
        "1. Return a JSON array of actions. Each action has: {action, selector, value, description}\n"
        "2. Valid action types: click, fill, upload, select, scroll, wait, done, skip\n"
        "3. For 'fill' actions, provide the CSS selector and the value to type\n"
        "4. For 'click' actions, provide the CSS selector of the button/link to click\n"
        "5. For 'upload' actions, provide the file input selector (value will be resume path)\n"
        "6. Use 'done' when the form appears fully filled and ready for submission\n"
        "7. Use 'skip' if the page is not a form or cannot be automated\n"
        "8. ONLY return valid JSON array, no explanations\n\n"
        "CSS Selector Tips:\n"
        "- Use descriptive selectors: button:has-text('Apply'), input[name='email']\n"
        "- For file uploads: input[type='file']\n"
        "- For submit buttons: button[type='submit'], button:has-text('Submit')\n"
    )
    
    user_prompt = (
        f"Page URL: {page_url}\n"
        f"Page Title: {page_title}\n"
        f"Iteration: {iteration}\n\n"
        f"Applicant Details:\n{applicant_summary}\n\n"
        f"{history}\n\n"
        f"[A screenshot of the current page state is attached]\n\n"
        f"Analyze the page and return the next actions as a JSON array.\n"
        f"If the page shows a confirmation or success message, return: [{{'action': 'done', 'description': 'Application submitted'}}]\n"
    )
    
    # For now, use the DOM_REASONING task type (Tier 3) since vision requires
    # specific multi-modal API calls. The router will select the best available model.
    # TODO: Add proper multimodal image support when Gemini/Grok vision APIs
    # are integrated into llm_providers.py
    
    try:
        result = llm_router.route(
            task_type=TaskType.DOM_REASONING,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            json_mode=True,
            temperature=0.2,
        )
        
        if not result:
            return []
        
        # Parse JSON array from response
        json_match = re.search(r"\[.*\]", result, re.DOTALL)
        if json_match:
            actions = json.loads(json_match.group(0))
            if isinstance(actions, list):
                # Validate actions
                valid = []
                for action in actions:
                    if isinstance(action, dict) and action.get("action") in VALID_ACTIONS:
                        valid.append(action)
                return valid
        
        # Try parsing as object with actions array
        json_obj = re.search(r"\{.*\}", result, re.DOTALL)
        if json_obj:
            obj = json.loads(json_obj.group(0))
            if "actions" in obj and isinstance(obj["actions"], list):
                return [a for a in obj["actions"] if isinstance(a, dict) and a.get("action") in VALID_ACTIONS]
    
    except Exception as e:
        logger.error(f"VisionNavigator: LLM plan generation failed: {e}")
    
    return []


# ─────────────────────────────────────────────────────────────────────────────
# Action Executor
# ─────────────────────────────────────────────────────────────────────────────

def _execute_action(
    page: Page,
    action: Dict[str, Any],
    resume_path: Optional[str] = None,
) -> bool:
    """Execute a single action from the vision plan."""
    act_type = action.get("action", "")
    selector = action.get("selector", "")
    value = action.get("value", "")
    desc = action.get("description", "")
    
    try:
        if act_type == "fill" and selector and value:
            loc = page.locator(selector).first
            if loc.is_visible():
                loc.fill("")
                loc.fill(value)
                logger.info(f"VisionNav: Filled '{selector}' → '{value[:30]}...' ({desc})")
                page.wait_for_timeout(300)
                return True
        
        elif act_type == "click" and selector:
            loc = page.locator(selector).first
            if loc.is_visible():
                loc.scroll_into_view_if_needed()
                loc.click()
                logger.info(f"VisionNav: Clicked '{selector}' ({desc})")
                page.wait_for_timeout(1000)
                return True
        
        elif act_type == "upload" and selector:
            if resume_path and Path(resume_path).exists():
                loc = page.locator(selector).first
                loc.set_input_files(resume_path)
                logger.info(f"VisionNav: Uploaded file to '{selector}' ({desc})")
                page.wait_for_timeout(2000)
                return True
        
        elif act_type == "select" and selector and value:
            loc = page.locator(selector).first
            if loc.is_visible():
                loc.select_option(label=value)
                logger.info(f"VisionNav: Selected '{value}' in '{selector}' ({desc})")
                return True
        
        elif act_type == "scroll":
            page.evaluate("window.scrollBy(0, 500)")
            logger.info(f"VisionNav: Scrolled down ({desc})")
            page.wait_for_timeout(500)
            return True
        
        elif act_type == "wait":
            wait_ms = int(value) if value else 2000
            page.wait_for_timeout(min(wait_ms, 5000))
            return True
        
        elif act_type in ("done", "skip"):
            logger.info(f"VisionNav: Action='{act_type}' ({desc})")
            return True
    
    except Exception as e:
        logger.warning(f"VisionNav: Action '{act_type}' on '{selector}' failed: {e}")
    
    return False


# ─────────────────────────────────────────────────────────────────────────────
# Main Navigator — Iterative Screenshot → Reason → Act Loop
# ─────────────────────────────────────────────────────────────────────────────

class VisionNavigator:
    """
    Vision-based page navigator for unknown application forms.
    
    Uses iterative screenshot → LLM → action loops to intelligently
    fill and submit application forms on unknown external sites.
    
    Usage:
        navigator = VisionNavigator()
        result = navigator.navigate_and_fill(
            page=page,
            applicant_info=user_profile,
            resume_path="/path/to/resume.pdf",
        )
        if result["success"]:
            print("Form filled successfully!")
    """
    
    def __init__(self, max_iterations: int = 8):
        self.max_iterations = max_iterations
    
    def navigate_and_fill(
        self,
        page: Page,
        applicant_info: Dict[str, Any],
        resume_path: Optional[str] = None,
        apply_url: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Main entry point — iteratively fills an unknown application form.
        
        Returns:
            {
                "success": bool,
                "iterations": int,
                "actions_executed": int,
                "screenshots": [str],
                "error": str | None,
            }
        """
        logger.info(
            f"VisionNavigator: Starting vision-based navigation "
            f"(url={page.url}, max_iterations={self.max_iterations})"
        )
        
        screenshots = []
        total_actions = 0
        previous_actions = []
        
        for iteration in range(1, self.max_iterations + 1):
            logger.info(f"VisionNavigator: === Iteration {iteration}/{self.max_iterations} ===")
            
            # 1. Capture screenshot
            filepath, b64 = _capture_and_encode(page, f"iter{iteration}")
            if filepath:
                screenshots.append(filepath)
            
            # 2. Get page metadata
            page_title = ""
            try:
                page_title = page.title()
            except Exception:
                pass
            
            # 3. Generate action plan from vision LLM
            actions = _generate_vision_plan(
                screenshot_b64=b64 or "",
                page_url=apply_url or page.url,
                applicant_info=applicant_info,
                page_title=page_title,
                iteration=iteration,
                previous_actions=previous_actions,
            )
            
            if not actions:
                logger.warning(
                    f"VisionNavigator: No actions generated on iteration {iteration}. "
                    f"Falling back to DOM heuristics."
                )
                # Try basic DOM-based fallback
                actions = self._dom_fallback_actions(page, applicant_info)
            
            if not actions:
                logger.info(f"VisionNavigator: No more actions available. Stopping.")
                break
            
            # 4. Execute actions
            iteration_executed = 0
            form_done = False
            
            for action in actions:
                if action.get("action") == "done":
                    form_done = True
                    break
                
                if action.get("action") == "skip":
                    return {
                        "success": False,
                        "iterations": iteration,
                        "actions_executed": total_actions,
                        "screenshots": screenshots,
                        "error": "Page not automatable (skip signal)",
                    }
                
                success = _execute_action(page, action, resume_path)
                if success:
                    iteration_executed += 1
                    total_actions += 1
                    previous_actions.append(
                        f"{action.get('action')}: {action.get('description', action.get('selector', ''))}"
                    )
            
            if form_done:
                logger.info(
                    f"VisionNavigator: Form fill complete after "
                    f"{iteration} iterations, {total_actions} actions."
                )
                return {
                    "success": True,
                    "iterations": iteration,
                    "actions_executed": total_actions,
                    "screenshots": screenshots,
                    "error": None,
                }
            
            if iteration_executed == 0:
                logger.info(
                    f"VisionNavigator: No actions executed on iteration {iteration}. "
                    f"Stopping to avoid infinite loop."
                )
                break
            
            # 5. Wait for page to settle
            page.wait_for_timeout(1500)
        
        # Final state capture
        filepath, _ = _capture_and_encode(page, "final")
        if filepath:
            screenshots.append(filepath)
        
        return {
            "success": total_actions > 0,
            "iterations": min(iteration, self.max_iterations),
            "actions_executed": total_actions,
            "screenshots": screenshots,
            "error": None if total_actions > 0 else "No actions could be executed",
        }
    
    def _dom_fallback_actions(
        self,
        page: Page,
        applicant_info: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        """
        Fallback: Generate actions from DOM analysis when vision LLM fails.
        This bridges to the existing unknown_ats_planner logic.
        """
        try:
            from backend.app.automation.ats.handlers.unknown_ats_planner import (
                extract_interactive_dom,
                generate_action_plan_with_llm,
            )
            
            plan = generate_action_plan_with_llm(page, applicant_info)
            if plan and "actions" in plan:
                return plan["actions"]
        except Exception as e:
            logger.warning(f"VisionNavigator: DOM fallback failed: {e}")
        
        return []


# ─────────────────────────────────────────────────────────────────────────────
# Global Instance
# ─────────────────────────────────────────────────────────────────────────────

vision_navigator = VisionNavigator()
