import logging
from typing import Dict, Any, List
from playwright.sync_api import Page

from backend.app.automation.ats.base_ats import BaseATS
from backend.app.automation.ats.ats_router import register_ats
from backend.app.automation.browser.playwright_client import PlaywrightClient
from backend.app.automation.question_engine.qa_agent import QuestionAnsweringAgent

logger = logging.getLogger("uvicorn.error")

class BaseATSAdapter(BaseATS):
    """
    Subclass providing helper methods for form filling and question answering.
    """
    def fill_form_heuristics(
        self,
        page: Page,
        client: PlaywrightClient,
        qa_agent: QuestionAnsweringAgent,
        candidate_profile: Dict[str, Any],
        resume_id: int,
        log
    ) -> bool:
        """
        Fills text, radio, and dropdown fields on the page.
        """
        # 1. Fill text fields & textareas
        text_inputs = page.locator("input[type='text'], input[type='email'], input[type='tel'], textarea")
        for i in range(text_inputs.count()):
            try:
                inp = text_inputs.nth(i)
                if not inp.is_visible() or inp.input_value().strip():
                    continue
                
                label = page.evaluate(
                    "(el) => {"
                    "  let parent = el.closest('.form-group, .question, .field-wrapper, div[class*=\"input\"]');"
                    "  if (parent) {"
                    "    let lbl = parent.querySelector('label');"
                    "    if (lbl) return lbl.innerText;"
                    "    return parent.innerText;"
                    "  }"
                    "  return '';"
                    "}", inp
                )
                if not label:
                    label = (inp.get_attribute("name") or "") + " " + (inp.get_attribute("placeholder") or "")
                
                answer = qa_agent.generate_answer(resume_id, label, candidate_profile)
                inp.fill(answer)
                log(f"ATSAdapter: Filled '{label[:30]}...' -> '{answer}'")
                page.wait_for_timeout(300)
            except Exception:
                pass

        # 2. Dropdown Selects
        selects = page.locator("select")
        for i in range(selects.count()):
            try:
                sel = selects.nth(i)
                if sel.is_visible() and not sel.input_value().strip():
                    label = page.evaluate(
                        "(el) => {"
                        "  let parent = el.closest('.form-group, .question, .field-wrapper');"
                        "  if (parent) {"
                        "    let lbl = parent.querySelector('label');"
                        "    if (lbl) return lbl.innerText;"
                        "    return parent.innerText;"
                        "  }"
                        "  return '';"
                        "}", sel
                    )
                    
                    answer = qa_agent.generate_answer(resume_id, label, candidate_profile)
                    
                    options = sel.locator("option")
                    matched_val = ""
                    for o_idx in range(options.count()):
                        val = options.nth(o_idx).get_attribute("value")
                        txt = options.nth(o_idx).inner_text().strip().lower()
                        if val and val.strip() and (answer.lower() in txt or txt in answer.lower()):
                            matched_val = val
                            break
                    
                    if not matched_val and options.count() > 1:
                        # Default to first non-empty option
                        for o_idx in range(options.count()):
                            val = options.nth(o_idx).get_attribute("value")
                            if val and val.strip():
                                matched_val = val
                                break
                    
                    if matched_val:
                        sel.select_option(value=matched_val)
                        log(f"ATSAdapter: Selected dropdown for '{label[:30]}...' -> value '{matched_val}'")
            except Exception:
                pass
        
        # Check if there are still empty mandatory inputs
        empty_required = page.locator("input[required]:not([value]), textarea[required]")
        for i in range(empty_required.count()):
            try:
                if empty_required.nth(i).is_visible() and not empty_required.nth(i).input_value().strip():
                    log("ATSAdapter: Unanswered required fields exist.")
                    return False
            except Exception:
                pass
                
        return True


