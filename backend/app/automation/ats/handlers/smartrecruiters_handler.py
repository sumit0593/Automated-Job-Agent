import logging
from typing import Dict, Any
from playwright.sync_api import Page
from backend.app.automation.ats.base_ats import BaseATS

logger = logging.getLogger("uvicorn.error")

class SmartRecruitersHandler(BaseATS):
    """Dedicated modular handler for SmartRecruiters job application forms."""
    
    def apply(self, page: Page, applicant_info: Dict[str, Any], resume_path: str = None) -> bool:
        logger.info(f"SmartRecruitersHandler: Initiating application on {page.url}...")
        try:
            page.wait_for_load_state("domcontentloaded")

            first_name = applicant_info.get("first_name", "")
            last_name = applicant_info.get("last_name", "")
            email = applicant_info.get("email", "")

            if page.locator("#first-name-input").is_visible():
                page.fill("#first-name-input", first_name)
            if page.locator("#last-name-input").is_visible():
                page.fill("#last-name-input", last_name)
            if page.locator("#email-input").is_visible():
                page.fill("#email-input", email)

            if resume_path and page.locator("input[type='file']").is_visible():
                page.set_input_files("input[type='file']", resume_path)
                logger.info("SmartRecruitersHandler: Attached resume file.")

            return True
        except Exception as e:
            logger.error(f"SmartRecruitersHandler error: {e}")
            return False
