import logging
from typing import Dict, Any
from playwright.sync_api import Page
from backend.app.automation.ats.base_ats import BaseATS

logger = logging.getLogger("uvicorn.error")

class WorkdayHandler(BaseATS):
    """Dedicated modular handler for Workday enterprise career portals."""
    
    def apply(self, page: Page, applicant_info: Dict[str, Any], resume_path: str = None) -> bool:
        logger.info(f"WorkdayHandler: Initiating application on {page.url}...")
        try:
            page.wait_for_load_state("domcontentloaded")

            apply_btn = page.locator("a[data-automation-id='adventureButton'], button:has-text('Apply')")
            if apply_btn.is_visible():
                apply_btn.first.click()
                page.wait_for_timeout(1500)

            if resume_path and page.locator("input[type='file']").is_visible():
                page.set_input_files("input[type='file']", resume_path)
                logger.info("WorkdayHandler: Attached resume to Workday application.")

            return True
        except Exception as e:
            logger.error(f"WorkdayHandler error: {e}")
            return False