@register_ats("greenhouse")
class GreenhouseATS(BaseATSAdapter):
    def fill_application(self, page: Page, apply_url: str, resume_path: str, user_profile: Dict[str, Any], candidate_profile: Dict[str, Any], resume_id: int) -> Dict[str, Any]:
        client = PlaywrightClient(page, "greenhouse")
        qa_agent = QuestionAnsweringAgent()
        logs = []
        def log(msg): logger.info(msg); logs.append(msg)

        log(f"GreenhouseATS: Navigating to {apply_url}")
        try:
            page.goto(apply_url, timeout=30000, wait_until="domcontentloaded")
            page.wait_for_timeout(3000)
            client.dismiss_popups()

            # Upload resume
            resume_input = page.locator("input[type='file'][accept*='pdf'], input[type='file']#resume_file, input[type='file']")
            if resume_input.count() > 0:
                client.safe_upload_file(resume_input.first.get_attribute("id") or "input[type='file']", resume_path)
                client.human_delay(2000, 3000)

            # Heuristic filling
            success = self.fill_form_heuristics(page, client, qa_agent, candidate_profile, resume_id, log)
            
            client.capture_state_screenshot("greenhouse_filled")
            return {
                "success": success,
                "logs": "\n".join(logs),
                "error": None if success else "Requires review",
                "needs_review": not success
            }
        except Exception as e:
            client.capture_state_screenshot("greenhouse_error")
            return {"success": False, "logs": "\n".join(logs), "error": str(e)}


@register_ats("lever")
class LeverATS(BaseATSAdapter):
    def fill_application(self, page: Page, apply_url: str, resume_path: str, user_profile: Dict[str, Any], candidate_profile: Dict[str, Any], resume_id: int) -> Dict[str, Any]:
        client = PlaywrightClient(page, "lever")
        qa_agent = QuestionAnsweringAgent()
        logs = []
        def log(msg): logger.info(msg); logs.append(msg)

        log(f"LeverATS: Navigating to {apply_url}")
        try:
            page.goto(apply_url, timeout=30000, wait_until="domcontentloaded")
            page.wait_for_timeout(3000)
            client.dismiss_popups()

            # Check for introductory Apply button
            apply_btn = page.locator("a.postings-btn:has-text('Apply'), a:has-text('Apply for this job')")
            if apply_btn.count() > 0:
                apply_btn.first.click()
                page.wait_for_load_state("domcontentloaded")
                page.wait_for_timeout(2000)

            # Upload resume
            resume_input = page.locator("input[type='file']#resume-upload-input, input[type='file']")
            if resume_input.count() > 0:
                resume_input.first.set_input_files(resume_path)
                client.human_delay(2000, 3000)

            # Fill Form
            success = self.fill_form_heuristics(page, client, qa_agent, candidate_profile, resume_id, log)
            
            client.capture_state_screenshot("lever_filled")
            return {
                "success": success,
                "logs": "\n".join(logs),
                "error": None if success else "Requires review",
                "needs_review": not success
            }
        except Exception as e:
            client.capture_state_screenshot("lever_error")
            return {"success": False, "logs": "\n".join(logs), "error": str(e)}


@register_ats("ashby")
class AshbyATS(BaseATSAdapter):
    def fill_application(self, page: Page, apply_url: str, resume_path: str, user_profile: Dict[str, Any], candidate_profile: Dict[str, Any], resume_id: int) -> Dict[str, Any]:
        client = PlaywrightClient(page, "ashby")
        qa_agent = QuestionAnsweringAgent()
        logs = []
        def log(msg): logger.info(msg); logs.append(msg)

        log(f"AshbyATS: Navigating to {apply_url}")
        try:
            page.goto(apply_url, timeout=30000, wait_until="domcontentloaded")
            page.wait_for_timeout(3000)
            client.dismiss_popups()

            # Upload resume
            resume_input = page.locator("input[type='file']")
            if resume_input.count() > 0:
                resume_input.first.set_input_files(resume_path)
                client.human_delay(2000, 3000)

            success = self.fill_form_heuristics(page, client, qa_agent, candidate_profile, resume_id, log)
            client.capture_state_screenshot("ashby_filled")
            return {
                "success": success,
                "logs": "\n".join(logs),
                "error": None if success else "Requires review",
                "needs_review": not success
            }
        except Exception as e:
            client.capture_state_screenshot("ashby_error")
            return {"success": False, "logs": "\n".join(logs), "error": str(e)}


