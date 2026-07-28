import logging
import urllib.parse
from typing import List, Dict, Any
from playwright.sync_api import Page, expect

from backend.app.services.scraper.base_portal import BasePortal
from backend.app.services.scraper.registry import register_portal, get_ats_plugin
from backend.app.services.browser_manager import (
    capture_screenshot,
    dismiss_popups,
    human_delay,
    safe_click,
)

logger = logging.getLogger("uvicorn.error")

@register_portal("linkedin")
class LinkedInPortal(BasePortal):
    """
    LinkedIn job board plugin. Handles login, job discovery with advanced search filters,
    and multi-step application automation (Easy Apply vs External redirect).
    """

    def login(self, page: Page, username: str, password: str) -> List[Dict[str, Any]]:
        page.goto("https://www.linkedin.com/login", timeout=20000, wait_until="domcontentloaded")
        human_delay(page, 1000, 2000)
        
        try:
            username_field = page.locator("#username")
            if username_field.count() > 0:
                username_field.fill(username)
            password_field = page.locator("#password")
            if password_field.count() > 0:
                password_field.fill(password)
            
            # Click sign in if visible
            submit_btn = page.locator("button[type='submit']")
            if submit_btn.count() > 0:
                submit_btn.click()
        except Exception as e:
            logger.warning(f"LinkedIn: Prefilling fields failed: {e}")

        logger.info("LinkedIn: Awaiting manual/Google/MFA login completion (timeout: 120s)...")
        success = False
        for _ in range(120):
            page.wait_for_timeout(1000)
            current_url = page.url
            
            # Parse path to prevent matching query parameters like session_redirect=...jobs
            parsed = urllib.parse.urlparse(current_url)
            path = parsed.path.lower()
            
            is_login_page = any(x in path for x in ["login", "signup", "authwall", "checkpoint"])
            reached_feed = any(x in path for x in ["feed", "mynetwork", "jobs", "messaging"]) or path.startswith("/in/")
            
            nav_visible = False
            try:
                if page.locator("#global-nav, .global-nav__me").count() > 0:
                    nav_visible = True
            except Exception:
                pass
                
            if not is_login_page and (reached_feed or nav_visible):
                success = True
                break
        
        if not success:
            capture_screenshot(page, "linkedin_login_timeout")
            raise TimeoutError("LinkedIn login verification timed out.")
            
        logger.info("LinkedIn login successful.")
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
        page_size = 25
        start = 0
        
        # Build filter query params
        filter_params = []
        
        # Posted Date mapping
        # 24h -> r86400, 3d -> r259200, 7d -> r604800, 15d -> r1209600, 30d -> r2592000
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

        # Experience level mapping
        # entry -> associate/entry (2,3), mid -> associate/mid-senior (3,4), senior -> senior/director (4,5)
        exp = filters.get("experience_level")
        if exp == "entry":
            filter_params.append("f_E=2%2C3")
        elif exp == "mid":
            filter_params.append("f_E=3%2C4")
        elif exp == "senior":
            filter_params.append("f_E=4%2C5")

        # Remote filter mapping
        # remote -> 2, hybrid -> 3, onsite -> 1
        remote = filters.get("remote_filter")
        if remote == "remote":
            filter_params.append("f_WT=2")
        elif remote == "hybrid":
            filter_params.append("f_WT=3")
        elif remote == "onsite":
            filter_params.append("f_WT=1")

        # Job type mapping
        # full-time -> F, part-time -> P, contract -> C, internship -> I
        job_type = filters.get("job_type")
        if job_type == "full-time":
            filter_params.append("f_JT=F")
        elif job_type == "part-time":
            filter_params.append("f_JT=P")
        elif job_type == "contract":
            filter_params.append("f_JT=C")
        elif job_type == "internship":
            filter_params.append("f_JT=I")

        # Sorting
        # newest -> sortBy=DD, relevance -> sortBy=R
        sort_by = filters.get("sort_by")
        if sort_by == "newest":
            filter_params.append("sortBy=DD")
        else:
            filter_params.append("sortBy=R")

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
            
            logger.info(f"LinkedIn: Loading page {page_num + 1} (start={start})...")
            page.goto(search_url, timeout=30000, wait_until="domcontentloaded")
            
            try:
                page.wait_for_selector(
                    ".job-card-container, .jobs-search-results__list-item, "
                    "[data-occludable-job-id], .job-card-list__entity-lockup, "
                    ".scaffold-layout__list-item",
                    timeout=12000
                )
            except Exception:
                logger.warning(f"LinkedIn: No job cards rendered on page {page_num + 1}")
                break

            dismiss_popups(page)
            human_delay(page, 500, 1000)

            # Scroll results container to load all dynamic cards
            for _ in range(5):
                page.evaluate("""
                    const container = document.querySelector('.jobs-search-results-list, .scaffold-layout__list');
                    if (container) container.scrollTop = container.scrollHeight;
                    else window.scrollTo(0, document.body.scrollHeight);
                """)
                page.wait_for_timeout(1000)

            job_cards = page.locator(
                ".job-card-container, .jobs-search-results__list-item, "
                "[data-occludable-job-id], .job-card-list__entity-lockup, "
                ".scaffold-layout__list-item"
            )
            card_count = job_cards.count()
            logger.info(f"LinkedIn: Page {page_num + 1} has {card_count} job cards.")

            if card_count == 0:
                break

            page_results = self._extract_cards(page, job_cards, card_count, keyword, seen_urls)
            results.extend(page_results)

            if card_count < 10:
                break
                
            start += page_size
            human_delay(page, 1500, 2500)

        return results[:max_jobs]

    def _extract_cards(self, page: Page, job_cards, card_count: int, keyword: str, seen_urls: set) -> List[Dict[str, Any]]:
        page_results = []
        for i in range(card_count):
            try:
                card = job_cards.nth(i)
                card.scroll_into_view_if_needed(timeout=2000)
                
                title_el = card.locator(".job-card-list__title, a.job-card-list__title-link, [class*='job-title'], a.job-card-container__link strong")
                title = title_el.first.inner_text(timeout=2000).strip() if title_el.count() > 0 else ""
                if not title:
                    continue

                comp_el = card.locator(".job-card-container__company-name, .job-card-list__company-name, [class*='company-name']")
                company = comp_el.first.inner_text(timeout=2000).strip() if comp_el.count() > 0 else "Unknown"

                loc_el = card.locator(".job-card-container__metadata-item, .job-card-list__metadata-item, [class*='location']")
                loc = loc_el.first.inner_text(timeout=2000).strip() if loc_el.count() > 0 else "Remote"

                link_el = card.locator("a.job-card-list__title-link, a.job-card-container__link, a[href*='/jobs/view/']")
                job_href = link_el.first.get_attribute("href") or "" if link_el.count() > 0 else ""
                if not job_href:
                    continue

                job_url = job_href.split("?")[0]
                if not job_url.startswith("http"):
                    job_url = "https://www.linkedin.com" + job_url

                if job_url in seen_urls:
                    continue
                seen_urls.add(job_url)

                company = company.replace("\n", "").strip()
                loc = loc.replace("\n", "").strip()
                desc = f"LinkedIn listing for a {title} role at {company} ({loc})."

                page_results.append({
                    "title": title,
                    "company": company,
                    "description": desc,
                    "url": job_url,
                    "location": loc,
                    "skills_required": [keyword.capitalize()],
                    "experience_required": 2.0
                })
            except Exception as e:
                logger.debug(f"LinkedIn card extraction failed: {e}")
        return page_results

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

        log(f"LinkedInPortal: Loading {apply_url}...")
        try:
            page.goto(apply_url, timeout=30000, wait_until="domcontentloaded")
            page.wait_for_timeout(3000)
            dismiss_popups(page)

            # Check Easy Apply
            easy_apply_btn = page.locator("button.jobs-apply-button, button:has-text('Easy Apply')")
            if easy_apply_btn.count() == 0:
                # Might be an external apply
                external_apply_btn = page.locator("button:has-text('Apply'), a:has-text('Apply')")
                if external_apply_btn.count() > 0:
                    log("LinkedInPortal: Detected External Apply. Clicking and handing off to ATS adapter...")
                    try:
                        with page.expect_popup(timeout=10000) as popup_info:
                            external_apply_btn.first.click()
                        new_page = popup_info.value
                        new_page.wait_for_load_state("domcontentloaded")
                        new_url = new_page.url
                        log(f"LinkedInPortal: Switched to new tab: {new_url}")
                        
                        # Hand off to corresponding ATS plugin
                        ats_plugin = get_ats_plugin(new_url)
                        res = ats_plugin.fill_application(new_page, new_url, resume_path, user_profile)
                        return {
                            "success": res.get("success", False),
                            "logs": "\n".join(logs) + "\n" + res.get("logs", ""),
                            "error": res.get("error")
                        }
                    except Exception as redir_err:
                        log(f"LinkedInPortal External Handoff failed: {redir_err}")
                        return {"success": False, "logs": "\n".join(logs), "error": str(redir_err)}
                
                log("LinkedInPortal: No Easy Apply or External Apply buttons found.")
                return {"success": False, "logs": "\n".join(logs), "error": "No apply buttons found."}

            log("LinkedInPortal: Clicking Easy Apply...")
            easy_apply_btn.first.click()
            page.wait_for_timeout(2000)

            # Await Easy Apply Modal
            try:
                page.wait_for_selector(".jobs-easy-apply-modal, .artdeco-modal", timeout=8000)
                log("LinkedInPortal: Easy Apply modal open.")
            except Exception:
                return {"success": False, "logs": "\n".join(logs), "error": "Easy Apply modal didn't open."}

            # Multi-step flow loop
            for step in range(10):
                log(f"LinkedInPortal: Easy Apply Step {step + 1}")
                
                # Check for file input (Resume upload)
                file_input = page.locator("input[type='file']")
                if file_input.count() > 0:
                    file_input.first.set_input_files(resume_path)
                    log("LinkedInPortal: Uploaded resume.")
                    human_delay(page, 1000, 2000)

                # Fill standard text fields
                self._fill_fields(page, log, user_profile)
                
                # Handle radio groups and selects
                self._fill_radios_and_selects(page, log)

                # Validation: check for unfilled mandatory fields
                unanswered_mandatory = page.locator(
                    ".jobs-easy-apply-modal input[required][value=''], "
                    ".jobs-easy-apply-modal select[required]:not(:has(option:selected:not([value=''])))"
                )
                if unanswered_mandatory.count() > 0:
                    log("LinkedInPortal: Form has unanswered mandatory fields. Halting submission.")
                    capture_screenshot(page, "linkedin_mandatory_missing")
                    return {
                        "success": False,
                        "logs": "\n".join(logs),
                        "error": "Unanswered required questions. Action required."
                    }

                # Uncheck follow company
                follow_ch = page.locator("input[id*='follow-company']")
                if follow_ch.count() > 0 and follow_ch.first.is_checked():
                    try:
                        follow_ch.first.uncheck()
                        log("LinkedInPortal: Unchecked follow company.")
                    except Exception:
                        pass

                # Locate next/review/submit buttons
                submit_btn = page.locator("button:has-text('Submit application'), button:has-text('Submit')")
                review_btn = page.locator("button:has-text('Review')")
                next_btn = page.locator("button:has-text('Next')")

                if submit_btn.count() > 0 and submit_btn.first.is_enabled():
                    log("LinkedInPortal: Clicking Submit...")
                    submit_btn.first.click()
                    page.wait_for_timeout(4000)
                    capture_screenshot(page, "linkedin_submitted")
                    log("LinkedInPortal: Successfully submitted application.")
                    return {"success": True, "logs": "\n".join(logs), "error": None}
                elif review_btn.count() > 0 and review_btn.first.is_enabled():
                    log("LinkedInPortal: Clicking Review...")
                    review_btn.first.click()
                    page.wait_for_timeout(1000)
                elif next_btn.count() > 0 and next_btn.first.is_enabled():
                    log("LinkedInPortal: Clicking Next...")
                    next_btn.first.click()
                    page.wait_for_timeout(1000)
                else:
                    log("LinkedInPortal: Stuck on form step. Human action required.")
                    capture_screenshot(page, "linkedin_stuck")
                    return {
                        "success": False,
                        "logs": "\n".join(logs),
                        "error": "Form stuck. Dynamic or complex questions require manual completion."
                    }
            
            return {"success": False, "logs": "\n".join(logs), "error": "Exceeded maximum Easy Apply steps."}

        except Exception as e:
            capture_screenshot(page, "linkedin_apply_error")
            log(f"LinkedInPortal Error: {e}")
            return {"success": False, "logs": "\n".join(logs), "error": str(e)}

    def _fill_fields(self, page: Page, log, user_profile: Dict[str, Any]):
        first_name = user_profile.get("first_name", "")
        last_name = user_profile.get("last_name", "")
        email = user_profile.get("email", "")
        phone = user_profile.get("phone", "")

        text_inputs = page.locator(".jobs-easy-apply-modal input[type='text'], .jobs-easy-apply-modal input[type='email'], .jobs-easy-apply-modal input[type='tel']")
        for i in range(text_inputs.count()):
            try:
                inp = text_inputs.nth(i)
                if not inp.is_visible() or inp.input_value().strip():
                    continue
                
                combined = ((inp.get_attribute("id") or "") + (inp.get_attribute("name") or "") + (inp.get_attribute("aria-label") or "")).lower()
                
                if "first" in combined:
                    inp.fill(first_name)
                elif "last" in combined:
                    inp.fill(last_name)
                elif "email" in combined:
                    inp.fill(email)
                elif "phone" in combined and phone:
                    inp.fill(phone)
                elif "experience" in combined or "years" in combined:
                    inp.fill("2")
                else:
                    # Generic fallback fill
                    inp.fill("Yes")
            except Exception:
                pass

    def _fill_radios_and_selects(self, page: Page, log):
        # Handle simple select boxes
        selects = page.locator(".jobs-easy-apply-modal select")
        for i in range(selects.count()):
            try:
                sel = selects.nth(i)
                if sel.is_visible() and not sel.input_value():
                    options = sel.locator("option")
                    for o_idx in range(options.count()):
                        val = options.nth(o_idx).get_attribute("value")
                        if val and val.strip():
                            sel.select_option(value=val)
                            log(f"LinkedInPortal: Auto-selected dropdown: {val}")
                            break
            except Exception:
                pass

        # Handle radios
        fieldsets = page.locator(".jobs-easy-apply-modal fieldset")
        for i in range(fieldsets.count()):
            try:
                fieldset = fieldsets.nth(i)
                radios = fieldset.locator("input[type='radio']")
                if radios.count() > 0:
                    any_checked = False
                    for r_idx in range(radios.count()):
                        if radios.nth(r_idx).is_checked():
                            any_checked = True
                            break
                    if not any_checked:
                        # Prefer "Yes" if it exists, otherwise first option
                        yes_btn = fieldset.locator("label:has-text('Yes')")
                        if yes_btn.count() > 0:
                            yes_btn.first.click()
                        else:
                            radios.first.click()
            except Exception:
                pass
