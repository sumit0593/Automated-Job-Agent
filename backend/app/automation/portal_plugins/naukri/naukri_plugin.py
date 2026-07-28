import logging
import urllib.parse
import re
from typing import List, Dict, Any, Optional
from playwright.sync_api import Page

from backend.app.automation.portal_plugins.base_portal import BasePortal
from backend.app.automation.portal_plugins.registry import register_portal
from backend.app.automation.browser.playwright_client import PlaywrightClient
from backend.app.automation.question_engine.qa_agent import QuestionAnsweringAgent
from backend.app.automation.ats.ats_router import get_ats_plugin

logger = logging.getLogger("uvicorn.error")

@register_portal("naukri")
class NaukriPortalPlugin(BasePortal):
    """
    Naukri job board plugin. Handles login, job search, filters, Quick Apply,
    and external redirection workflows.
    """
    def login(self, page: Page, username: str, password: str) -> List[Dict[str, Any]]:
        client = PlaywrightClient(page, "naukri")
        page.goto("https://www.naukri.com/nlogin/login", timeout=20000, wait_until="domcontentloaded")
        client.human_delay(1000, 2000)
        
        try:
            username_field = page.locator("#usernameField")
            if username_field.count() > 0:
                username_field.fill(username)
            password_field = page.locator("#passwordField")
            if password_field.count() > 0:
                password_field.fill(password)
            
            submit_btn = page.locator("button[type='submit']")
            if submit_btn.count() > 0:
                submit_btn.click()
        except Exception as e:
            logger.warning(f"Naukri: login prefill failed: {e}")

        logger.info("Naukri: Waiting for manual login completion (120s max)...")
        success = False
        for _ in range(120):
            page.wait_for_timeout(1000)
            current_url = page.url
            if "mnjuser" in current_url or "homepage" in current_url:
                success = True
                break
            try:
                if page.locator(".nI-gNb-drawer__toggle, .user-name").count() > 0:
                    if "nlogin" not in current_url:
                        success = True
                        break
            except Exception:
                pass
        
        if not success:
            client.capture_state_screenshot("login_timeout")
            raise TimeoutError("Naukri login verification timed out.")
            
        logger.info("Naukri login verified.")
        return page.context.cookies()

    def search_jobs(
        self,
        page: Page,
        keyword: str,
        location: str,
        filters: Dict[str, Any],
        max_jobs: int
    ) -> List[Dict[str, Any]]:
        client = PlaywrightClient(page, "naukri")
        results = []
        seen_urls = set()
        
        filter_params = []
        posted_date = filters.get("posted_date")
        if posted_date == "24h":
            filter_params.append("jobAge=1")
        elif posted_date == "3d":
            filter_params.append("jobAge=3")
        elif posted_date == "7d":
            filter_params.append("jobAge=7")
        elif posted_date == "15d":
            filter_params.append("jobAge=15")
        elif posted_date == "30d":
            filter_params.append("jobAge=30")

        exp = filters.get("experience_level")
        if exp == "entry":
            filter_params.append("experience=1")
        elif exp == "mid":
            filter_params.append("experience=3")
        elif exp == "senior":
            filter_params.append("experience=7")

        remote = filters.get("remote_filter")
        if remote == "remote":
            filter_params.append("wfhType=0")
        elif remote == "hybrid":
            filter_params.append("wfhType=2")
        elif remote == "onsite":
            filter_params.append("wfhType=1")

        job_type = filters.get("job_type")
        if job_type == "full-time":
            filter_params.append("jobType=0")
        elif job_type == "contract":
            filter_params.append("jobType=2")

        sort_by = filters.get("sort_by")
        if sort_by == "newest":
            filter_params.append("sort=date")

        query_string = "&".join(filter_params)
        max_pages = min((max_jobs // 20) + 1, 10)

        for page_num in range(1, max_pages + 1):
            if len(results) >= max_jobs:
                break
            
            if page_num == 1:
                search_url = f"https://www.naukri.com/jobs-in-india?k={urllib.parse.quote(keyword)}"
            else:
                search_url = f"https://www.naukri.com/jobs-in-india-page-{page_num}?k={urllib.parse.quote(keyword)}"
                
            if location:
                search_url += f"&l={urllib.parse.quote(location)}"
            if query_string:
                search_url += f"&{query_string}"

            logger.info(f"Naukri: Loading search page {page_num}...")
            page.goto(search_url, timeout=30000, wait_until="domcontentloaded")
            
            try:
                page.wait_for_selector(
                    "article.jobTuple, .srp-jobtuple-wrapper, [data-job-id], .cust-job-tuple",
                    timeout=12000
                )
            except Exception:
                logger.warning(f"Naukri: No job cards visible on page {page_num}")
                break

            client.dismiss_popups()
            client.human_delay(500, 1000)

            job_cards = page.locator("article.jobTuple, .srp-jobtuple-wrapper, [data-job-id], .cust-job-tuple")
            card_count = job_cards.count()
            if card_count == 0:
                break

            for i in range(card_count):
                if len(results) >= max_jobs:
                    break
                try:
                    card = job_cards.nth(i)
                    
                    title_el = card.locator("a.title, a[class*='title'], [class*='jobTitle'], .info h2 a").first
                    title = title_el.inner_text(timeout=2000).strip() if title_el.count() > 0 else ""
                    if not title:
                        continue

                    comp_el = card.locator("a.comp-name, a[class*='comp-name'], [class*='company'], .subTitle a").first
                    company = comp_el.inner_text(timeout=2000).strip() if comp_el.count() > 0 else "Unknown"

                    loc_el = card.locator(".loc-wrap span.loc, .location, .loc, [class*='location']").first
                    loc = loc_el.inner_text(timeout=2000).strip() if loc_el.count() > 0 else "Remote"

                    link_el = card.locator("a.title, a[class*='title'], a[href*='/job-listings']").first
                    job_href = link_el.get_attribute("href") or ""
                    if not job_href:
                        continue

                    job_url = job_href.split("?")[0]
                    if job_url in seen_urls:
                        continue
                    seen_urls.add(job_url)

                    desc_el = card.locator(".job-desc, .jobDescription, [class*='description']").first
                    desc = desc_el.inner_text(timeout=2000).strip() if desc_el.count() > 0 else f"Naukri listing for {title}."

                    exp_el = card.locator(".expwdth, [class*='experience'], .ni-job-tuple-icon-srp-experience + span").first
                    exp_text = exp_el.inner_text(timeout=2000).strip() if exp_el.count() > 0 else ""
                    experience = 2.0
                    if exp_text:
                        exp_match = re.search(r"(\d+)", exp_text)
                        if exp_match:
                            experience = float(exp_match.group(1))

                    results.append({
                        "title": title,
                        "company": company.replace("\n", "").strip(),
                        "description": desc[:1200],
                        "url": job_url,
                        "location": loc.replace("\n", "").strip(),
                        "skills_required": [keyword.capitalize()],
                        "experience_required": experience
                    })
                except Exception as e:
                    logger.debug(f"Naukri card parse error: {e}")

            if card_count < 10:
                break
            client.human_delay(1500, 2500)

        return results[:max_jobs]

    def apply_job(
        self,
        page: Page,
        apply_url: str,
        resume_path: str,
        user_profile: Dict[str, Any],
        candidate_profile: Dict[str, Any],
        resume_id: int
    ) -> Dict[str, Any]:
        client = PlaywrightClient(page, "naukri")
        logs = []
        def log(msg):
            logger.info(msg)
            logs.append(msg)

        log(f"NaukriPortalPlugin: Loading job posting {apply_url}...")
        try:
            page.goto(apply_url, timeout=30000, wait_until="domcontentloaded")
            page.wait_for_timeout(3000)
            client.dismiss_popups()

            # Detect Apply Buttons
            apply_selectors = [
                "#apply-button", "button[id*='apply']", "button[class*='apply']", 
                "button:has-text('Apply')", "button:has-text('Apply Now')"
            ]

            clicked_apply = False
            for selector in apply_selectors:
                btn = page.locator(selector)
                if btn.count() > 0 and btn.first.is_visible():
                    log(f"NaukriPortalPlugin: Found apply button: {selector}")
                    
                    # Try to detect if this opens a pop-up tab redirecting to an external site
                    new_page = client.check_for_new_tab(lambda: btn.first.click())
                    if new_page:
                        new_url = new_page.url
                        log(f"NaukriPortalPlugin: Redirection to external company site detected: {new_url}")
                        # Handoff to corresponding ATS Plugin
                        ats_plugin = get_ats_plugin(new_url)
                        res = ats_plugin.fill_application(new_page, new_url, resume_path, user_profile, candidate_profile, resume_id)
                        return {
                            "success": res.get("success", False),
                            "logs": "\n".join(logs) + "\n" + res.get("logs", ""),
                            "error": res.get("error")
                        }
                    else:
                        clicked_apply = True
                        break

            if clicked_apply:
                page.wait_for_timeout(3000)
                client.dismiss_popups()

                # Quick Apply Form or chatbot questionnaire checking
                form_selectors = [
                    "[class*='chatbot']", "[class*='questionnaire']", 
                    ".apply-form", "form[name*='apply']"
                ]
                has_questions = False
                for f_sel in form_selectors:
                    if page.locator(f_sel).count() > 0:
                        has_questions = True
                        break
                
                if has_questions:
                    log("NaukriPortalPlugin: Quick Apply form or chatbot detected. Resolving questions...")
                    qa_agent = QuestionAnsweringAgent()
                    success_fill = self._fill_naukri_form(page, log, candidate_profile, resume_id, qa_agent)
                    if not success_fill:
                        client.capture_state_screenshot("naukri_manual_needed")
                        return {
                            "success": False,
                            "logs": "\n".join(logs),
                            "error": "Complex screening questions detected. Human intervention required.",
                            "needs_review": True
                        }

                log("NaukriPortalPlugin: Quick Apply successful.")
                client.capture_state_screenshot("naukri_quick_applied")
                return {"success": True, "logs": "\n".join(logs), "error": None}

            # If no in-page apply button was clickable, check for explicit external links
            redirect_selectors = [
                "button:has-text('Apply on company site')", 
                "a:has-text('Apply on company site')", 
                "button:has-text('Company Site')"
            ]
            for selector in redirect_selectors:
                btn = page.locator(selector)
                if btn.count() > 0 and btn.first.is_visible():
                    log("NaukriPortalPlugin: Found Company Site link. Redirecting...")
                    new_page = client.check_for_new_tab(lambda: btn.first.click())
                    if new_page:
                        new_url = new_page.url
                        log(f"NaukriPortalPlugin: Redirected to {new_url}. Routing to ATS...")
                        ats_plugin = get_ats_plugin(new_url)
                        res = ats_plugin.fill_application(new_page, new_url, resume_path, user_profile, candidate_profile, resume_id)
                        return {
                            "success": res.get("success", False),
                            "logs": "\n".join(logs) + "\n" + res.get("logs", ""),
                            "error": res.get("error")
                        }

            log("NaukriPortalPlugin: No apply pathways matched.")
            client.capture_state_screenshot("naukri_no_apply_found")
            return {"success": False, "logs": "\n".join(logs), "error": "No apply buttons found."}

        except Exception as e:
            client.capture_state_screenshot("naukri_apply_error")
            log(f"NaukriPortalPlugin Error: {e}")
            return {"success": False, "logs": "\n".join(logs), "error": str(e)}

    def _fill_naukri_form(
        self,
        page: Page,
        log,
        candidate_profile: Dict[str, Any],
        resume_id: int,
        qa_agent: QuestionAnsweringAgent
    ) -> bool:
        """Prefills questionnaire fields on Naukri."""
        inputs = page.locator("input[type='text'], input[type='number'], textarea")
        for i in range(inputs.count()):
            try:
                inp = inputs.nth(i)
                if not inp.is_visible() or inp.input_value().strip():
                    continue
                
                # Fetch question labels by checking siblings
                label = page.evaluate(
                    "(el) => {"
                    "  let parent = el.closest('.question, .field-wrapper, .chatbot-question');"
                    "  return parent ? parent.innerText : '';"
                    "}", inp
                )
                if not label:
                    label = (inp.get_attribute("name") or "") + " " + (inp.get_attribute("placeholder") or "")
                
                answer = qa_agent.generate_answer(resume_id, label, candidate_profile)
                inp.fill(answer)
                log(f"NaukriPortalPlugin: Filled '{label[:30]}...' -> '{answer}'")
                page.wait_for_timeout(300)
            except Exception:
                pass

        # Check if there are still unanswered required visible input fields
        visible_inputs = page.locator("input[required]:not([value])")
        for i in range(visible_inputs.count()):
            try:
                if visible_inputs.nth(i).is_visible() and not visible_inputs.nth(i).input_value().strip():
                    log("NaukriPortalPlugin: Form has unanswered mandatory fields.")
                    return False
            except Exception:
                pass
                
        return True