@register_ats("workday")
class WorkdayATS(BaseATSAdapter):
    def fill_application(self, page: Page, apply_url: str, resume_path: str, user_profile: Dict[str, Any], candidate_profile: Dict[str, Any], resume_id: int) -> Dict[str, Any]:
        client = PlaywrightClient(page, "workday")
        qa_agent = QuestionAnsweringAgent()
        logs = []
        def log(msg): logger.info(msg); logs.append(msg)

        log(f"WorkdayATS: Navigating to {apply_url}")
        try:
            page.goto(apply_url, timeout=30000, wait_until="domcontentloaded")
            page.wait_for_timeout(4000)
            client.dismiss_popups()

            # Click Apply manually if visible
            apply_btn = page.locator("button:has-text('Apply'), a:has-text('Apply Now'), button:has-text('Apply manually')")
            if apply_btn.count() > 0:
                apply_btn.first.click()
                page.wait_for_timeout(3000)

            # Upload resume
            file_inputs = page.locator("input[type='file']")
            if file_inputs.count() > 0:
                file_inputs.first.set_input_files(resume_path)
                client.human_delay(2500, 4000)

            success = self.fill_form_heuristics(page, client, qa_agent, candidate_profile, resume_id, log)
            client.capture_state_screenshot("workday_filled")
            return {
                "success": success,
                "logs": "\n".join(logs),
                "error": None if success else "Requires review",
                "needs_review": not success
            }
        except Exception as e:
            client.capture_state_screenshot("workday_error")
            return {"success": False, "logs": "\n".join(logs), "error": str(e)}


@register_ats("smartrecruiters")
class SmartRecruitersATS(BaseATSAdapter):
    def fill_application(self, page: Page, apply_url: str, resume_path: str, user_profile: Dict[str, Any], candidate_profile: Dict[str, Any], resume_id: int) -> Dict[str, Any]:
        client = PlaywrightClient(page, "smartrecruiters")
        qa_agent = QuestionAnsweringAgent()
        logs = []
        def log(msg): logger.info(msg); logs.append(msg)

        try:
            page.goto(apply_url, timeout=30000, wait_until="domcontentloaded")
            page.wait_for_timeout(3000)
            client.dismiss_popups()

            resume_input = page.locator("input[type='file']")
            if resume_input.count() > 0:
                resume_input.first.set_input_files(resume_path)
                client.human_delay(2000, 3000)

            success = self.fill_form_heuristics(page, client, qa_agent, candidate_profile, resume_id, log)
            client.capture_state_screenshot("smartrecruiters_filled")
            return {"success": success, "logs": "\n".join(logs), "error": None if success else "Review required", "needs_review": not success}
        except Exception as e:
            client.capture_state_screenshot("smartrecruiters_error")
            return {"success": False, "logs": "\n".join(logs), "error": str(e)}


@register_ats("icims")
class IcimsATS(BaseATSAdapter):
    def fill_application(self, page: Page, apply_url: str, resume_path: str, user_profile: Dict[str, Any], candidate_profile: Dict[str, Any], resume_id: int) -> Dict[str, Any]:
        client = PlaywrightClient(page, "icims")
        qa_agent = QuestionAnsweringAgent()
        logs = []
        def log(msg): logger.info(msg); logs.append(msg)

        try:
            page.goto(apply_url, timeout=30000, wait_until="domcontentloaded")
            page.wait_for_timeout(3000)
            client.dismiss_popups()

            apply_btn = page.locator("a:has-text('Apply for this job'), button:has-text('Apply')")
            if apply_btn.count() > 0:
                apply_btn.first.click()
                page.wait_for_timeout(3000)

            file_inputs = page.locator("input[type='file']")
            if file_inputs.count() > 0:
                file_inputs.first.set_input_files(resume_path)
                client.human_delay(2000, 3000)

            success = self.fill_form_heuristics(page, client, qa_agent, candidate_profile, resume_id, log)
            client.capture_state_screenshot("icims_filled")
            return {"success": success, "logs": "\n".join(logs), "error": None if success else "Review required", "needs_review": not success}
        except Exception as e:
            client.capture_state_screenshot("icims_error")
            return {"success": False, "logs": "\n".join(logs), "error": str(e)}


