import logging
from typing import Dict, Any
from playwright.sync_api import Page
from backend.app.automation.ats.base_ats import BaseATS

logger = logging.getLogger("uvicorn.error")

class DarwinHandler(BaseATS):
    """Dedicated modular handler for Darwinbox recruitment portals."""
    
    def apply(self, page: Page, applicant_info: Dict[str, Any], resume_path: str = None) -> bool:
        logger.info(f"DarwinHandler: Initiating application on {page.url}...")
        try:
            page.wait_for_load_state("domcontentloaded")

            apply_btn = page.locator("button:has-text('Apply'), a:has-text('Apply Now')")
            if apply_btn.is_visible():
                apply_btn.first.click()
                page.wait_for_timeout(1000)

            full_name = f"{applicant_info.get('first_name', '')} {applicant_info.get('last_name', '')}".strip()
            email = applicant_info.get("email", "")
            phone = applicant_info.get("phone", "")

            if page.locator("input[name*='name'], #name").is_visible():
                page.fill("input[name*='name'], #name", full_name)
            if page.locator("input[name*='email'], #email").is_visible():
                page.fill("input[name*='email'], #email", email)
            if page.locator("input[name*='phone'], #mobile").is_visible():
                page.fill("input[name*='phone'], #mobile", phone)

            if resume_path and page.locator("input[type='file']").is_visible():
                page.set_input_files("input[type='file']", resume_path)
                logger.info("DarwinHandler: Attached resume file.")

            return True
        except Exception as e:
            logger.error(f"DarwinHandler error: {e}")
            return False
