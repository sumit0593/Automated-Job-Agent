import logging
from typing import Dict, Any
from playwright.sync_api import Page
from backend.app.services.scraper.base_ats import BaseATS
from backend.app.services.scraper.registry import register_ats
from backend.app.services.browser_manager import capture_screenshot, safe_click, human_delay, dismiss_popups

logger = logging.getLogger("uvicorn.error")

@register_ats("oracle")
class OracleATS(BaseATS):
    """
    ATS Adapter for Oracle Recruiting Cloud application pages.
    """
    def fill_application(
        self,
        page: Page,
        apply_url: str,
        resume_path: str,
        user_profile: Dict[str, Any]
    ) -> Dict[str, Any]:
        logs = []
        def log(msg):
            logger.info(msg)
            logs.append(msg)

        log(f"OracleATS: Loading application {apply_url}...")
        try:
            page.goto(apply_url, timeout=30000, wait_until="domcontentloaded")
            page.wait_for_timeout(3000)
            dismiss_popups(page)

            first_name = user_profile.get("first_name", "")
            last_name = user_profile.get("last_name", "")
            email = user_profile.get("email", "")

            # Basic layout detection and filling
            file_inputs = page.locator("input[type='file']")
            if file_inputs.count() > 0:
                log("OracleATS: Uploading resume file...")
                file_inputs.first.set_input_files(resume_path)
                human_delay(page, 2000, 3000)

            # Heuristics for standard ORC text inputs
            inputs = page.locator("input[type='text'], input[type='email']")
            for i in range(inputs.count()):
                try:
                    inp = inputs.nth(i)
                    combined = ((inp.get_attribute("id") or "") + (inp.get_attribute("name") or "") + (inp.get_attribute("placeholder") or "")).lower()
                    if "first" in combined:
                        inp.fill(first_name)
                    elif "last" in combined:
                        inp.fill(last_name)
                    elif "email" in combined:
                        inp.fill(email)
                except Exception:
                    pass

            capture_screenshot(page, "oracle_ats_filled")
            page.wait_for_timeout(4000)
            return {"success": True, "logs": "\n".join(logs), "error": None}
        except Exception as e:
            capture_screenshot(page, "oracle_ats_error")
            log(f"OracleATS Error: {e}")
            return {"success": False, "logs": "\n".join(logs), "error": str(e)}


@register_ats("successfactors")
class SuccessFactorsATS(BaseATS):
    """
    ATS Adapter for SAP SuccessFactors Recruiting.
    """
    def fill_application(
        self,
        page: Page,
        apply_url: str,
        resume_path: str,
        user_profile: Dict[str, Any]
    ) -> Dict[str, Any]:
        logs = []
        def log(msg):
            logger.info(msg)
            logs.append(msg)

        log(f"SuccessFactorsATS: Loading application {apply_url}...")
        try:
            page.goto(apply_url, timeout=30000, wait_until="domcontentloaded")
            page.wait_for_timeout(3000)
            dismiss_popups(page)

            first_name = user_profile.get("first_name", "")
            last_name = user_profile.get("last_name", "")
            email = user_profile.get("email", "")

            # Resume upload
            file_inputs = page.locator("input[type='file']")
            if file_inputs.count() > 0:
                log("SuccessFactorsATS: Uploading resume file...")
                file_inputs.first.set_input_files(resume_path)
                human_delay(page, 2000, 3000)

            # Heuristics for standard SAP SuccessFactors inputs
            inputs = page.locator("input[type='text'], input[type='email']")
            for i in range(inputs.count()):
                try:
                    inp = inputs.nth(i)
                    combined = ((inp.get_attribute("id") or "") + (inp.get_attribute("name") or "")).lower()
                    if "first" in combined:
                        inp.fill(first_name)
                    elif "last" in combined:
                        inp.fill(last_name)
                    elif "email" in combined:
                        inp.fill(email)
                except Exception:
                    pass

            capture_screenshot(page, "successfactors_ats_filled")
            page.wait_for_timeout(4000)
            return {"success": True, "logs": "\n".join(logs), "error": None}
        except Exception as e:
            capture_screenshot(page, "successfactors_ats_error")
            log(f"SuccessFactorsATS Error: {e}")
            return {"success": False, "logs": "\n".join(logs), "error": str(e)}


