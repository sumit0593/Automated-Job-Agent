import logging
import urllib.parse
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

@register_portal("indeed")
class IndeedPortal(BasePortal):
    """
    Indeed job board plugin. Handles job discovery with advanced search filters
    and external ATS handoff for submissions.
    """

    def login(self, page: Page, username: str, password: str) -> List[Dict[str, Any]]:
        page.goto("https://secure.indeed.com/auth", timeout=20000, wait_until="domcontentloaded")
        human_delay(page, 1000, 2000)
        
        try:
            email_field = page.locator("#ifl-InputFormField-email")
            if email_field.count() > 0:
                email_field.fill(username)
                page.locator("button[type='submit']").click()
                page.wait_for_timeout(2000)
            
            password_field = page.locator("#ifl-InputFormField-password")
            if password_field.count() > 0:
                password_field.fill(password)
                page.locator("button[type='submit']").click()
        except Exception as e:
            logger.warning(f"Indeed: login prefill failed: {e}")

        logger.info("Indeed: Awaiting manual login completion (timeout: 120s)...")
        success = False
        for _ in range(120):
            page.wait_for_timeout(1000)
            if "indeed.com" in page.url and not "auth" in page.url:
                success = True
                break
            try:
                if page.locator("#gnav-main-container, .gnav-LoggedUser").count() > 0:
                    success = True
                    break
            except Exception:
                pass
        
        if not success:
            capture_screenshot(page, "indeed_login_timeout")
            raise TimeoutError("Indeed login verification timed out.")
            
        logger.info("Indeed login successful.")
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
        start = 0
        
        # Build filter query params for Indeed
        filter_params = []
        
        # Posted Date mapping (fromage: 1, 3, 7, 14, last)
        posted_date = filters.get("posted_date")
        if posted_date == "24h":
            filter_params.append("fromage=1")
        elif posted_date == "3d":
            filter_params.append("fromage=3")
        elif posted_date == "7d":
            filter_params.append("fromage=7")
        elif posted_date == "15d":
            filter_params.append("fromage=14")
        elif posted_date == "30d":
            filter_params.append("fromage=30")

        # Remote filter mapping
        # remote -> sc=0kf%3Aattr(DS5S1)%3B
        remote = filters.get("remote_filter")
        if remote == "remote":
            filter_params.append("sc=0kf%3Aattr(DS5S1)%3B")

        # Sorting (date or relevance)
        sort_by = filters.get("sort_by")
        if sort_by == "newest":
            filter_params.append("sort=date")

        query_string = "&".join(filter_params)
        max_pages = (max_jobs // 15) + 1

        for page_num in range(max_pages):
            if len(results) >= max_jobs:
                break
            
            search_url = (
                f"https://www.indeed.com/jobs"
                f"?q={urllib.parse.quote(keyword)}"
                f"&l={urllib.parse.quote(location)}"
                f"&start={start}"
            )
            if query_string:
                search_url += f"&{query_string}"

            logger.info(f"Indeed: Loading page {page_num + 1} (start={start})...")
            page.goto(search_url, timeout=30000, wait_until="domcontentloaded")
            
            try:
                page.wait_for_selector(
                    ".job_seen_beacon, td.resultContent, .slider_container",
                    timeout=12000
                )
            except Exception:
                logger.warning(f"Indeed: No job cards rendered on page {page_num + 1}")
                break

            dismiss_popups(page)
            human_delay(page, 500, 1000)

            # Extract job cards
            job_cards = page.locator(".job_seen_beacon, td.resultContent")
            card_count = job_cards.count()
            logger.info(f"Indeed: Page {page_num + 1} has {card_count} job cards.")

            if card_count == 0:
                break

            for i in range(card_count):
                if len(results) >= max_jobs:
                    break
                try:
                    card = job_cards.nth(i)
                    
                    title_el = card.locator("h2.jobTitle, a[class*='JobTitle']")
                    title = title_el.first.inner_text(timeout=2000).strip() if title_el.count() > 0 else ""
                    if not title:
                        continue

                    comp_el = card.locator(".companyName, [data-testid='company-name']")
                    company = comp_el.first.inner_text(timeout=2000).strip() if comp_el.count() > 0 else "Unknown"

                    loc_el = card.locator(".companyLocation, [data-testid='text-location']")
                    loc = loc_el.first.inner_text(timeout=2000).strip() if loc_el.count() > 0 else "Remote"

                    # Get URL
                    link_el = card.locator("a[data-jk], h2.jobTitle a")
                    job_jk = ""
                    if link_el.count() > 0:
                        job_jk = link_el.first.get_attribute("data-jk") or ""
                        if not job_jk:
                            href = link_el.first.get_attribute("href") or ""
                            if "jk=" in href:
                                job_jk = href.split("jk=")[1].split("&")[0]

                    if not job_jk:
                        continue

                    job_url = f"https://www.indeed.com/viewjob?jk={job_jk}"

                    if job_url in seen_urls:
                        continue
                    seen_urls.add(job_url)

                    desc = f"Indeed listing for a {title} role at {company} ({loc})."

                    results.append({
                        "title": title,
                        "company": company,
                        "description": desc,
                        "url": job_url,
                        "location": loc,
                        "skills_required": [keyword.capitalize()],
                        "experience_required": 2.0
                    })
                except Exception as e:
                    logger.debug(f"Indeed card extraction failed: {e}")

            if card_count < 10:
                break
                
            start += 15
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

        log(f"IndeedPortal: Loading {apply_url}...")
        try:
            page.goto(apply_url, timeout=30000, wait_until="domcontentloaded")
            page.wait_for_timeout(3000)
            dismiss_popups(page)

            # Check if indeed apply or external apply
            apply_btn = page.locator("#indeedApplyButton, button:has-text('Apply now')")
            if apply_btn.count() > 0:
                log("IndeedPortal: Found Indeed Quick Apply button. Clicking...")
                apply_btn.first.click()
                page.wait_for_timeout(4000)
                capture_screenshot(page, "indeed_quick_apply")
                return {"success": True, "logs": "\n".join(logs), "error": None}

            # Try external apply redirection
            external_btn = page.locator("button:has-text('Apply on company site'), a:has-text('Apply on company site')")
            if external_btn.count() > 0:
                log("IndeedPortal: Found External Apply redirect button. Clicking...")
                with page.expect_popup(timeout=10000) as popup_info:
                    external_btn.first.click()
                new_page = popup_info.value
                new_page.wait_for_load_state("domcontentloaded")
                new_url = new_page.url
                log(f"IndeedPortal: Switched to external page: {new_url}")

                # Handoff
                ats_plugin = get_ats_plugin(new_url)
                res = ats_plugin.fill_application(new_page, new_url, resume_path, user_profile)
                return {
                    "success": res.get("success", False),
                    "logs": "\n".join(logs) + "\n" + res.get("logs", ""),
                    "error": res.get("error")
                }

            log("IndeedPortal: Could not find any Apply button.")
            capture_screenshot(page, "indeed_no_apply")
            return {"success": False, "logs": "\n".join(logs), "error": "No apply buttons found."}

        except Exception as e:
            capture_screenshot(page, "indeed_apply_error")
            log(f"IndeedPortal Error: {e}")
            return {"success": False, "logs": "\n".join(logs), "error": str(e)}
