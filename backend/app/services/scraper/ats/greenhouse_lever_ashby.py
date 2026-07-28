import logging
from typing import Dict, Any
from playwright.sync_api import Page
from backend.app.services.scraper.base_ats import BaseATS
from backend.app.services.scraper.registry import register_ats
from backend.app.services.browser_manager import capture_screenshot, safe_click, human_delay, dismiss_popups

logger = logging.getLogger("uvicorn.error")

@register_ats("greenhouse")
class GreenhouseATS(BaseATS):
    """
    ATS Adapter for Greenhouse application boards.
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

        log(f"GreenhouseATS: Filling application at {apply_url}...")
        try:
            page.goto(apply_url, timeout=30000, wait_until="domcontentloaded")
            page.wait_for_timeout(3000)
            dismiss_popups(page)

            first_name = user_profile.get("first_name", "")
            last_name = user_profile.get("last_name", "")
            email = user_profile.get("email", "")
            phone = user_profile.get("phone", "")
            cover_letter = user_profile.get("cover_letter", "")

            # Fill name fields
            if page.locator("#first_name").count() > 0:
                page.fill("#first_name", first_name)
                page.fill("#last_name", last_name)
                log("GreenhouseATS: Filled first_name/last_name fields.")
            elif page.locator("#name").count() > 0:
                page.fill("#name", f"{first_name} {last_name}")
                log("GreenhouseATS: Filled single name field.")

            # Email and phone
            if page.locator("#email").count() > 0:
                page.fill("#email", email)
            if page.locator("#phone").count() > 0:
                page.fill("#phone", phone)

            # Resume upload
            resume_input = page.locator("input[type='file'][accept*='pdf'], input[type='file']#resume_file, input[type='file']")
            if resume_input.count() > 0:
                log("GreenhouseATS: Uploading resume file...")
                resume_input.first.set_input_files(resume_path)
                human_delay(page, 1500, 2500)

            # Cover letter
            if cover_letter:
                cover_input = page.locator("textarea#cover_letter_text, textarea#cover_letter, textarea[name*='cover']")
                if cover_input.count() > 0:
                    cover_input.first.fill(cover_letter)
                    log("GreenhouseATS: Filled cover letter textarea.")

            capture_screenshot(page, "greenhouse_ats_filled")
            page.wait_for_timeout(4000)
            return {"success": True, "logs": "\n".join(logs), "error": None}
        except Exception as e:
            capture_screenshot(page, "greenhouse_ats_error")
            log(f"GreenhouseATS Error: {e}")
            return {"success": False, "logs": "\n".join(logs), "error": str(e)}


@register_ats("lever")
class LeverATS(BaseATS):
    """
    ATS Adapter for Lever application boards.
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

        log(f"LeverATS: Filling application at {apply_url}...")
        try:
            page.goto(apply_url, timeout=30000, wait_until="domcontentloaded")
            page.wait_for_timeout(3000)
            dismiss_popups(page)

            # Lever usually has a pre-apply page with "Apply for this job" button
            apply_btn = page.locator("a.postings-btn:has-text('Apply'), a:has-text('Apply for this job')")
            if apply_btn.count() > 0:
                log("LeverATS: Found entry page. Clicking Apply...")
                apply_btn.first.click()
                page.wait_for_load_state("domcontentloaded")
                page.wait_for_timeout(2000)

            first_name = user_profile.get("first_name", "")
            last_name = user_profile.get("last_name", "")
            email = user_profile.get("email", "")
            phone = user_profile.get("phone", "")

            # Resume upload
            resume_input = page.locator("input[type='file']#resume-upload-input, input[type='file']")
            if resume_input.count() > 0:
                log("LeverATS: Uploading resume file...")
                resume_input.first.set_input_files(resume_path)
                human_delay(page, 2000, 3000)

            # Name, email, phone
            name_input = page.locator("input[name='name']")
            if name_input.count() > 0:
                name_input.fill(f"{first_name} {last_name}")
            email_input = page.locator("input[name='email']")
            if email_input.count() > 0:
                email_input.fill(email)
            phone_input = page.locator("input[name='phone']")
            if phone_input.count() > 0:
                phone_input.fill(phone)

            capture_screenshot(page, "lever_ats_filled")
            page.wait_for_timeout(4000)
            return {"success": True, "logs": "\n".join(logs), "error": None}
        except Exception as e:
            capture_screenshot(page, "lever_ats_error")
            log(f"LeverATS Error: {e}")
            return {"success": False, "logs": "\n".join(logs), "error": str(e)}


@register_ats("ashby")
class AshbyATS(BaseATS):
    """
    ATS Adapter for Ashby application boards.
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

        log(f"AshbyATS: Filling application at {apply_url}...")
        try:
            page.goto(apply_url, timeout=30000, wait_until="domcontentloaded")
            page.wait_for_timeout(3000)
            dismiss_popups(page)

            first_name = user_profile.get("first_name", "")
            last_name = user_profile.get("last_name", "")
            email = user_profile.get("email", "")
            phone = user_profile.get("phone", "")

            # Try to upload resume first
            resume_input = page.locator("input[type='file'][accept*='pdf'], input[type='file']")
            if resume_input.count() > 0:
                log("AshbyATS: Uploading resume file...")
                resume_input.first.set_input_files(resume_path)
                human_delay(page, 2000, 3000)

            # Heuristics for text inputs on Ashby
            inputs = page.locator("input[type='text'], input[type='email'], input[type='tel']")
            for i in range(inputs.count()):
                try:
                    inp = inputs.nth(i)
                    id_val = (inp.get_attribute("id") or "").lower()
                    name_val = (inp.get_attribute("name") or "").lower()
                    placeholder = (inp.get_attribute("placeholder") or "").lower()
                    combined = id_val + name_val + placeholder

                    if "first" in combined or "given" in combined:
                        inp.fill(first_name)
                    elif "last" in combined or "family" in combined:
                        inp.fill(last_name)
                    elif "email" in combined:
                        inp.fill(email)
                    elif "phone" in combined:
                        inp.fill(phone)
                except Exception:
                    pass

            capture_screenshot(page, "ashby_ats_filled")
            page.wait_for_timeout(4000)
            return {"success": True, "logs": "\n".join(logs), "error": None}
        except Exception as e:
            capture_screenshot(page, "ashby_ats_error")
            log(f"AshbyATS Error: {e}")
            return {"success": False, "logs": "\n".join(logs), "error": str(e)}