@register_ats("taleo")
class TaleoATS(BaseATS):
    """
    ATS Adapter for Taleo application pages.
    """
    def fill_application(
        self,
        page: Page,
        apply_url: str,
        resume_path: str,
        user_profile: Dict[str, Any]
    ) -> Dict[str, Any]:
        logs = []
        def log(msg):
            logger.info(msg)
            logs.append(msg)

        log(f"TaleoATS: Loading application {apply_url}...")
        try:
            page.goto(apply_url, timeout=30000, wait_until="domcontentloaded")
            page.wait_for_timeout(3000)
            dismiss_popups(page)

            first_name = user_profile.get("first_name", "")
            last_name = user_profile.get("last_name", "")
            email = user_profile.get("email", "")

            # Locate file input
            file_inputs = page.locator("input[type='file']")
            if file_inputs.count() > 0:
                log("TaleoATS: Uploading resume file...")
                file_inputs.first.set_input_files(resume_path)
                human_delay(page, 2000, 3000)

            # Heuristics for Taleo inputs (often uses tables or deep nested layouts)
            inputs = page.locator("input[type='text'], input[type='email']")
            for i in range(inputs.count()):
                try:
                    inp = inputs.nth(i)
                    combined = ((inp.get_attribute("id") or "") + (inp.get_attribute("name") or "")).lower()
                    if "first" in combined:
                        inp.fill(first_name)
                    elif "last" in combined:
                        inp.fill(last_name)
                    elif "email" in combined:
                        inp.fill(email)
                except Exception:
                    pass

            capture_screenshot(page, "taleo_ats_filled")
            page.wait_for_timeout(4000)
            return {"success": True, "logs": "\n".join(logs), "error": None}
        except Exception as e:
            capture_screenshot(page, "taleo_ats_error")
            log(f"TaleoATS Error: {e}")
            return {"success": False, "logs": "\n".join(logs), "error": str(e)}


@register_ats("bamboohr")
class BambooHRATS(BaseATS):
    """
    ATS Adapter for BambooHR application pages.
    """
    def fill_application(
        self,
        page: Page,
        apply_url: str,
        resume_path: str,
        user_profile: Dict[str, Any]
    ) -> Dict[str, Any]:
        logs = []
        def log(msg):
            logger.info(msg)
            logs.append(msg)

        log(f"BambooHRATS: Loading application {apply_url}...")
        try:
            page.goto(apply_url, timeout=30000, wait_until="domcontentloaded")
            page.wait_for_timeout(3000)
            dismiss_popups(page)

            first_name = user_profile.get("first_name", "")
            last_name = user_profile.get("last_name", "")
            email = user_profile.get("email", "")
            phone = user_profile.get("phone", "")

            # Upload resume
            resume_input = page.locator("input[type='file']")
            if resume_input.count() > 0:
                log("BambooHRATS: Uploading resume file...")
                resume_input.first.set_input_files(resume_path)
                human_delay(page, 2000, 3000)

            # Heuristics for BambooHR fields
            if page.locator("input[id*='firstname'], input[name*='first_name']").count() > 0:
                page.locator("input[id*='firstname'], input[name*='first_name']").first.fill(first_name)
            if page.locator("input[id*='lastname'], input[name*='last_name']").count() > 0:
                page.locator("input[id*='lastname'], input[name*='last_name']").first.fill(last_name)
            if page.locator("input[id*='email'], input[name*='email']").count() > 0:
                page.locator("input[id*='email'], input[name*='email']").first.fill(email)
            if page.locator("input[id*='phone'], input[name*='phone']").count() > 0 and phone:
                page.locator("input[id*='phone'], input[name*='phone']").first.fill(phone)

            capture_screenshot(page, "bamboohr_ats_filled")
            page.wait_for_timeout(4000)
            return {"success": True, "logs": "\n".join(logs), "error": None}
        except Exception as e:
            capture_screenshot(page, "bamboohr_ats_error")
            log(f"BambooHRATS Error: {e}")
            return {"success": False, "logs": "\n".join(logs), "error": str(e)}
