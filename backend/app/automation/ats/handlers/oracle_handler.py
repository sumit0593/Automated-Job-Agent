import logging
from typing import Dict, Any
from playwright.sync_api import Page
from backend.app.automation.ats.base_ats import BaseATS

logger = logging.getLogger("uvicorn.error")

class OracleHandler(BaseATS):
    """Dedicated modular handler for Oracle Taleo & Oracle Recruiting Cloud."""
    
    def apply(self, page: Page, applicant_info: Dict[str, Any], resume_path: str = None) -> bool:
        logger.info(f"OracleHandler: Initiating application on {page.url}...")
        try:
            page.wait_for_load_state("domcontentloaded")

            apply_btn = page.locator("button:has-text('Apply'), a:has-text('Apply Online')")
            if apply_btn.is_visible():
                apply_btn.first.click()
                page.wait_for_timeout(1500)

            if resume_path and page.locator("input[type='file']").is_visible():
                page.set_input_files("input[type='file']", resume_path)
                logger.info("OracleHandler: Attached resume to Oracle workflow.")

            return True
        except Exception as e:
            logger.error(f"OracleHandler error: {e}")
            return False
