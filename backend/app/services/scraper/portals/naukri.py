import logging
import urllib.parse
import re
from typing import List, Dict, Any
from playwright.sync_api import Page

from backend.app.services.scraper.base_portal import BasePortal
from backend.app.services.scraper.registry import register_portal, get_ats_plugin
from backend.app.services.browser_manager import (
    capture_screenshot,
    dismiss_popups,
    human_delay,
    safe_click,
)

logger = logging.getLogger("uvicorn.error")

@register_portal("naukri")
class NaukriPortal(BasePortal):
    """
    Naukri job board plugin. Handles login, job discovery with advanced search filters,
    and application automation (Quick Apply vs External redirection).
    """

    def login(self, page: Page, username: str, password: str) -> List[Dict[str, Any]]:
        page.goto("https://www.naukri.com/nlogin/login", timeout=20000, wait_until="domcontentloaded")
        human_delay(page, 1000, 2000)
        
        try:
            username_field = page.locator("#usernameField")
            if username_field.count() > 0:
                username_field.fill(username)
            password_field = page.locator("#passwordField")
            if password_field.count() > 0:
                password_field.fill(password)
            
            # Submit button
            submit_btn = page.locator("button[type='submit']")
            if submit_btn.count() > 0:
                submit_btn.click()
        except Exception as e:
            logger.warning(f"Naukri: Prefilling fields failed: {e}")

        logger.info("Naukri: Awaiting manual login completion (timeout: 120s)...")
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
            capture_screenshot(page, "naukri_login_timeout")
            raise TimeoutError("Naukri login verification timed out.")
            
        logger.info("Naukri login successful.")
        return page.context.cookies()

    def search_jobs(
        self,
        page: Page,
        keyword: str,
        location: str,
        filters: Dict[str, Any],
        max_jobs: int
    ) -> List[Dict[str, Any]]:
        results = []
        seen_urls = set()
        
        # Build filter query params for Naukri
        filter_params = []
        
        # Posted Date mapping
        # 24h -> jobAge=1, 3d -> jobAge=3, 7d -> jobAge=7, 15d -> jobAge=15, 30d -> jobAge=30
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

        # Experience level mapping
        # entry -> 0-2, mid -> 2-5, senior -> 5-10
        exp = filters.get("experience_level")
        if exp == "entry":
            filter_params.append("experience=1") # 1 represents entry range in some Naukri API/Query mappings
        elif exp == "mid":
            filter_params.append("experience=3")
        elif exp == "senior":
            filter_params.append("experience=7")

        # Remote filter mapping
        # remote -> wfhType=0, hybrid -> wfhType=2, onsite -> wfhType=1
        remote = filters.get("remote_filter")
        if remote == "remote":
            filter_params.append("wfhType=0")
        elif remote == "hybrid":
            filter_params.append("wfhType=2")
        elif remote == "onsite":
            filter_params.append("wfhType=1")

        # Job type mapping
        # full-time -> jobType=0, contract -> jobType=2
        job_type = filters.get("job_type")
        if job_type == "full-time":
            filter_params.append("jobType=0")
        elif job_type == "contract":
            filter_params.append("jobType=2")

        # Sorting
        # newest -> sort=date, relevance -> sort=relevance
        sort_by = filters.get("sort_by")
        if sort_by == "newest":
            filter_params.append("sort=date")

        query_string = "&".join(filter_params)
        max_pages = min((max_jobs // 20) + 1, 10)  # Max 10 pages to be safe

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

            logger.info(f"Naukri: Loading page {page_num}...")
            page.goto(search_url, timeout=30000, wait_until="domcontentloaded")
            
            try:
                page.wait_for_selector(
                    "article.jobTuple, .srp-jobtuple-wrapper, [data-job-id], .cust-job-tuple, .styles_jlc__main__VfBbi",
                    timeout=12000
                )
            except Exception:
                logger.warning(f"Naukri: No job cards rendered on page {page_num}")
                break

            dismiss_popups(page)
            human_delay(page, 500, 1000)

            # Extract job cards
            job_cards = page.locator("article.jobTuple, .srp-jobtuple-wrapper, [data-job-id], .cust-job-tuple, .styles_jlc__main__VfBbi")
            card_count = job_cards.count()
            logger.info(f"Naukri: Page {page_num} has {card_count} job cards.")

            if card_count == 0:
                break

            for i in range(card_count):
                if len(results) >= max_jobs:
                    break
                try:
                    card = job_cards.nth(i)
                    
                    title_el = card.locator("a.title, a[class*='title'], .row1 a, [class*='jobTitle'], .info h2 a")
                    title = title_el.first.inner_text(timeout=2000).strip() if title_el.count() > 0 else ""
                    if not title:
                        continue

                    comp_el = card.locator("a.comp-name, a[class*='comp-name'], .comp-dtls-wrap a, [class*='company'], .subTitle a")
                    company = comp_el.first.inner_text(timeout=2000).strip() if comp_el.count() > 0 else "Unknown"

                    loc_el = card.locator(".loc-wrap span.loc, .location, .loc, [class*='location']")
                    loc = loc_el.first.inner_text(timeout=2000).strip() if loc_el.count() > 0 else "Remote"

                    link_el = card.locator("a.title, a[class*='title'], .row1 a, a[href*='/job-listings']")
                    job_href = link_el.first.get_attribute("href") or "" if link_el.count() > 0 else ""
                    if not job_href:
                        continue

                    job_url = job_href.split("?")[0]

                    if job_url in seen_urls:
                        continue
                    seen_urls.add(job_url)

                    desc_el = card.locator(".job-desc, .jobDescription, [class*='ellipsis'], [class*='description']")
                    desc = desc_el.first.inner_text(timeout=2000).strip() if desc_el.count() > 0 else ""
                    if not desc:
                        desc = f"Naukri listing for a {title} role at {company} ({loc})."

                    exp_el = card.locator(".expwdth, [class*='experience'], .ni-job-tuple-icon-srp-experience + span")
                    exp_text = exp_el.first.inner_text(timeout=2000).strip() if exp_el.count() > 0 else ""
                    experience = 2.0
                    if exp_text:
                        exp_match = re.search(r"(\d+)", exp_text)
                        if exp_match:
                            experience = float(exp_match.group(1))

                    results.append({
                        "title": title,
                        "company": company,
                        "description": desc[:1200],
                        "url": job_url,
                        "location": loc,
                        "skills_required": [keyword.capitalize()],
                        "experience_required": experience
                    })
                except Exception as e:
                    logger.debug(f"Naukri card extraction failed: {e}")

            if card_count < 10:
                break
            
            human_delay(page, 1500, 2500)

        return results[:max_jobs]

    def apply_job(
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

        # Force HTTPS scheme
        if apply_url.startswith("http://"):
            apply_url = "https://" + apply_url[7:]

        log(f"NaukriPortal: Loading {apply_url}...")
        try:
            page.goto(apply_url, timeout=30000, wait_until="domcontentloaded")
            page.wait_for_timeout(2000)

            # Check if Akamai / Edgesuite bot protection threw Access Denied on direct link
            if "access denied" in page.title().lower() or page.locator("h1:has-text('Access Denied')").count() > 0:
                log("NaukriPortal: Akamai Access Denied on direct URL. Recovering via homepage session...")
                page.goto("https://www.naukri.com", timeout=20000, wait_until="domcontentloaded")
                page.wait_for_timeout(2000)
                page.goto(apply_url, timeout=30000, wait_until="domcontentloaded")
                page.wait_for_timeout(3000)

            dismiss_popups(page)

            # 1. Check if job is ALREADY APPLIED on user's Naukri profile
            already_applied_selectors = [
                "button:has-text('Applied')",
                "span:has-text('Applied')",
                ":text('Already Applied')",
                "[class*='already-applied']",
                ".already-applied",
                ".styles_already-applied__1S0c2"
            ]
            for sel in already_applied_selectors:
                el = page.locator(sel)
                if el.count() > 0 and el.first.is_visible():
                    log("✅ NaukriPortal: Job is already applied on user's Naukri profile!")
                    capture_screenshot(page, "naukri_already_applied")
                    return {"success": True, "already_applied": True, "logs": "\n".join(logs) + "\nAlready applied on Naukri profile."}

            # 2. Selectors for apply button
            apply_selectors = [
                "#apply-button",
                "button.apply-button",
                ".apply-button-header",
                "[class*='applyButton']",
                "[class*='apply-button']",
                "[class*='applyBtn']",
                "[class*='apply-btn']",
                "button[id*='apply']",
                "button[class*='apply']",
                "button:has-text('Apply')",
                "button:has-text('Apply Now')",
                "button:has-text('Apply on site')",
                "button:has-text('Apply on company site')",
                "a:has-text('Apply on company site')",
                "a:has-text('Apply')",
                ".apply-container button"
            ]

            clicked_apply = False
            for selector in apply_selectors:
                btn = page.locator(selector)
                if btn.count() > 0 and btn.first.is_visible():
                    btn_text = (btn.first.inner_text() or "").strip()
                    if "applied" in btn_text.lower():
                        log("✅ NaukriPortal: Job is already applied on user's Naukri profile!")
                        return {"success": True, "already_applied": True, "logs": "\n".join(logs) + "\nAlready applied on Naukri profile."}

                    log(f"NaukriPortal: Clicking apply button ({selector}): '{btn_text}'")
                    
                    try:
                        # Open in new page or detect redirection
                        with page.expect_popup(timeout=8000) as popup_info:
                            btn.first.click()
                        
                        new_page = popup_info.value
                        new_page.wait_for_load_state("domcontentloaded")
                        new_url = new_page.url
                        log(f"NaukriPortal: Redirection detected to external site: {new_url}")
                        
                        # Hand off to ATS Adapter
                        ats_plugin = get_ats_plugin(new_url)
                        res = ats_plugin.fill_application(new_page, new_url, resume_path, user_profile)
                        return {
                            "success": res.get("success", False),
                            "logs": "\n".join(logs) + "\n" + res.get("logs", ""),
                            "error": res.get("error")
                        }
                    except Exception:
                        # No popup opened, stays in-page (Quick Apply)
                        clicked_apply = True
                        break

            if clicked_apply:
                page.wait_for_timeout(4000)
                dismiss_popups(page)

                # Check if in-page login modal popped up
                login_user = page.locator("#usernameField, input[placeholder*='Username'], input[name='email']")
                if login_user.count() > 0 and login_user.first.is_visible():
                    log("NaukriPortal: In-page login popup detected. Auto-authenticating...")
                    try:
                        from backend.app.database import SessionLocal
                        from backend.app import models
                        db = SessionLocal()
                        cred = db.query(models.UserCredential).filter(models.UserCredential.platform == "naukri").first()
                        db.close()

                        if cred and cred.username and cred.password:
                            login_user.first.fill(cred.username)
                            login_pass = page.locator("#passwordField, input[type='password']")
                            if login_pass.count() > 0:
                                login_pass.first.fill(cred.password)
                            submit = page.locator("button[type='submit'], button:has-text('Login')")
                            if submit.count() > 0:
                                submit.first.click()
                                page.wait_for_timeout(4000)
                                log("NaukriPortal: Authenticated via in-page login modal.")
                    except Exception as auth_err:
                        log(f"NaukriPortal: In-page login failed: {auth_err}")

                # Check if questionnaire appeared
                form_selectors = [
                    "[class*='chatbot']",
                    "[class*='questionnaire']",
                    ".apply-form",
                    "form[name*='apply']"
                ]
                
                has_questions = False
                for f_sel in form_selectors:
                    if page.locator(f_sel).count() > 0:
                        has_questions = True
                        break
                
                if has_questions:
                    log("NaukriPortal: Quick Apply form or chatbot detected.")
                    # Attempt heuristic filling of notice period, CTC, etc.
                    success_fill = self._fill_naukri_questions(page, log, user_profile)
                    if not success_fill:
                        capture_screenshot(page, "naukri_manual_required")
                        return {
                            "success": False,
                            "logs": "\n".join(logs),
                            "error": "Complex questionnaire detected. Action required by user."
                        }

                log("NaukriPortal: Quick Apply completed successfully on user's Naukri profile.")
                capture_screenshot(page, "naukri_quick_applied")
                return {"success": True, "logs": "\n".join(logs), "error": None}

            # Check for redirect links directly visible
            redirect_selectors = [
                "button:has-text('Apply on company site')",
                "a:has-text('Apply on company site')",
                "button:has-text('Company Site')"
            ]
            for selector in redirect_selectors:
                btn = page.locator(selector)
                if btn.count() > 0 and btn.first.is_visible():
                    log("NaukriPortal: Found external redirect button. Clicking...")
                    with page.expect_popup(timeout=10000) as popup_info:
                        btn.first.click()
                    new_page = popup_info.value
                    new_page.wait_for_load_state("domcontentloaded")
                    new_url = new_page.url
                    log(f"NaukriPortal: Handoff to external ATS: {new_url}")
                    
                    ats_plugin = get_ats_plugin(new_url)
                    res = ats_plugin.fill_application(new_page, new_url, resume_path, user_profile)
                    return {
                        "success": res.get("success", False),
                        "logs": "\n".join(logs) + "\n" + res.get("logs", ""),
                        "error": res.get("error")
                    }

            log("NaukriPortal: Could not find any Apply button.")
            capture_screenshot(page, "naukri_no_apply")
            return {"success": False, "logs": "\n".join(logs), "error": "No apply buttons found."}

        except Exception as e:
            capture_screenshot(page, "naukri_apply_error")
            log(f"NaukriPortal Error: {e}")
            return {"success": False, "logs": "\n".join(logs), "error": str(e)}

    def _fill_naukri_questions(self, page: Page, log, user_profile: Dict[str, Any]) -> bool:
        """
        Attempts to fill questionnaire fields heuristically.
        If complex unanswered required fields are found, returns False so it pauses for human review.
        """
        log("NaukriPortal: Filling chatbot / form questions...")
        
        # Heuristics for typical Indian tech job form questions
        notice_period = user_profile.get("notice_period", "Immediate")
        current_ctc = user_profile.get("current_ctc", "8,00,000")
        expected_ctc = user_profile.get("expected_ctc", "12,00,000")
        experience = str(user_profile.get("experience_years", "2"))

        # Look for text inputs containing matching labels
        inputs = page.locator("input[type='text'], input[type='number']")
        for i in range(inputs.count()):
            try:
                inp = inputs.nth(i)
                label_text = ""
                id_val = (inp.get_attribute("id") or "").lower()
                name_val = (inp.get_attribute("name") or "").lower()
                placeholder = (inp.get_attribute("placeholder") or "").lower()
                
                # Check siblings or parents for labels
                combined = id_val + name_val + placeholder
                
                if "notice" in combined:
                    inp.fill(notice_period)
                elif "current" in combined and "ctc" in combined:
                    inp.fill(current_ctc)
                elif "expected" in combined and "ctc" in combined:
                    inp.fill(expected_ctc)
                elif "experience" in combined:
                    inp.fill(experience)
            except Exception:
                pass

        # Check if there are still unanswered visible input fields
        visible_inputs = page.locator("input[required]:not([value])")
        for i in range(visible_inputs.count()):
            try:
                if visible_inputs.nth(i).is_visible() and not visible_inputs.nth(i).input_value():
                    log("NaukriPortal: Form has unanswered mandatory fields.")
                    return False
            except Exception:
                pass
                
        return True
