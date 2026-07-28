import logging
from typing import Dict, Any
from playwright.sync_api import Page
from backend.app.automation.ats.base_ats import BaseATS

logger = logging.getLogger("uvicorn.error")

class ZohoRecruitHandler(BaseATS):
    """Dedicated modular handler for Zoho Recruit candidate portals."""
    
    def apply(self, page: Page, applicant_info: Dict[str, Any], resume_path: str = None) -> bool:
        logger.info(f"ZohoRecruitHandler: Initiating application on {page.url}...")
        try:
            page.wait_for_load_state("domcontentloaded")

            first_name = applicant_info.get("first_name", "")
            last_name = applicant_info.get("last_name", "")
            email = applicant_info.get("email", "")
            phone = applicant_info.get("phone", "")

            if page.locator("input[name='First Name']").is_visible():
                page.fill("input[name='First Name']", first_name)
            if page.locator("input[name='Last Name']").is_visible():
                page.fill("input[name='Last Name']", last_name)
            if page.locator("input[name='Email']").is_visible():
                page.fill("input[name='Email']", email)
            if page.locator("input[name='Phone']").is_visible():
                page.fill("input[name='Phone']", phone)

            if resume_path and page.locator("input[type='file']").is_visible():
                page.set_input_files("input[type='file']", resume_path)
                logger.info("ZohoRecruitHandler: Attached resume to Zoho form.")

            return True
        except Exception as e:
            logger.error(f"ZohoRecruitHandler error: {e}")
            return False
