import logging
from typing import Dict, Any
from playwright.sync_api import Page
from backend.app.automation.ats.base_ats import BaseATS

logger = logging.getLogger("uvicorn.error")

class GreenhouseHandler(BaseATS):
    """Dedicated modular handler for Greenhouse.io job boards and embedded forms."""
    
    def apply(self, page: Page, applicant_info: Dict[str, Any], resume_path: str = None) -> bool:
        logger.info(f"GreenhouseHandler: Initiating application on {page.url}...")
        try:
            page.wait_for_load_state("domcontentloaded")
            
            first_name = applicant_info.get("first_name", "")
            last_name = applicant_info.get("last_name", "")
            email = applicant_info.get("email", "")
            phone = applicant_info.get("phone", "")

            if page.locator("#first_name").is_visible():
                page.fill("#first_name", first_name)
            if page.locator("#last_name").is_visible():
                page.fill("#last_name", last_name)
            if page.locator("input[name='job_application[first_name]']").is_visible():
                page.fill("input[name='job_application[first_name]']", first_name)
            if page.locator("input[name='job_application[last_name]']").is_visible():
                page.fill("input[name='job_application[last_name]']", last_name)
                
            if page.locator("#email").is_visible():
                page.fill("#email", email)
            if page.locator("#phone").is_visible():
                page.fill("#phone", phone)

            if resume_path and page.locator("input[type='file']").is_visible():
                page.set_input_files("input[type='file']", resume_path)
                logger.info("GreenhouseHandler: Resume attached successfully.")

            return True
        except Exception as e:
            logger.error(f"GreenhouseHandler error: {e}")
            return False
