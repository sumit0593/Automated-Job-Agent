import logging
from typing import Dict, Any
from playwright.sync_api import Page
from backend.app.services.scraper.base_ats import BaseATS
from backend.app.services.scraper.registry import register_ats
from backend.app.services.browser_manager import capture_screenshot, safe_click, human_delay, dismiss_popups

logger = logging.getLogger("uvicorn.error")

@register_ats("workday")
class WorkdayATS(BaseATS):
    """
    ATS Adapter for Workday Careers portal.
    Workday uses highly structured multi-step forms with dynamic locators.
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

        log(f"WorkdayATS: Navigating to Workday portal {apply_url}...")
        try:
            page.goto(apply_url, timeout=30000, wait_until="domcontentloaded")
            page.wait_for_timeout(4000)
            dismiss_popups(page)

            # Look for "Apply" button or similar to initiate
            apply_btn = page.locator("button:has-text('Apply'), a:has-text('Apply Now'), button:has-text('Apply manually')")
            if apply_btn.count() > 0:
                log("WorkdayATS: Clicking initial Apply button...")
                apply_btn.first.click()
                page.wait_for_timeout(3000)

            # Heuristics for standard Workday text fields
            first_name = user_profile.get("first_name", "")
            last_name = user_profile.get("last_name", "")
            email = user_profile.get("email", "")
            phone = user_profile.get("phone", "")

            # Try to upload resume if a file input exists
            file_inputs = page.locator("input[type='file']")
            if file_inputs.count() > 0:
                log("WorkdayATS: Uploading resume file...")
                file_inputs.first.set_input_files(resume_path)
                human_delay(page, 2000, 3500)

            # Look for input fields using Workday specific patterns or generic fallback
            inputs = page.locator("input[data-automation-id*='input'], input[type='text'], input[type='email']")
            for i in range(inputs.count()):
                try:
                    inp = inputs.nth(i)
                    auto_id = (inp.get_attribute("data-automation-id") or "").lower()
                    id_val = (inp.get_attribute("id") or "").lower()
                    combined = auto_id + id_val
                    
                    if "firstname" in combined or "givenname" in combined:
                        inp.fill(first_name)
                    elif "lastname" in combined or "familyname" in combined:
                        inp.fill(last_name)
                    elif "email" in combined:
                        inp.fill(email)
                    elif "phone" in combined and phone:
                        inp.fill(phone)
                except Exception:
                    pass

            capture_screenshot(page, "workday_ats_filled")
            log("WorkdayATS: Fields prefilled. Paused for human review/submission.")
            page.wait_for_timeout(5000)
            return {"success": True, "logs": "\n".join(logs), "error": None}
        except Exception as e:
            capture_screenshot(page, "workday_ats_error")
            log(f"WorkdayATS Error: {e}")
            return {"success": False, "logs": "\n".join(logs), "error": str(e)}


@register_ats("smartrecruiters")
class SmartRecruitersATS(BaseATS):
    """
    ATS Adapter for SmartRecruiters application pages.
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

        log(f"SmartRecruitersATS: Loading application {apply_url}...")
        try:
            page.goto(apply_url, timeout=30000, wait_until="domcontentloaded")
            page.wait_for_timeout(3000)
            dismiss_popups(page)

            first_name = user_profile.get("first_name", "")
            last_name = user_profile.get("last_name", "")
            email = user_profile.get("email", "")
            phone = user_profile.get("phone", "")

            # Upload resume
            resume_input = page.locator("input[type='file'], #resume-upload")
            if resume_input.count() > 0:
                log("SmartRecruitersATS: Uploading resume...")
                resume_input.first.set_input_files(resume_path)
                human_delay(page, 2000, 3000)

            # Fields
            if page.locator("input[name='firstName']").count() > 0:
                page.fill("input[name='firstName']", first_name)
            if page.locator("input[name='lastName']").count() > 0:
                page.fill("input[name='lastName']", last_name)
            if page.locator("input[name='email']").count() > 0:
                page.fill("input[name='email']", email)
            if page.locator("input[name='phone']").count() > 0 and phone:
                page.fill("input[name='phone']", phone)

            capture_screenshot(page, "smartrecruiters_ats_filled")
            page.wait_for_timeout(4000)
            return {"success": True, "logs": "\n".join(logs), "error": None}
        except Exception as e:
            capture_screenshot(page, "smartrecruiters_ats_error")
            log(f"SmartRecruitersATS Error: {e}")
            return {"success": False, "logs": "\n".join(logs), "error": str(e)}


@register_ats("icims")
class IcimsATS(BaseATS):
    """
    ATS Adapter for iCIMS application portals.
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

        log(f"IcimsATS: Loading application {apply_url}...")
        try:
            page.goto(apply_url, timeout=30000, wait_until="domcontentloaded")
            page.wait_for_timeout(3000)
            dismiss_popups(page)

            # Locate the apply button or frame
            apply_btn = page.locator("a:has-text('Apply for this job'), button:has-text('Apply')")
            if apply_btn.count() > 0:
                apply_btn.first.click()
                page.wait_for_timeout(3000)

            first_name = user_profile.get("first_name", "")
            last_name = user_profile.get("last_name", "")
            email = user_profile.get("email", "")

            # Simple heuristic matching
            file_inputs = page.locator("input[type='file']")
            if file_inputs.count() > 0:
                log("IcimsATS: Uploading resume file...")
                file_inputs.first.set_input_files(resume_path)
                human_delay(page, 2000, 3000)

            # Heuristics for standard input boxes
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

            capture_screenshot(page, "icims_ats_filled")
            page.wait_for_timeout(4000)
            return {"success": True, "logs": "\n".join(logs), "error": None}
        except Exception as e:
            capture_screenshot(page, "icims_ats_error")
            log(f"IcimsATS Error: {e}")
            return {"success": False, "logs": "\n".join(logs), "error": str(e)}
