import logging
import urllib.parse
from typing import List, Dict, Any, Optional
from playwright.sync_api import Page, expect

from backend.app.automation.portal_plugins.base_portal import BasePortal
from backend.app.automation.portal_plugins.registry import register_portal
from backend.app.automation.browser.playwright_client import PlaywrightClient
from backend.app.automation.question_engine.qa_agent import QuestionAnsweringAgent
from backend.app.automation.ats.ats_router import get_ats_plugin

logger = logging.getLogger("uvicorn.error")

@register_portal("linkedin")
class LinkedInPortalPlugin(BasePortal):
    """
    LinkedIn job board plugin implementing isolated login, search, filters,
    and Easy Apply / External Apply state management.
    """
    def login(self, page: Page, username: str, password: str) -> List[Dict[str, Any]]:
        client = PlaywrightClient(page, "linkedin")
        page.goto("https://www.linkedin.com/login", timeout=20000, wait_until="domcontentloaded")
        client.human_delay(1000, 2000)
        
        try:
            username_field = page.locator("#username")
            if username_field.count() > 0:
                username_field.fill(username)
            password_field = page.locator("#password")
            if password_field.count() > 0:
                password_field.fill(password)
            
            submit_btn = page.locator("button[type='submit']")
            if submit_btn.count() > 0:
                submit_btn.click()
        except Exception as e:
            logger.warning(f"LinkedIn login prefill failed: {e}")

        logger.info("LinkedIn: Waiting for manual/MFA login verification (120s max)...")
        success = False
        for _ in range(120):
            page.wait_for_timeout(1000)
            current_url = page.url
            parsed = urllib.parse.urlparse(current_url)
            path = parsed.path.lower()
            
            is_login_page = any(x in path for x in ["login", "signup", "authwall", "checkpoint"])
            reached_home = any(x in path for x in ["feed", "mynetwork", "jobs", "messaging"]) or path.startswith("/in/")
            
            nav_visible = False
            try:
                if page.locator("#global-nav, .global-nav__me").count() > 0:
                    nav_visible = True
            except Exception:
                pass
                
            if not is_login_page and (reached_home or nav_visible):
                success = True
                break
        
        if not success:
            client.capture_state_screenshot("login_timeout")
            raise TimeoutError("LinkedIn login verification timed out.")
            
        logger.info("LinkedIn login verified.")
        return page.context.cookies()

    def search_jobs(
        self,
        page: Page,
        keyword: str,
        location: str,
        filters: Dict[str, Any],
        max_jobs: int
    ) -> List[Dict[str, Any]]:
        client = PlaywrightClient(page, "linkedin")
        results = []
        seen_urls = set()
        page_size = 25
        start = 0
        
        filter_params = []
        posted_date = filters.get("posted_date")
        if posted_date == "24h":
            filter_params.append("f_TPR=r86400")
        elif posted_date == "3d":
            filter_params.append("f_TPR=r259200")
        elif posted_date == "7d":
            filter_params.append("f_TPR=r604800")
        elif posted_date == "15d":
            filter_params.append("f_TPR=r1209600")
        elif posted_date == "30d":
            filter_params.append("f_TPR=r2592000")

        exp = filters.get("experience_level")
        if exp == "entry":
            filter_params.append("f_E=2%2C3")
        elif exp == "mid":
            filter_params.append("f_E=3%2C4")
        elif exp == "senior":
            filter_params.append("f_E=4%2C5")

        remote = filters.get("remote_filter")
        if remote == "remote":
            filter_params.append("f_WT=2")
        elif remote == "hybrid":
            filter_params.append("f_WT=3")
        elif remote == "onsite":
            filter_params.append("f_WT=1")

        query_string = "&".join(filter_params)
        max_pages = (max_jobs // page_size) + 1

        for page_num in range(max_pages):
            if len(results) >= max_jobs:
                break
            
            search_url = (
                f"https://www.linkedin.com/jobs/search/"
                f"?keywords={urllib.parse.quote(keyword)}"
                f"&location={urllib.parse.quote(location)}"
                f"&start={start}"
            )
            if query_string:
                search_url += f"&{query_string}"
            
            logger.info(f"LinkedIn: Fetching search page {page_num + 1}...")
            page.goto(search_url, timeout=30000, wait_until="domcontentloaded")
            
            try:
                page.wait_for_selector(
                    ".job-card-container, .jobs-search-results__list-item, .scaffold-layout__list-item",
                    timeout=12000
                )
            except Exception:
                logger.warning("LinkedIn: No job cards visible.")
                break

            client.dismiss_popups()
            client.human_delay(500, 1000)
            client.scroll_to_bottom(1000, 5)

            job_cards = page.locator(".job-card-container, .jobs-search-results__list-item, .scaffold-layout__list-item")
            card_count = job_cards.count()
            
            if card_count == 0:
                break

            for i in range(card_count):
                if len(results) >= max_jobs:
                    break
                try:
                    card = job_cards.nth(i)
                    card.scroll_into_view_if_needed(timeout=2000)
                    
                    title_el = card.locator(".job-card-list__title, a.job-card-list__title-link, [class*='job-title']").first
                    title = title_el.inner_text(timeout=2000).strip() if title_el.count() > 0 else ""
                    if not title:
                        continue

                    comp_el = card.locator(".job-card-container__company-name, .job-card-list__company-name, [class*='company-name']").first
                    company = comp_el.inner_text(timeout=2000).strip() if comp_el.count() > 0 else "Unknown"

                    loc_el = card.locator(".job-card-container__metadata-item, .job-card-list__metadata-item, [class*='location']").first
                    loc = loc_el.inner_text(timeout=2000).strip() if loc_el.count() > 0 else "Remote"

                    link_el = card.locator("a.job-card-list__title-link, a.job-card-container__link, a[href*='/jobs/view/']").first
                    job_href = link_el.get_attribute("href") or ""
                    if not job_href:
                        continue

                    job_url = job_href.split("?")[0]
                    if not job_url.startswith("http"):
                        job_url = "https://www.linkedin.com" + job_url

                    if job_url in seen_urls:
                        continue
                    seen_urls.add(job_url)

                    results.append({
                        "title": title,
                        "company": company.replace("\n", "").strip(),
                        "description": f"LinkedIn job posting for {title} at {company} in {loc}.",
                        "url": job_url,
                        "location": loc.replace("\n", "").strip(),
                        "skills_required": [keyword.capitalize()],
                        "experience_required": 2.0
                    })
                except Exception as e:
                    logger.debug(f"Card parse error: {e}")

            if card_count < 10:
                break
            start += page_size
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
        client = PlaywrightClient(page, "linkedin")
        logs = []
        def log(msg):
            logger.info(msg)
            logs.append(msg)

        log(f"LinkedInPortalPlugin: Directing to {apply_url}")
        try:
            page.goto(apply_url, timeout=30000, wait_until="domcontentloaded")
            page.wait_for_timeout(3000)
            client.dismiss_popups()

            # 1. Validation Check: Check if Already Applied
            already_applied_indicators = [
                "span:has-text('Applied')",
                "span:has-text('Already Applied')",
                ".jobs-s-apply__applied-date",
                "button[disabled]:has-text('Applied')"
            ]
            for indicator in already_applied_indicators:
                if page.locator(indicator).count() > 0:
                    log("LinkedInPortalPlugin: Already applied to this job listing. Skipping.")
                    return {"success": True, "logs": "\n".join(logs) + "\nAlready applied."}

            # 2. Detect Easy Apply vs External Apply
            easy_apply_btn = page.locator("button.jobs-apply-button, button:has-text('Easy Apply')")
            if easy_apply_btn.count() == 0:
                # Fallback check for External Apply
                external_btn = page.locator("button:has-text('Apply'), a:has-text('Apply')")
                if external_btn.count() > 0:
                    log("LinkedInPortalPlugin: External apply detected. Redirecting...")
                    new_page = client.check_for_new_tab(lambda: external_btn.first.click())
                    if new_page:
                        new_url = new_page.url
                        log(f"LinkedInPortalPlugin: Redirected to {new_url}. Handing off to ATS Router...")
                        ats_plugin = get_ats_plugin(new_url)
                        res = ats_plugin.fill_application(new_page, new_url, resume_path, user_profile, candidate_profile, resume_id)
                        return {
                            "success": res.get("success", False),
                            "logs": "\n".join(logs) + "\n" + res.get("logs", ""),
                            "error": res.get("error")
                        }
                
                log("LinkedInPortalPlugin: No apply button identified.")
                return {"success": False, "logs": "\n".join(logs), "error": "No apply buttons found."}

            # 3. Trigger Easy Apply modal
            log("LinkedInPortalPlugin: Clicking Easy Apply...")
            easy_apply_btn.first.click()
            page.wait_for_timeout(2000)

            try:
                page.wait_for_selector(".jobs-easy-apply-modal, .artdeco-modal", timeout=8000)
                log("LinkedInPortalPlugin: Easy Apply Modal opened.")
            except Exception:
                return {"success": False, "logs": "\n".join(logs), "error": "Easy Apply modal did not render."}

            qa_agent = QuestionAnsweringAgent()

            # 4. Multi-step form loop
            for step in range(12):
                log(f"LinkedInPortalPlugin: Easy Apply Step {step + 1}")
                client.dismiss_popups()
                
                # A. Select or upload Resume
                file_input = page.locator("input[type='file']")
                if file_input.count() > 0:
                    # Look for existing resumes listed on page
                    uploaded_resume = page.locator("h3:has-text('resume'), .jobs-document-card__title")
                    # If multiple exist, we can select the first or just upload the tailored version to be sure
                    file_input.first.set_input_files(resume_path)
                    log("LinkedInPortalPlugin: Uploaded tailored resume.")
                    client.human_delay(1500, 2500)

                # B. Fill text inputs & textareas
                self._fill_text_fields(page, log, user_profile, candidate_profile, resume_id, qa_agent)
                
                # C. Handle radios and drop-downs
                self._fill_radios_and_selects(page, log, candidate_profile, resume_id, qa_agent)

                # D. Uncheck follow company checkbox
                follow_company = page.locator("input[id*='follow-company']")
                if follow_company.count() > 0 and follow_company.first.is_checked():
                    try:
                        follow_company.first.uncheck()
                        log("LinkedInPortalPlugin: Unchecked follow company.")
                    except Exception:
                        pass

                # E. Screen for validation error cues
                error_messages = page.locator(".artdeco-inline-feedback--error, .fb-form-element__error")
                if error_messages.count() > 0:
                    err_txt = error_messages.first.inner_text().strip()
                    log(f"LinkedInPortalPlugin: Validation error detected: {err_txt}")

                # F. Locate submit/next buttons
                submit_btn = page.locator("button:has-text('Submit application'), button:has-text('Submit')")
                review_btn = page.locator("button:has-text('Review')")
                next_btn = page.locator("button:has-text('Next')")

                if submit_btn.count() > 0 and submit_btn.first.is_enabled():
                    log("LinkedInPortalPlugin: Submit button is active. Submitting application...")
                    submit_btn.first.click()
                    page.wait_for_timeout(4000)
                    client.capture_state_screenshot("easy_apply_submitted")
                    return {"success": True, "logs": "\n".join(logs), "error": None}
                elif review_btn.count() > 0 and review_btn.first.is_enabled():
                    log("LinkedInPortalPlugin: Clicking Review...")
                    review_btn.first.click()
                    page.wait_for_timeout(1500)
                elif next_btn.count() > 0 and next_btn.first.is_enabled():
                    log("LinkedInPortalPlugin: Clicking Next...")
                    next_btn.first.click()
                    page.wait_for_timeout(1500)
                else:
                    # Modal stuck or missing mandatory fields. Request Human Review fallback
                    log("LinkedInPortalPlugin: Application stuck on step. Human action required.")
                    client.capture_state_screenshot("easy_apply_stuck")
                    return {
                        "success": False,
                        "logs": "\n".join(logs),
                        "error": "Form stuck. Requires human intervention.",
                        "needs_review": True
                    }

            return {"success": False, "logs": "\n".join(logs), "error": "Exceeded maximum Easy Apply steps (12)."}

        except Exception as e:
            client.capture_state_screenshot("easy_apply_error")
            log(f"LinkedInPortalPlugin Error: {e}")
            return {"success": False, "logs": "\n".join(logs), "error": str(e)}

    def _fill_text_fields(
        self,
        page: Page,
        log,
        user_profile: Dict[str, Any],
        candidate_profile: Dict[str, Any],
        resume_id: int,
        qa_agent: QuestionAnsweringAgent
    ):
        text_inputs = page.locator(".jobs-easy-apply-modal input[type='text'], .jobs-easy-apply-modal input[type='email'], .jobs-easy-apply-modal input[type='tel'], .jobs-easy-apply-modal textarea")
        for i in range(text_inputs.count()):
            try:
                inp = text_inputs.nth(i)
                if not inp.is_visible():
                    continue
                
                # Check if it has a prefilled value. If it's already filled, skip
                val = inp.input_value().strip()
                if val:
                    continue

                # Locate question label or description
                label = ""
                label_el = page.locator(f"label[for='{inp.get_attribute('id')}']")
                if label_el.count() > 0:
                    label = label_el.first.inner_text().strip()
                else:
                    # Check parent/ancestor spans
                    label = page.evaluate(
                        "(el) => { "
                        "  let parent = el.closest('.fb-form-element-role-title, .jobs-easy-apply-form-section__grouping');"
                        "  return parent ? parent.innerText : '';"
                        "}", inp
                    )
                
                if not label:
                    # Fallback to name/id fields
                    label = (inp.get_attribute("name") or "") + " " + (inp.get_attribute("id") or "")
                
                # Call QA Agent to generate answer
                answer = qa_agent.generate_answer(resume_id, label, candidate_profile)
                inp.fill(answer)
                log(f"LinkedInPortalPlugin: Filled '{label[:30]}...' -> '{answer}'")
                page.wait_for_timeout(300)
            except Exception as ex:
                logger.debug(f"Failed to fill text input: {ex}")

    def _fill_radios_and_selects(
        self,
        page: Page,
        log,
        candidate_profile: Dict[str, Any],
        resume_id: int,
        qa_agent: QuestionAnsweringAgent
    ):
        # 1. Dropdown Selects
        selects = page.locator(".jobs-easy-apply-modal select")
        for i in range(selects.count()):
            try:
                sel = selects.nth(i)
                if sel.is_visible() and not sel.input_value():
                    # Find label text
                    label = ""
                    label_el = page.locator(f"label[for='{sel.get_attribute('id')}']")
                    if label_el.count() > 0:
                        label = label_el.first.inner_text().strip()
                    
                    # Ask QA Agent to resolve
                    answer = qa_agent.generate_answer(resume_id, label, candidate_profile)
                    
                    # Find matching option
                    options = sel.locator("option")
                    matched_val = ""
                    for o_idx in range(options.count()):
                        val = options.nth(o_idx).get_attribute("value")
                        txt = options.nth(o_idx).inner_text().strip().lower()
                        if val and val.strip() and (answer.lower() in txt or txt in answer.lower()):
                            matched_val = val
                            break
                    
                    if not matched_val and options.count() > 1:
                        # Fallback to first non-empty option
                        for o_idx in range(options.count()):
                            val = options.nth(o_idx).get_attribute("value")
                            if val and val.strip():
                                matched_val = val
                                break
                    
                    if matched_val:
                        sel.select_option(value=matched_val)
                        log(f"LinkedInPortalPlugin: Selected dropdown for '{label[:30]}...' -> value '{matched_val}'")
            except Exception:
                pass

        # 2. Radio Groups
        fieldsets = page.locator(".jobs-easy-apply-modal fieldset")
        for i in range(fieldsets.count()):
            try:
                fieldset = fieldsets.nth(i)
                radios = fieldset.locator("input[type='radio']")
                if radios.count() > 0:
                    # Check if already checked
                    any_checked = False
                    for r_idx in range(radios.count()):
                        if radios.nth(r_idx).is_checked():
                            any_checked = True
                            break
                    
                    if not any_checked:
                        # Extract fieldset legend or label
                        legend_el = fieldset.locator("legend")
                        label = legend_el.first.inner_text().strip() if legend_el.count() > 0 else "Radio Question"
                        
                        answer = qa_agent.generate_answer(resume_id, label, candidate_profile)
                        
                        # Match radio options
                        clicked = False
                        for r_idx in range(radios.count()):
                            radio = radios.nth(r_idx)
                            # Find associated label text
                            radio_id = radio.get_attribute("id")
                            radio_lbl = fieldset.locator(f"label[for='{radio_id}']")
                            if radio_lbl.count() > 0:
                                radio_txt = radio_lbl.first.inner_text().strip().lower()
                                if answer.lower() in radio_txt or radio_txt in answer.lower() or (
                                    ("yes" in answer.lower() and "yes" in radio_txt) or 
                                    ("no" in answer.lower() and "no" in radio_txt)
                                ):
                                    radio.click()
                                    log(f"LinkedInPortalPlugin: Clicked radio '{radio_txt}' for '{label[:30]}...'")
                                    clicked = True
                                    break
                        
                        if not clicked:
                            # Fallback: prefer Yes if it exists, otherwise click first radio
                            yes_btn = fieldset.locator("label:has-text('Yes')")
                            if yes_btn.count() > 0:
                                yes_btn.first.click()
                            else:
                                radios.first.click()
                                log(f"LinkedInPortalPlugin: Clicked default radio option.")
            except Exception:
                pass
