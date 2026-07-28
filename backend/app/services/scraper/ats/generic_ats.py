import logging
from typing import Dict, Any
from playwright.sync_api import Page
from backend.app.services.scraper.base_ats import BaseATS
from backend.app.services.scraper.registry import register_ats
from backend.app.services.browser_manager import capture_screenshot, safe_click, human_delay, dismiss_popups

logger = logging.getLogger("uvicorn.error")

@register_ats("generic")
class GenericATS(BaseATS):
    """
    Fallback adapter for unknown or custom company application portals.
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

        log(f"GenericATS: Navigating to {apply_url}...")
        try:
            page.goto(apply_url, timeout=30000, wait_until="domcontentloaded")
            page.wait_for_timeout(3000)
            dismiss_popups(page)

            first_name = user_profile.get("first_name", "")
            last_name = user_profile.get("last_name", "")
            email = user_profile.get("email", "")

            log("GenericATS: Attempting heuristic form filling...")
            # Try to upload resume first
            file_inputs = page.locator("input[type='file']")
            uploaded = False
            for i in range(file_inputs.count()):
                try:
                    inp = file_inputs.nth(i)
                    accept = inp.get_attribute("accept") or ""
                    id_attr = inp.get_attribute("id") or ""
                    name_attr = inp.get_attribute("name") or ""
                    combined = (accept + id_attr + name_attr).lower()
                    if "pdf" in combined or "resume" in combined or "cv" in combined or file_inputs.count() == 1:
                        inp.set_input_files(resume_path)
                        log(f"GenericATS: Uploaded resume to input field {i}")
                        uploaded = True
                        break
                except Exception as e:
                    log(f"GenericATS: Heuristic upload failed on field {i}: {e}")

            # Fill text inputs
            text_inputs = page.locator("input[type='text'], input[type='email'], input[type='tel']")
            for i in range(text_inputs.count()):
                try:
                    inp = text_inputs.nth(i)
                    if not inp.is_visible():
                        continue
                    
                    placeholder = (inp.get_attribute("placeholder") or "").lower()
                    name = (inp.get_attribute("name") or "").lower()
                    id_val = (inp.get_attribute("id") or "").lower()
                    combined = placeholder + name + id_val
                    
                    if "first" in combined and "name" in combined:
                        inp.fill(first_name)
                    elif "last" in combined and "name" in combined:
                        inp.fill(last_name)
                    elif "email" in combined:
                        inp.fill(email)
                    elif ("phone" in combined or "mobile" in combined) and user_profile.get("phone"):
                        inp.fill(user_profile.get("phone"))
                    elif "name" in combined and not inp.input_value():
                        inp.fill(f"{first_name} {last_name}")
                except Exception as e:
                    log(f"GenericATS: Heuristic text fill failed: {e}")

            capture_screenshot(page, "generic_ats_filled")
            log("GenericATS: Form filled heuristics completed. Pausing for human verification.")
            page.wait_for_timeout(5000)

            return {
                "success": True,
                "logs": "\n".join(logs),
                "error": None
            }
        except Exception as e:
            capture_screenshot(page, "generic_ats_error")
            log(f"GenericATS Error: {e}")
            return {
                "success": False,
                "logs": "\n".join(logs),
                "error": str(e)
            }