@register_ats("oracle")
class OracleATS(BaseATSAdapter):
    def fill_application(self, page: Page, apply_url: str, resume_path: str, user_profile: Dict[str, Any], candidate_profile: Dict[str, Any], resume_id: int) -> Dict[str, Any]:
        client = PlaywrightClient(page, "oracle")
        qa_agent = QuestionAnsweringAgent()
        logs = []
        def log(msg): logger.info(msg); logs.append(msg)

        try:
            page.goto(apply_url, timeout=30000, wait_until="domcontentloaded")
            page.wait_for_timeout(3000)
            client.dismiss_popups()

            file_inputs = page.locator("input[type='file']")
            if file_inputs.count() > 0:
                file_inputs.first.set_input_files(resume_path)
                client.human_delay(2000, 3000)

            success = self.fill_form_heuristics(page, client, qa_agent, candidate_profile, resume_id, log)
            client.capture_state_screenshot("oracle_filled")
            return {"success": success, "logs": "\n".join(logs), "error": None if success else "Review required", "needs_review": not success}
        except Exception as e:
            client.capture_state_screenshot("oracle_error")
            return {"success": False, "logs": "\n".join(logs), "error": str(e)}


@register_ats("successfactors")
class SuccessFactorsATS(BaseATSAdapter):
    def fill_application(self, page: Page, apply_url: str, resume_path: str, user_profile: Dict[str, Any], candidate_profile: Dict[str, Any], resume_id: int) -> Dict[str, Any]:
        client = PlaywrightClient(page, "successfactors")
        qa_agent = QuestionAnsweringAgent()
        logs = []
        def log(msg): logger.info(msg); logs.append(msg)

        try:
            page.goto(apply_url, timeout=30000, wait_until="domcontentloaded")
            page.wait_for_timeout(3000)
            client.dismiss_popups()

            file_inputs = page.locator("input[type='file']")
            if file_inputs.count() > 0:
                file_inputs.first.set_input_files(resume_path)
                client.human_delay(2000, 3000)

            success = self.fill_form_heuristics(page, client, qa_agent, candidate_profile, resume_id, log)
            client.capture_state_screenshot("successfactors_filled")
            return {"success": success, "logs": "\n".join(logs), "error": None if success else "Review required", "needs_review": not success}
        except Exception as e:
            client.capture_state_screenshot("successfactors_error")
            return {"success": False, "logs": "\n".join(logs), "error": str(e)}


@register_ats("taleo")
class TaleoATS(BaseATSAdapter):
    def fill_application(self, page: Page, apply_url: str, resume_path: str, user_profile: Dict[str, Any], candidate_profile: Dict[str, Any], resume_id: int) -> Dict[str, Any]:
        client = PlaywrightClient(page, "taleo")
        qa_agent = QuestionAnsweringAgent()
        logs = []
        def log(msg): logger.info(msg); logs.append(msg)

        try:
            page.goto(apply_url, timeout=30000, wait_until="domcontentloaded")
            page.wait_for_timeout(3000)
            client.dismiss_popups()

            file_inputs = page.locator("input[type='file']")
            if file_inputs.count() > 0:
                file_inputs.first.set_input_files(resume_path)
                client.human_delay(2000, 3000)

            success = self.fill_form_heuristics(page, client, qa_agent, candidate_profile, resume_id, log)
            client.capture_state_screenshot("taleo_filled")
            return {"success": success, "logs": "\n".join(logs), "error": None if success else "Review required", "needs_review": not success}
        except Exception as e:
            client.capture_state_screenshot("taleo_error")
            return {"success": False, "logs": "\n".join(logs), "error": str(e)}


