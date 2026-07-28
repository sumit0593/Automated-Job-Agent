import logging
from typing import Dict, Any
from playwright.sync_api import Page
from backend.app.automation.ats.base_ats import BaseATS
from backend.app.automation.ats.handlers.unknown_ats_planner import (
    generate_action_plan_with_llm,
    execute_action_plan
)

logger = logging.getLogger("uvicorn.error")

class CustomATSHandler(BaseATS):
    """
    Fallback handler for Custom/Unknown ATS platforms.
    Combines standard heuristic matching with LLM DOM Action Planning.
    """
    
    def apply(self, page: Page, applicant_info: Dict[str, Any], resume_path: str = None) -> bool:
        logger.info(f"CustomATSHandler: Executing application for unknown portal at {page.url}...")
        try:
            page.wait_for_load_state("domcontentloaded")

            first_name = applicant_info.get("first_name", "")
            last_name = applicant_info.get("last_name", "")
            full_name = f"{first_name} {last_name}".strip()
            email = applicant_info.get("email", "")
            phone = applicant_info.get("phone", "")

            filled_any = False

            # Phase 1: Fast Heuristic Field Matching
            if page.locator("input[name*='first']").is_visible():
                page.fill("input[name*='first']", first_name)
                filled_any = True
            if page.locator("input[name*='last']").is_visible():
                page.fill("input[name*='last']", last_name)
                filled_any = True
            elif page.locator("input[name*='name']").is_visible():
                page.fill("input[name*='name']", full_name)
                filled_any = True

            if page.locator("input[type='email'], input[name*='email']").is_visible():
                page.fill("input[type='email'], input[name*='email']", email)
                filled_any = True
            if page.locator("input[type='tel'], input[name*='phone'], input[name*='mobile']").is_visible():
                page.fill("input[type='tel'], input[name*='phone'], input[name*='mobile']", phone)
                filled_any = True

            if resume_path and page.locator("input[type='file']").is_visible():
                page.set_input_files("input[type='file']", resume_path)
                logger.info("CustomATSHandler: Attached resume to form.")
                filled_any = True

            # Phase 2: LLM DOM Action Planner (if heuristic filling was partial or unrecognized portal format)
            logger.info("CustomATSHandler: Engaging LLM Action Planner for custom form completion...")
            action_plan = generate_action_plan_with_llm(page, applicant_info, resume_path)
            plan_success = execute_action_plan(page, action_plan, applicant_info, resume_path)

            return filled_any or plan_success
        except Exception as e:
            logger.error(f"CustomATSHandler error: {e}")
            return False
