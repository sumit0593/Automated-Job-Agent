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

@register_portal("foundit")
class FounditPortal(BasePortal):
    def login(self, page: Page, username: str, password: str) -> List[Dict[str, Any]]:
        page.goto("https://www.foundit.in/login", timeout=20000)
        # Placeholder for login filling
        page.wait_for_timeout(3000)
        return page.context.cookies()

    def search_jobs(self, page: Page, keyword: str, location: str, filters: Dict[str, Any], max_jobs: int) -> List[Dict[str, Any]]:
        results = []
        search_url = f"https://www.foundit.in/s/jobs?searchId=&k={urllib.parse.quote(keyword)}&l={urllib.parse.quote(location)}"
        logger.info(f"Foundit: Loading search {search_url}...")
        try:
            page.goto(search_url, timeout=30000, wait_until="domcontentloaded")
            page.wait_for_timeout(3000)
            dismiss_popups(page)
            
            cards = page.locator(".srpCard, [class*='srpCard']")
            count = min(cards.count(), max_jobs)
            for i in range(count):
                card = cards.nth(i)
                title = card.locator(".jobTitle, [class*='jobTitle']").first.inner_text().strip()
                company = card.locator(".companyName, [class*='companyName']").first.inner_text().strip()
                loc = card.locator(".location, [class*='location']").first.inner_text().strip()
                href = card.locator("a").first.get_attribute("href") or ""
                url = href.split("?")[0] if href else ""
                
                results.append({
                    "title": title,
                    "company": company,
                    "description": f"Foundit job listing for {title} at {company} in {loc}.",
                    "url": url if url.startswith("http") else f"https://www.foundit.in{url}",
                    "location": loc,
                    "skills_required": [keyword.capitalize()],
                    "experience_required": 2.0
                })
        except Exception as e:
            logger.error(f"Foundit search failed: {e}")
        return results

    def apply_job(self, page: Page, apply_url: str, resume_path: str, user_profile: Dict[str, Any]) -> Dict[str, Any]:
        logger.info(f"FounditPortal: Appling to {apply_url}...")
        # Heuristic generic apply
        plugin = get_ats_plugin(apply_url)
        return plugin.fill_application(page, apply_url, resume_path, user_profile)


@register_portal("cutshort")
class CutshortPortal(BasePortal):
    def login(self, page: Page, username: str, password: str) -> List[Dict[str, Any]]:
        page.goto("https://cutshort.io/login", timeout=20000)
        page.wait_for_timeout(3000)
        return page.context.cookies()

    def search_jobs(self, page: Page, keyword: str, location: str, filters: Dict[str, Any], max_jobs: int) -> List[Dict[str, Any]]:
        results = []
        search_url = f"https://cutshort.io/jobs?q={urllib.parse.quote(keyword)}"
        logger.info(f"Cutshort: Loading search {search_url}...")
        try:
            page.goto(search_url, timeout=30000, wait_until="domcontentloaded")
            page.wait_for_timeout(3000)
            
            cards = page.locator("[class*='JobCard'], .job-card")
            count = min(cards.count(), max_jobs)
            for i in range(count):
                card = cards.nth(i)
                title = card.locator("h3, [class*='title']").first.inner_text().strip()
                company = card.locator("[class*='companyName'], [class*='company']").first.inner_text().strip()
                loc = "India"
                
                results.append({
                    "title": title,
                    "company": company,
                    "description": f"Cutshort listing: {title} at {company}.",
                    "url": page.url,
                    "location": loc,
                    "skills_required": [keyword.capitalize()],
                    "experience_required": 2.0
                })
        except Exception as e:
            logger.error(f"Cutshort search failed: {e}")
        return results

    def apply_job(self, page: Page, apply_url: str, resume_path: str, user_profile: Dict[str, Any]) -> Dict[str, Any]:
        plugin = get_ats_plugin(apply_url)
        return plugin.fill_application(page, apply_url, resume_path, user_profile)


@register_portal("wellfound")
class WellfoundPortal(BasePortal):
    def login(self, page: Page, username: str, password: str) -> List[Dict[str, Any]]:
        page.goto("https://wellfound.com/login", timeout=20000)
        page.wait_for_timeout(3000)
        return page.context.cookies()

    def search_jobs(self, page: Page, keyword: str, location: str, filters: Dict[str, Any], max_jobs: int) -> List[Dict[str, Any]]:
        results = []
        search_url = f"https://wellfound.com/jobs?q={urllib.parse.quote(keyword)}"
        logger.info(f"Wellfound: Loading search {search_url}...")
        try:
            page.goto(search_url, timeout=30000, wait_until="domcontentloaded")
            page.wait_for_timeout(3000)
            
            cards = page.locator("[data-test='JobResult'], .styles_result__")
            count = min(cards.count(), max_jobs)
            for i in range(count):
                card = cards.nth(i)
                title = card.locator("h4, [class*='title']").first.inner_text().strip()
                company = card.locator("[class*='companyName']").first.inner_text().strip()
                
                results.append({
                    "title": title,
                    "company": company,
                    "description": f"Wellfound opportunity: {title} at {company}.",
                    "url": page.url,
                    "location": "Remote",
                    "skills_required": [keyword.capitalize()],
                    "experience_required": 2.0
                })
        except Exception as e:
            logger.error(f"Wellfound search failed: {e}")
        return results

    def apply_job(self, page: Page, apply_url: str, resume_path: str, user_profile: Dict[str, Any]) -> Dict[str, Any]:
        plugin = get_ats_plugin(apply_url)
        return plugin.fill_application(page, apply_url, resume_path, user_profile)


