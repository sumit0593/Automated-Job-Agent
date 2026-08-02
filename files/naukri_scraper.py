"""
Naukri Scraper — BeautifulSoup4 (bs4)

WHY BeautifulSoup4 OVER OTHERS:
  - html.parser (stdlib)  : no CSS selector support, slow on large pages
  - lxml                  : fast but requires C lib, complex install on some hosts
  - BeautifulSoup4 + lxml : fastest + full CSS selector + forgiving malformed HTML
  - Scrapy                : overkill for single-site agent scraping

DECISION: bs4 with lxml backend for speed + full CSS selector power.
Playwright handles JS-rendered pages (fallback). bs4 handles static HTML.

ANTI-BOT HANDLING:
  - Randomized delays between requests
  - Rotating user agents
  - Session reuse (Naukri auth cookie)
  - Playwright fallback for JS-heavy / CAPTCHA pages
"""

import asyncio
import random
import logging
from typing import Optional

import httpx
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/123.0.0.0 Safari/537.36",
]

NAUKRI_BASE    = "https://www.naukri.com"
SEARCH_PATH    = "/jobapi/v3/search"
MIN_DELAY      = 2.0   # seconds between requests
MAX_DELAY      = 5.0


class NaukriScraper:

    def __init__(self, config: dict):
        self.config     = config
        self.cookies    = config.get("naukri_cookies", {})
        self.headers    = {
            "User-Agent":    random.choice(USER_AGENTS),
            "Accept":        "application/json, text/html,*/*",
            "Accept-Language": "en-US,en;q=0.9",
            "Referer":       NAUKRI_BASE,
        }
        self.search_params = config.get("search_params", {
            "keyword":  "software engineer",
            "location": "bangalore",
            "exp":      "2-5",
            "k":        20,       # results per page
        })

    # ─── Fetch Listings ──────────────────────────────────────────────────────

    async def fetch_job_listings(self) -> list[dict]:
        """
        Fetches job listings from Naukri API + HTML fallback.
        Returns list of normalized job dicts.
        """
        jobs = []
        async with httpx.AsyncClient(
            headers  = self.headers,
            cookies  = self.cookies,
            timeout  = 20,
            follow_redirects = True,
        ) as client:
            try:
                # Try JSON API first (fastest)
                resp = await client.get(NAUKRI_BASE + SEARCH_PATH, params=self.search_params)
                if resp.status_code == 200 and "application/json" in resp.headers.get("content-type",""):
                    data = resp.json()
                    jobs = self._parse_api_response(data)
                    logger.info(f"[Scraper] API: {len(jobs)} jobs")
                else:
                    # Fallback to HTML scrape
                    jobs = await self._scrape_html_listings(client)
            except Exception as e:
                logger.error(f"[Scraper] Fetch failed: {e}")

        return jobs

    async def _scrape_html_listings(self, client: httpx.AsyncClient) -> list[dict]:
        """Scrape listing page HTML using BeautifulSoup4 + lxml."""
        jobs = []
        search_url = (
            f"{NAUKRI_BASE}/{self.search_params.get('keyword','').replace(' ','-')}-jobs"
            f"-in-{self.search_params.get('location','')}"
        )
        await asyncio.sleep(random.uniform(MIN_DELAY, MAX_DELAY))

        resp = await client.get(search_url)
        if resp.status_code != 200:
            logger.warning(f"[Scraper] HTML listing returned {resp.status_code}")
            return []

        soup = BeautifulSoup(resp.text, "lxml")   # lxml backend = fastest + most tolerant
        cards = soup.select("article.jobTuple, div.job-container, div[data-job-id]")

        for card in cards:
            job = self._parse_listing_card(card)
            if job:
                jobs.append(job)
                await asyncio.sleep(random.uniform(0.1, 0.3))

        logger.info(f"[Scraper] HTML: {len(jobs)} jobs")
        return jobs

    # ─── Parse Helpers ───────────────────────────────────────────────────────

    def _parse_api_response(self, data: dict) -> list[dict]:
        jobs = []
        for item in data.get("jobDetails", []):
            jobs.append({
                "job_id":    str(item.get("jobId", "")),
                "title":     item.get("title", ""),
                "company":   item.get("companyName", ""),
                "url":       item.get("jdURL", ""),
                "apply_url": item.get("applyRedirectUrl", ""),
                "location":  item.get("placeholders", [{}])[0].get("label", ""),
                "tags":      item.get("tagsAndSkills", "").split(","),
                "raw":       item,
            })
        return jobs

    def _parse_listing_card(self, card) -> Optional[dict]:
        try:
            job_id  = card.get("data-job-id") or card.get("id", "")
            title   = self._text(card, "a.title, a.jobTitle, h2.title")
            company = self._text(card, "a.subTitle, span.comp-name, div.comp-name")
            url_el  = card.select_one("a.title, a.jobTitle")
            url     = (url_el.get("href","") if url_el else "")
            if url and not url.startswith("http"):
                url = NAUKRI_BASE + url
            tags_el = card.select("span.dot-separator, span.tag-li, li.tag-li")
            tags    = [t.get_text(strip=True) for t in tags_el]

            if not job_id or not title:
                return None

            return {
                "job_id":    job_id,
                "title":     title,
                "company":   company,
                "url":       url,
                "apply_url": "",
                "tags":      tags,
            }
        except Exception as e:
            logger.warning(f"[Scraper] Card parse failed: {e}")
            return None

    # ─── Fetch Single Job Detail ──────────────────────────────────────────────

    async def fetch_job_detail(self, url: str) -> Optional[dict]:
        """
        Fetches full HTML of a single job page.
        Used by ApplyEngine to get definitive job type + form structure.
        """
        await asyncio.sleep(random.uniform(MIN_DELAY, MAX_DELAY))
        async with httpx.AsyncClient(
            headers  = {**self.headers, "User-Agent": random.choice(USER_AGENTS)},
            cookies  = self.cookies,
            timeout  = 20,
        ) as client:
            try:
                resp = await client.get(url)
                if resp.status_code != 200:
                    return None
                soup = BeautifulSoup(resp.text, "lxml")
                return {
                    "html":        resp.text,
                    "soup":        soup,
                    "description": self._text(soup, "div.job-desc, section.job-desc, div#job-description"),
                    "skills":      [s.get_text(strip=True) for s in soup.select("span.tag-li, a.tech-stack")],
                }
            except Exception as e:
                logger.error(f"[Scraper] Detail fetch failed for {url}: {e}")
                return None

    # ─── Utility ─────────────────────────────────────────────────────────────

    @staticmethod
    def _text(el, selector: str) -> str:
        found = el.select_one(selector)
        return found.get_text(strip=True) if found else ""
