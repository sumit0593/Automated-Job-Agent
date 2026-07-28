import logging
import urllib.parse
from typing import List, Dict, Any
from playwright.sync_api import Page
from backend.app.automation.portal_plugins.base_portal import BasePortal
from backend.app.automation.portal_plugins.registry import register_portal
from backend.app.automation.browser.playwright_client import PlaywrightClient
from backend.app.automation.ats.ats_router import get_ats_plugin

logger = logging.getLogger("uvicorn.error")

class BaseExtraPortal(BasePortal):
    """
    Subclass for extra portals that redirects directly to the ATS router.
    """
    def login(self, page: Page, username: str, password: str) -> List[Dict[str, Any]]:
        logger.info(f"Login not implemented/required for extra portal.")
        return []

    def search_jobs(self, page: Page, keyword: str, location: str, filters: Dict[str, Any], max_jobs: int) -> List[Dict[str, Any]]:
        logger.info(f"Search not implemented/required for extra portal.")
        return []

    def apply_job(
        self,
        page: Page,
        apply_url: str,
        resume_path: str,
        user_profile: Dict[str, Any],
        candidate_profile: Dict[str, Any],
        resume_id: int
    ) -> Dict[str, Any]:
        logger.info(f"Extra portal apply. Handing off to ATS Router for {apply_url}")
        plugin = get_ats_plugin(apply_url)
        return plugin.fill_application(page, apply_url, resume_path, user_profile, candidate_profile, resume_id)


@register_portal("indeed")
class IndeedPortalPlugin(BaseExtraPortal):
    def search_jobs(self, page: Page, keyword: str, location: str, filters: Dict[str, Any], max_jobs: int) -> List[Dict[str, Any]]:
        client = PlaywrightClient(page, "indeed")
        results = []
        seen_urls = set()
        start = 0
        
        filter_params = []
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

        query_string = "&".join(filter_params)
        max_pages = (max_jobs // 15) + 1

        for page_num in range(max_pages):
            if len(results) >= max_jobs:
                break
            
            search_url = f"https://www.indeed.com/jobs?q={urllib.parse.quote(keyword)}&l={urllib.parse.quote(location)}&start={start}"
            if query_string:
                search_url += f"&{query_string}"

            logger.info(f"Indeed: Fetching search page {page_num + 1}...")
            page.goto(search_url, timeout=30000, wait_until="domcontentloaded")
            
            try:
                page.wait_for_selector(".job_seen_beacon, td.resultContent", timeout=12000)
            except Exception:
                break

            client.dismiss_popups()
            client.human_delay(500, 1000)

            job_cards = page.locator(".job_seen_beacon, td.resultContent")
            card_count = job_cards.count()
            if card_count == 0:
                break

            for i in range(card_count):
                if len(results) >= max_jobs:
                    break
                try:
                    card = job_cards.nth(i)
                    title_el = card.locator("h2.jobTitle, a[class*='JobTitle']").first
                    title = title_el.inner_text(timeout=2000).strip() if title_el.count() > 0 else ""
                    if not title:
                        continue

                    comp_el = card.locator(".companyName, [data-testid='company-name']").first
                    company = comp_el.inner_text(timeout=2000).strip() if comp_el.count() > 0 else "Unknown"

                    loc_el = card.locator(".companyLocation, [data-testid='text-location']").first
                    loc = loc_el.inner_text(timeout=2000).strip() if loc_el.count() > 0 else "Remote"

                    link_el = card.locator("a[data-jk], h2.jobTitle a").first
                    job_jk = ""
                    if link_el.count() > 0:
                        job_jk = link_el.get_attribute("data-jk") or ""
                        if not job_jk:
                            href = link_el.get_attribute("href") or ""
                            if "jk=" in href:
                                job_jk = href.split("jk=")[1].split("&")[0]

                    if not job_jk:
                        continue

                    job_url = f"https://www.indeed.com/viewjob?jk={job_jk}"
                    if job_url in seen_urls:
                        continue
                    seen_urls.add(job_url)

                    results.append({
                        "title": title,
                        "company": company.replace("\n", "").strip(),
                        "description": f"Indeed listing for {title} at {company}.",
                        "url": job_url,
                        "location": loc.replace("\n", "").strip(),
                        "skills_required": [keyword.capitalize()],
                        "experience_required": 2.0
                    })
                except Exception as e:
                    logger.debug(f"Indeed card parse error: {e}")

            if card_count < 10:
                break
            start += 15
            client.human_delay(1500, 2500)

        return results[:max_jobs]


@register_portal("foundit")
class FounditPortalPlugin(BaseExtraPortal):
    pass

@register_portal("cutshort")
class CutshortPortalPlugin(BaseExtraPortal):
    pass

@register_portal("instahyre")
class InstahyrePortalPlugin(BaseExtraPortal):
    pass

@register_portal("wellfound")
class WellfoundPortalPlugin(BaseExtraPortal):
    pass

@register_portal("glassdoor")
class GlassdoorPortalPlugin(BaseExtraPortal):
    pass

@register_portal("hirist")
class HiristPortalPlugin(BaseExtraPortal):
    pass

@register_portal("company careers")
@register_portal("company_careers")
class CompanyCareersPortalPlugin(BaseExtraPortal):
    pass