@register_portal("instahyre")
class InstahyrePortal(BasePortal):
    def login(self, page: Page, username: str, password: str) -> List[Dict[str, Any]]:
        page.goto("https://www.instahyre.com/login", timeout=20000)
        page.wait_for_timeout(3000)
        return page.context.cookies()

    def search_jobs(self, page: Page, keyword: str, location: str, filters: Dict[str, Any], max_jobs: int) -> List[Dict[str, Any]]:
        results = []
        search_url = f"https://www.instahyre.com/search-jobs?q={urllib.parse.quote(keyword)}"
        logger.info(f"Instahyre: Loading search {search_url}...")
        try:
            page.goto(search_url, timeout=30000, wait_until="domcontentloaded")
            page.wait_for_timeout(3000)
            
            cards = page.locator(".job-card, [id*='job-card']")
            count = min(cards.count(), max_jobs)
            for i in range(count):
                card = cards.nth(i)
                title = card.locator(".title, h3").first.inner_text().strip()
                company = card.locator(".company-name").first.inner_text().strip()
                
                results.append({
                    "title": title,
                    "company": company,
                    "description": f"Instahyre job: {title} at {company}.",
                    "url": page.url,
                    "location": "India",
                    "skills_required": [keyword.capitalize()],
                    "experience_required": 2.0
                })
        except Exception as e:
            logger.error(f"Instahyre search failed: {e}")
        return results

    def apply_job(self, page: Page, apply_url: str, resume_path: str, user_profile: Dict[str, Any]) -> Dict[str, Any]:
        plugin = get_ats_plugin(apply_url)
        return plugin.fill_application(page, apply_url, resume_path, user_profile)


@register_portal("hirist")
class HiristPortal(BasePortal):
    def login(self, page: Page, username: str, password: str) -> List[Dict[str, Any]]:
        page.goto("https://www.hirist.tech/login", timeout=20000)
        return page.context.cookies()

    def search_jobs(self, page: Page, keyword: str, location: str, filters: Dict[str, Any], max_jobs: int) -> List[Dict[str, Any]]:
        results = []
        search_url = f"https://www.hirist.tech/search.html?keyword={urllib.parse.quote(keyword)}"
        logger.info(f"Hirist: Loading search {search_url}...")
        try:
            page.goto(search_url, timeout=30000, wait_until="domcontentloaded")
            page.wait_for_timeout(3000)
            
            cards = page.locator(".job-box, .job-tuple")
            count = min(cards.count(), max_jobs)
            for i in range(count):
                card = cards.nth(i)
                title = card.locator(".job-title, h3").first.inner_text().strip()
                company = card.locator(".company-name").first.inner_text().strip()
                
                results.append({
                    "title": title,
                    "company": company,
                    "description": f"Hirist job: {title} at {company}.",
                    "url": page.url,
                    "location": "India",
                    "skills_required": [keyword.capitalize()],
                    "experience_required": 2.0
                })
        except Exception as e:
            logger.error(f"Hirist search failed: {e}")
        return results

    def apply_job(self, page: Page, apply_url: str, resume_path: str, user_profile: Dict[str, Any]) -> Dict[str, Any]:
        plugin = get_ats_plugin(apply_url)
        return plugin.fill_application(page, apply_url, resume_path, user_profile)


@register_portal("glassdoor")
class GlassdoorPortal(BasePortal):
    def login(self, page: Page, username: str, password: str) -> List[Dict[str, Any]]:
        page.goto("https://www.glassdoor.com/profile/login_input.htm", timeout=20000)
        return page.context.cookies()

    def search_jobs(self, page: Page, keyword: str, location: str, filters: Dict[str, Any], max_jobs: int) -> List[Dict[str, Any]]:
        results = []
        search_url = f"https://www.glassdoor.com/Job/jobs.htm?sc.keyword={urllib.parse.quote(keyword)}"
        logger.info(f"Glassdoor: Loading search {search_url}...")
        try:
            page.goto(search_url, timeout=30000, wait_until="domcontentloaded")
            page.wait_for_timeout(3000)
            
            cards = page.locator(".JobCard_jobCardWrapper__", "[class*='JobCard']")
            count = min(cards.count(), max_jobs)
            for i in range(count):
                card = cards.nth(i)
                title = card.locator("[data-test='job-title']").first.inner_text().strip()
                company = card.locator("[data-test='employer-shortname']").first.inner_text().strip()
                
                results.append({
                    "title": title,
                    "company": company,
                    "description": f"Glassdoor job: {title} at {company}.",
                    "url": page.url,
                    "location": "United States",
                    "skills_required": [keyword.capitalize()],
                    "experience_required": 2.0
                })
        except Exception as e:
            logger.error(f"Glassdoor search failed: {e}")
        return results

    def apply_job(self, page: Page, apply_url: str, resume_path: str, user_profile: Dict[str, Any]) -> Dict[str, Any]:
        plugin = get_ats_plugin(apply_url)
        return plugin.fill_application(page, apply_url, resume_path, user_profile)
