import logging
from typing import Dict, Any
from playwright.sync_api import Page
from backend.app.automation.ats.base_ats import BaseATS

logger = logging.getLogger("uvicorn.error")

class AshbyHandler(BaseATS):
    """Dedicated modular handler for Ashby HQ candidate pages."""
    
    def apply(self, page: Page, applicant_info: Dict[str, Any], resume_path: str = None) -> bool:
        logger.info(f"AshbyHandler: Initiating application on {page.url}...")
        try:
            page.wait_for_load_state("domcontentloaded")

            full_name = f"{applicant_info.get('first_name', '')} {applicant_info.get('last_name', '')}".strip()
            email = applicant_info.get("email", "")

            if page.locator("input[name='name']").is_visible():
                page.fill("input[name='name']", full_name)
            if page.locator("input[name='email']").is_visible():
                page.fill("input[name='email']", email)

            if resume_path and page.locator("input[type='file']").is_visible():
                page.set_input_files("input[type='file']", resume_path)
                logger.info("AshbyHandler: Attached resume to Ashby form.")

            return True
        except Exception as e:
            logger.error(f"AshbyHandler error: {e}")
            return False
