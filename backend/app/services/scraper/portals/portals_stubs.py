import logging
import urllib.parse
from typing import List, Dict, Any
from playwright.sync_api import Page
from backend.app.services.scraper.base_portal import BasePortal
from backend.app.services.scraper.registry import register_portal, get_ats_plugin

logger = logging.getLogger("uvicorn.error")

class BaseStubPortal(BasePortal):
    """
    Base class for stub/simple job boards. Default behavior: Heuristic search and generic handoff.
    """
    def login(self, page: Page, username: str, password: str) -> List[Dict[str, Any]]:
        logger.info(f"Login not configured/required for stub portal.")
        return []

    def search_jobs(self, page: Page, keyword: str, location: str, filters: Dict[str, Any], max_jobs: int) -> List[Dict[str, Any]]:
        logger.info(f"Stub search called for {self.__class__.__name__}. Returning empty search list.")
        return []

    def apply_job(self, page: Page, apply_url: str, resume_path: str, user_profile: Dict[str, Any]) -> Dict[str, Any]:
        logger.info(f"Stub portal apply. Handing off directly to ATS Adapter for {apply_url}")
        plugin = get_ats_plugin(apply_url)
        return plugin.fill_application(page, apply_url, resume_path, user_profile)


@register_portal("shine")
class ShinePortal(BaseStubPortal):
    pass

@register_portal("freshersworld")
class FreshersworldPortal(BaseStubPortal):
    pass

@register_portal("internshala")
class InternshalaPortal(BaseStubPortal):
    pass

@register_portal("iimjobs")
class IimjobsPortal(BaseStubPortal):
    pass

@register_portal("remoteok")
class RemoteOKPortal(BaseStubPortal):
    def search_jobs(self, page: Page, keyword: str, location: str, filters: Dict[str, Any], max_jobs: int) -> List[Dict[str, Any]]:
        results = []
        search_url = f"https://remoteok.com/remote-{urllib.parse.quote(keyword)}-jobs"
        logger.info(f"RemoteOK: Loading {search_url}...")
        try:
            page.goto(search_url, timeout=30000, wait_until="domcontentloaded")
            page.wait_for_timeout(3000)
            
            cards = page.locator("tr.job")
            count = min(cards.count(), max_jobs)
            for i in range(count):
                card = cards.nth(i)
                title = card.locator("h2").first.inner_text().strip()
                company = card.locator("h3").first.inner_text().strip()
                
                # Check for apply link
                apply_href = card.locator("a.preventDoubleBind").first.get_attribute("href") or ""
                url = f"https://remoteok.com{apply_href}" if apply_href else page.url
                
                results.append({
                    "title": title,
                    "company": company,
                    "description": f"RemoteOK listing: {title} at {company}.",
                    "url": url,
                    "location": "Remote",
                    "skills_required": [keyword.capitalize()],
                    "experience_required": 2.0
                })
        except Exception as e:
            logger.error(f"RemoteOK search failed: {e}")
        return results


@register_portal("weworkremotely")
class WeWorkRemotelyPortal(BaseStubPortal):
    def search_jobs(self, page: Page, keyword: str, location: str, filters: Dict[str, Any], max_jobs: int) -> List[Dict[str, Any]]:
        results = []
        search_url = f"https://weworkremotely.com/remote-jobs/search?term={urllib.parse.quote(keyword)}"
        logger.info(f"WeWorkRemotely: Loading {search_url}...")
        try:
            page.goto(search_url, timeout=30000, wait_until="domcontentloaded")
            page.wait_for_timeout(3000)
            
            cards = page.locator("article ul li")
            count = min(cards.count(), max_jobs)
            for i in range(count):
                card = cards.nth(i)
                title_el = card.locator("span.title")
                if title_el.count() == 0:
                    continue
                title = title_el.first.inner_text().strip()
                company = card.locator("span.company").first.inner_text().strip()
                href = card.locator("a[href*='/remote-jobs/']").first.get_attribute("href") or ""
                url = f"https://weworkremotely.com{href}" if href else page.url
                
                results.append({
                    "title": title,
                    "company": company,
                    "description": f"WeWorkRemotely listing: {title} at {company}.",
                    "url": url,
                    "location": "Remote",
                    "skills_required": [keyword.capitalize()],
                    "experience_required": 2.0
                })
        except Exception as e:
            logger.error(f"WeWorkRemotely search failed: {e}")
        return results


@register_portal("flexjobs")
class FlexJobsPortal(BaseStubPortal):
    pass


@register_portal("company career pages")
@register_portal("company_careers")
class CompanyCareersPortal(BaseStubPortal):
    pass