@register_ats("bamboohr")
class BambooHRATS(BaseATSAdapter):
    def fill_application(self, page: Page, apply_url: str, resume_path: str, user_profile: Dict[str, Any], candidate_profile: Dict[str, Any], resume_id: int) -> Dict[str, Any]:
        client = PlaywrightClient(page, "bamboohr")
        qa_agent = QuestionAnsweringAgent()
        logs = []
        def log(msg): logger.info(msg); logs.append(msg)

        try:
            page.goto(apply_url, timeout=30000, wait_until="domcontentloaded")
            page.wait_for_timeout(3000)
            client.dismiss_popups()

            file_inputs = page.locator("input[type='file']")
            if file_inputs.count() > 0:
                file_inputs.first.set_input_files(resume_path)
                client.human_delay(2000, 3000)

            success = self.fill_form_heuristics(page, client, qa_agent, candidate_profile, resume_id, log)
            client.capture_state_screenshot("bamboohr_filled")
            return {"success": success, "logs": "\n".join(logs), "error": None if success else "Review required", "needs_review": not success}
        except Exception as e:
            client.capture_state_screenshot("bamboohr_error")
            return {"success": False, "logs": "\n".join(logs), "error": str(e)}


@register_ats("jobvite")
class JobviteATS(BaseATSAdapter):
    def fill_application(self, page: Page, apply_url: str, resume_path: str, user_profile: Dict[str, Any], candidate_profile: Dict[str, Any], resume_id: int) -> Dict[str, Any]:
        client = PlaywrightClient(page, "jobvite")
        qa_agent = QuestionAnsweringAgent()
        logs = []
        def log(msg): logger.info(msg); logs.append(msg)

        try:
            page.goto(apply_url, timeout=30000, wait_until="domcontentloaded")
            page.wait_for_timeout(3000)
            client.dismiss_popups()

            file_inputs = page.locator("input[type='file']")
            if file_inputs.count() > 0:
                file_inputs.first.set_input_files(resume_path)
                client.human_delay(2000, 3000)

            success = self.fill_form_heuristics(page, client, qa_agent, candidate_profile, resume_id, log)
            client.capture_state_screenshot("jobvite_filled")
            return {"success": success, "logs": "\n".join(logs), "error": None if success else "Review required", "needs_review": not success}
        except Exception as e:
            client.capture_state_screenshot("jobvite_error")
            return {"success": False, "logs": "\n".join(logs), "error": str(e)}


@register_ats("jazzhr")
class JazzHRATS(BaseATSAdapter):
    def fill_application(self, page: Page, apply_url: str, resume_path: str, user_profile: Dict[str, Any], candidate_profile: Dict[str, Any], resume_id: int) -> Dict[str, Any]:
        client = PlaywrightClient(page, "jazzhr")
        qa_agent = QuestionAnsweringAgent()
        logs = []
        def log(msg): logger.info(msg); logs.append(msg)

        try:
            page.goto(apply_url, timeout=30000, wait_until="domcontentloaded")
            page.wait_for_timeout(3000)
            client.dismiss_popups()

            file_inputs = page.locator("input[type='file']")
            if file_inputs.count() > 0:
                file_inputs.first.set_input_files(resume_path)
                client.human_delay(2000, 3000)

            success = self.fill_form_heuristics(page, client, qa_agent, candidate_profile, resume_id, log)
            client.capture_state_screenshot("jazzhr_filled")
            return {"success": success, "logs": "\n".join(logs), "error": None if success else "Review required", "needs_review": not success}
        except Exception as e:
            client.capture_state_screenshot("jazzhr_error")
            return {"success": False, "logs": "\n".join(logs), "error": str(e)}
