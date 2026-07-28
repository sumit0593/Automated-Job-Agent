"""
Job Scraper & Application Automation Service — Production-Grade Rewrite.

Fixes:
- Issue 1: Removes the hard-coded 8-job cap, adds pagination + infinite scroll
- Issue 2: Uses BrowserManager's launchPersistentContext() for session persistence
- Issue 3: Proper waits, retry logic, screenshot capture, multi-step form handling

All browser operations now go through browser_manager.py for consistent lifecycle management.
"""

import json
import logging
import urllib.request
import urllib.parse
import re
import time
from datetime import datetime
from typing import List, Dict, Any, Optional
from pathlib import Path

from backend.app.config import settings
from backend.app.services.browser_manager import (
    launch_persistent_browser,
    save_session_state,
    capture_screenshot,
    dismiss_popups,
    human_delay,
    safe_click,
    scroll_to_bottom,
    check_if_logged_in,
)

logger = logging.getLogger("uvicorn.error")

# ---------------------------------------------------------------------------
# ATS Detection
# ---------------------------------------------------------------------------

def detect_ats(url: str) -> str:
    """
    Analyzes job URL to detect the underlying ATS provider.
    """
    url_lower = url.lower()
    if "greenhouse.io" in url_lower:
        return "Greenhouse"
    elif "lever.co" in url_lower:
        return "Lever"
    elif "myworkdayjobs" in url_lower or "workday" in url_lower:
        return "Workday"
    elif "ashbyhq" in url_lower or "ashby" in url_lower:
        return "Ashby"
    elif "naukri.com" in url_lower:
        return "Naukri"
    elif "linkedin.com" in url_lower:
        return "LinkedIn"
    return "Generic"


# ---------------------------------------------------------------------------
# Greenhouse API Scraper (no browser needed)
# ---------------------------------------------------------------------------

def fetch_greenhouse_jobs(board_token: str) -> List[Dict[str, Any]]:
    """
    Fetches job listings from the Greenhouse board API for a specific company token.
    """
    url = f"https://boards-api.greenhouse.io/v1/boards/{board_token}/jobs?content=true"
    logger.info(f"Scraping Greenhouse board: {board_token} via API...")
    
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=15) as response:
            data = json.loads(response.read().decode("utf-8"))
            jobs = data.get("jobs", [])
            
            parsed_jobs = []
            for j in jobs:
                title = j.get("title")
                company = board_token.capitalize()
                job_url = j.get("absolute_url")
                location = j.get("location", {}).get("name", "Remote")
                description_html = j.get("content", "")
                
                description = re.sub('<[^<]+?>', '', description_html)
                
                skills = []
                for skill in ["python", "react", "fastapi", "aws", "docker", "kubernetes", "sql", "javascript", "typescript", "go", "machine learning", "pytorch"]:
                    if re.search(r"\b" + re.escape(skill) + r"\b", description.lower()):
                        skills.append(skill.capitalize())
                
                parsed_jobs.append({
                    "title": title,
                    "company": company,
                    "description": description[:1200],
                    "url": job_url,
                    "location": location,
                    "skills_required": skills,
                    "experience_required": 2.0
                })
            return parsed_jobs
    except Exception as e:
        logger.error(f"Failed to scrape Greenhouse board {board_token}: {e}")
        return []


# ---------------------------------------------------------------------------
# Platform Login (Persistent Context)
# ---------------------------------------------------------------------------

def login_to_platform(platform: str, username: str, password: str) -> List[Dict[str, Any]]:
    """
    Launches Playwright in headful mode with a PERSISTENT browser profile.
    Pre-fills fields if standard, and polls for up to 120s to let the user
    complete manual/Google/MFA login.
    
    Once successful landing is detected, saves the FULL session state
    (cookies + localStorage + IndexedDB) via the persistent profile directory.
    """
    pw = None
    context = None
    
    try:
        pw, context, page = launch_persistent_browser(
            platform=platform,
            headless=False,
        )
        
        if platform.lower() == "linkedin":
            # Check if already logged in from a previous session
            if check_if_logged_in(page, "linkedin"):
                logger.info("LinkedIn: Already authenticated from persistent profile!")
                state = save_session_state(context, platform)
                cookies = state.get("cookies", [])
                context.close()
                pw.stop()
                return cookies
            
            page.goto("https://www.linkedin.com/login", timeout=20000, wait_until="domcontentloaded")
            human_delay(page, 1000, 2000)
            
            # Fill fields as convenience if they exist
            try:
                username_field = page.locator("#username")
                if username_field.count() > 0:
                    username_field.fill(username)
                password_field = page.locator("#password")
                if password_field.count() > 0:
                    password_field.fill(password)
            except Exception:
                pass
            
            logger.info("Awaiting manual login completion (supports Google Sign-In, standard, MFA/OTPs). Timeout: 120s.")
            
            # Poll for feed/dashboard indicators for up to 120 seconds
            success = False
            for _ in range(120):
                time.sleep(1)
                current_url = page.url
                if any(x in current_url for x in ["feed", "mynetwork", "jobs", "messaging", "in/"]):
                    success = True
                    break
                try:
                    if page.locator("#global-nav, .global-nav__me, .search-global-typeahead").count() > 0:
                        success = True
                        break
                except Exception:
                    pass
            
            if not success:
                capture_screenshot(page, "linkedin_login_timeout")
                raise TimeoutError("LinkedIn login verification timed out (120s exceeded).")
                
        elif platform.lower() == "naukri":
            # Check if already logged in
            if check_if_logged_in(page, "naukri"):
                logger.info("Naukri: Already authenticated from persistent profile!")
                state = save_session_state(context, platform)
                cookies = state.get("cookies", [])
                context.close()
                pw.stop()
                return cookies
            
            page.goto("https://www.naukri.com/nlogin/login", timeout=20000, wait_until="domcontentloaded")
            human_delay(page, 1000, 2000)
            
            try:
                username_field = page.locator("#usernameField")
                if username_field.count() > 0:
                    username_field.fill(username)
                password_field = page.locator("#passwordField")
                if password_field.count() > 0:
                    password_field.fill(password)
            except Exception:
                pass
            
            logger.info("Awaiting manual login completion (supports Google Sign-In, standard, MFA/OTPs). Timeout: 120s.")
            
            success = False
            for _ in range(120):
                time.sleep(1)
                current_url = page.url
                if "mnjuser" in current_url or "homepage" in current_url:
                    success = True
                    break
                try:
                    if page.locator(".nI-gNb-drawer__toggle, .user-name, a[href*='logout']").count() > 0:
                        if "nlogin" not in current_url:
                            success = True
                            break
                except Exception:
                    pass
                    
            if not success:
                capture_screenshot(page, "naukri_login_timeout")
                raise TimeoutError("Naukri login verification timed out (120s exceeded).")
        else:
            raise ValueError(f"Platform {platform} login flow not implemented.")
            
        # Save full session state (cookies + localStorage + IndexedDB preserved in profile dir)
        state = save_session_state(context, platform)
        cookies = state.get("cookies", [])
        logger.info(f"Successfully captured login session for {platform}! ({len(cookies)} cookies)")
        
        context.close()
        pw.stop()
        return cookies
        
    except Exception as e:
        logger.error(f"Automation login failed for {platform}: {e}")
        if context:
            try:
                context.close()
            except Exception:
                pass
        if pw:
            try:
                pw.stop()
            except Exception:
                pass
        raise e


# ---------------------------------------------------------------------------
# Job Discovery with Pagination & Infinite Scroll (Persistent Context)
# ---------------------------------------------------------------------------

def discover_jobs_via_platform(
    platform: str,
    cookies: List[Dict[str, Any]],
    keyword: str,
    location: str = "",
    max_jobs: int = 100,
) -> List[Dict[str, Any]]:
    """
    Log in using persistent browser profile and fetch job listings from job portals.
    
    Key improvements over original:
    - No hard-coded job cap (configurable max_jobs, default 100)
    - Pagination support (LinkedIn: ?start=0,25,50... Naukri: -page-N)
    - Infinite scroll handling for LinkedIn
    - Deduplication by URL within session
    - Proper waits instead of fixed timeouts
    - Screenshot capture on errors
    """
    pw = None
    context = None
    
    logger.info(f"Job discovery started on {platform} for '{keyword}' (max: {max_jobs})...")
    results = []
    seen_urls = set()  # Deduplication within this session
    
    try:
        pw, context, page = launch_persistent_browser(
            platform=platform,
            headless=False,
        )
        
        # Add supplementary cookies from DB if available
        if cookies:
            try:
                context.add_cookies(cookies)
            except Exception as e:
                logger.warning(f"Could not add supplementary cookies: {e}")
        
        if platform.lower() == "linkedin":
            results = _scrape_linkedin_jobs(page, keyword, location, max_jobs, seen_urls)
            
        elif platform.lower() == "naukri":
            results = _scrape_naukri_jobs(page, keyword, location, max_jobs, seen_urls)
            
        else:
            logger.warning(f"Crawling not supported for platform {platform}")
        
        # Save session state after scraping
        save_session_state(context, platform)
        
        context.close()
        pw.stop()
        return results
        
    except Exception as e:
        logger.error(f"Error executing crawler on {platform}: {e}")
        if context:
            try:
                if context.pages:
                    capture_screenshot(context.pages[0], f"{platform}_scrape_error")
                context.close()
            except Exception:
                pass
        if pw:
            try:
                pw.stop()
            except Exception:
                pass
        return results  # Return whatever we collected before the error


def _scrape_linkedin_jobs(
    page, keyword: str, location: str, max_jobs: int, seen_urls: set
) -> List[Dict[str, Any]]:
    """
    Scrapes LinkedIn job listings with pagination and infinite scroll.
    LinkedIn pagination uses ?start=0, 25, 50, 75...
    """
    results = []
    page_size = 25  # LinkedIn loads ~25 jobs per page
    start = 0
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
        
        logger.info(f"LinkedIn: Loading page {page_num + 1} (start={start})...")
        page.goto(search_url, timeout=30000, wait_until="domcontentloaded")
        
        # Wait for job cards to render
        try:
            page.wait_for_selector(
                ".job-card-container, .jobs-search-results__list-item, "
                "[data-occludable-job-id], .job-card-list__entity-lockup, "
                ".scaffold-layout__list-item",
                timeout=15000
            )
        except Exception:
            logger.warning(f"No job cards found on LinkedIn page {page_num + 1}.")
            capture_screenshot(page, f"linkedin_no_cards_page{page_num + 1}")
            if page_num == 0:
                # First page has no results — check if login redirect happened
                if "login" in page.url or "authwall" in page.url:
                    logger.error("LinkedIn redirected to login — session expired.")
                    capture_screenshot(page, "linkedin_login_redirect")
                break
            else:
                break  # No more pages
        
        # Scroll down within the job list to load all cards on this page
        dismiss_popups(page)
        human_delay(page, 500, 1000)
        
        # Scroll the results container to load lazy-rendered cards
        for scroll_i in range(5):
            page.evaluate("""
                const container = document.querySelector('.jobs-search-results-list, .scaffold-layout__list');
                if (container) container.scrollTop = container.scrollHeight;
                else window.scrollTo(0, document.body.scrollHeight);
            """)
            page.wait_for_timeout(1200)
        
        # Extract job cards
        job_cards = page.locator(
            ".job-card-container, .jobs-search-results__list-item, "
            "[data-occludable-job-id], .job-card-list__entity-lockup, "
            ".scaffold-layout__list-item"
        )
        card_count = job_cards.count()
        logger.info(f"LinkedIn page {page_num + 1}: Found {card_count} job cards.")
        
        if card_count == 0:
            break
        
        page_results = _extract_linkedin_cards(page, job_cards, card_count, keyword, seen_urls)
        results.extend(page_results)
        
        logger.info(f"LinkedIn: Extracted {len(page_results)} new jobs from page {page_num + 1}. Total: {len(results)}")
        
        # If fewer cards than expected, we've likely reached the last page
        if card_count < 10:
            logger.info("LinkedIn: Fewer than 10 cards — likely last page.")
            break
        
        start += page_size
        human_delay(page, 1500, 3000)  # Human-like delay between pages
    
    logger.info(f"LinkedIn scraping complete. Total jobs collected: {len(results)}")
    return results[:max_jobs]


def _extract_linkedin_cards(
    page, job_cards, card_count: int, keyword: str, seen_urls: set
) -> List[Dict[str, Any]]:
    """Extracts job data from LinkedIn job cards on the current page."""
    results = []
    
    for i in range(card_count):
        try:
            card = job_cards.nth(i)
            
            # Scroll card into view
            try:
                card.scroll_into_view_if_needed(timeout=3000)
            except Exception:
                pass
            
            # Extract title
            title_el = card.locator(
                ".job-card-list__title, a.job-card-list__title-link, "
                "[class*='job-title'], .artdeco-entity-lockup__title, "
                "a.job-card-container__link strong"
            )
            title = title_el.first.inner_text(timeout=3000).strip() if title_el.count() > 0 else ""
            if not title:
                continue  # Skip cards without titles
            
            # Extract company
            comp_el = card.locator(
                ".job-card-container__primary-description, "
                ".job-card-container__company-name, "
                ".job-card-list__company-name, "
                ".artdeco-entity-lockup__subtitle, "
                "[class*='company-name']"
            )
            company = comp_el.first.inner_text(timeout=3000).strip() if comp_el.count() > 0 else "Unknown"
            
            # Extract location
            loc_el = card.locator(
                ".job-card-container__metadata-item, "
                ".job-card-list__metadata-item, "
                ".artdeco-entity-lockup__caption, "
                "[class*='location']"
            )
            loc = loc_el.first.inner_text(timeout=3000).strip() if loc_el.count() > 0 else "Remote"
            
            # Extract URL
            link_el = card.locator(
                "a.job-card-list__title-link, "
                "a.job-card-container__link, "
                "a[class*='job-card'], "
                "a[href*='/jobs/view/']"
            )
            job_href = ""
            if link_el.count() > 0:
                job_href = link_el.first.get_attribute("href") or ""
            
            if job_href:
                job_url = job_href.split("?")[0]
                if not job_url.startswith("http"):
                    job_url = "https://www.linkedin.com" + job_url
            else:
                continue  # Skip if no URL found
            
            # Deduplication
            if job_url in seen_urls:
                continue
            seen_urls.add(job_url)
            
            # Clean strings
            company = company.replace("\n", "").strip()
            loc = loc.replace("\n", "").strip()
            
            desc = f"Active opportunity for a {title} position at {company} located in {loc}. Apply now."
            
            results.append({
                "title": title,
                "company": company,
                "description": desc,
                "url": job_url,
                "location": loc,
                "skills_required": [keyword.capitalize()],
                "experience_required": 2.0
            })
        except Exception as card_err:
            logger.warning(f"Error parsing LinkedIn job card {i}: {card_err}")
    
    return results


def _scrape_naukri_jobs(
    page, keyword: str, location: str, max_jobs: int, seen_urls: set
) -> List[Dict[str, Any]]:
    """
    Scrapes Naukri job listings with pagination.
    Naukri pagination uses URL pattern: /jobs-in-india-page-2, -page-3, etc.
    """
    results = []
    max_pages = min((max_jobs // 20) + 1, 10)  # Naukri shows ~20 per page, cap at 10 pages
    
    for page_num in range(1, max_pages + 1):
        if len(results) >= max_jobs:
            break
        
        if page_num == 1:
            search_url = f"https://www.naukri.com/jobs-in-india?k={urllib.parse.quote(keyword)}"
            if location:
                search_url += f"&l={urllib.parse.quote(location)}"
        else:
            search_url = f"https://www.naukri.com/jobs-in-india-page-{page_num}?k={urllib.parse.quote(keyword)}"
            if location:
                search_url += f"&l={urllib.parse.quote(location)}"
        
        logger.info(f"Naukri: Loading page {page_num}...")
        page.goto(search_url, timeout=30000, wait_until="domcontentloaded")
        
        # Wait for job cards with resilient selectors
        try:
            page.wait_for_selector(
                "article.jobTuple, .srp-jobtuple-wrapper, "
                "[data-job-id], .cust-job-tuple, "
                ".list-container .jobTuple, .styles_jlc__main__VfBbi",
                timeout=12000
            )
        except Exception:
            logger.warning(f"No job cards found on Naukri page {page_num}.")
            if page_num == 1:
                capture_screenshot(page, "naukri_no_cards")
                # Check for login redirect
                if "nlogin" in page.url:
                    logger.error("Naukri redirected to login — session expired.")
                    capture_screenshot(page, "naukri_login_redirect")
                break
            else:
                break
        
        dismiss_popups(page)
        human_delay(page, 500, 1000)
        
        # Extract job cards with resilient selectors
        job_cards = page.locator(
            "article.jobTuple, .srp-jobtuple-wrapper, "
            "[data-job-id], .cust-job-tuple, "
            ".list-container .jobTuple, .styles_jlc__main__VfBbi"
        )
        card_count = job_cards.count()
        logger.info(f"Naukri page {page_num}: Found {card_count} job cards.")
        
        if card_count == 0:
            break
        
        for i in range(card_count):
            if len(results) >= max_jobs:
                break
                
            try:
                card = job_cards.nth(i)
                
                # Extract title — use multiple selector strategies
                title_el = card.locator(
                    "a.title, a[class*='title'], .row1 a, "
                    "[class*='jobTitle'], .info h2 a, a[class*='designation']"
                )
                title = title_el.first.inner_text(timeout=3000).strip() if title_el.count() > 0 else ""
                if not title:
                    continue
                
                # Extract company
                comp_el = card.locator(
                    "a.comp-name, a[class*='comp-name'], .comp-dtls-wrap a, "
                    "[class*='company'], .subTitle a, a[class*='companyName']"
                )
                company = comp_el.first.inner_text(timeout=3000).strip() if comp_el.count() > 0 else "Unknown"
                
                # Extract location
                loc_el = card.locator(
                    ".loc-wrap span.loc, .location, .loc, "
                    "[class*='location'], .locWrap span, .ni-job-tuple-icon-srp-location + span"
                )
                loc = loc_el.first.inner_text(timeout=3000).strip() if loc_el.count() > 0 else "Remote"
                
                # Extract URL
                link_el = card.locator(
                    "a.title, a[class*='title'], .row1 a, "
                    "a[href*='/job-listings'], a[href*='jobId']"
                )
                job_href = ""
                if link_el.count() > 0:
                    job_href = link_el.first.get_attribute("href") or ""
                
                job_url = job_href.split("?")[0] if job_href else ""
                if not job_url:
                    continue
                
                # Deduplication
                if job_url in seen_urls:
                    continue
                seen_urls.add(job_url)
                
                # Extract description snippet
                desc_el = card.locator(
                    ".job-desc, .jobDescription, [class*='ellipsis'], "
                    ".row3 .job-desc, [class*='description']"
                )
                desc = desc_el.first.inner_text(timeout=3000).strip() if desc_el.count() > 0 else ""
                if not desc:
                    desc = f"Opportunity for {title} at {company} in {loc}."
                
                # Extract experience if available
                exp_el = card.locator(
                    ".expwdth, [class*='experience'], .ni-job-tuple-icon-srp-experience + span"
                )
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
            except Exception as card_err:
                logger.warning(f"Error parsing Naukri job card {i}: {card_err}")
        
        logger.info(f"Naukri: Extracted jobs from page {page_num}. Total: {len(results)}")
        
        # If fewer cards than expected, likely last page
        if card_count < 10:
            break
        
        human_delay(page, 1500, 3000)
    
    logger.info(f"Naukri scraping complete. Total jobs collected: {len(results)}")
    return results[:max_jobs]


# ---------------------------------------------------------------------------
# Fallback Web Search (Greenhouse boards)
# ---------------------------------------------------------------------------

def search_jobs_on_web(query: str, location: str = "") -> List[Dict[str, Any]]:
    """
    Fallbacks to corporate board scrapers if keyword matches standard tech tags.
    """
    normalized_query = query.lower().strip()
    if normalized_query and " " not in normalized_query:
        greenhouse_jobs = fetch_greenhouse_jobs(normalized_query)
        if greenhouse_jobs:
            return greenhouse_jobs
            
    # Check if a known Greenhouse board is part of query
    greenhouse_boards = ["stripe", "figma", "airbnb", "reddit", "lyft", "github"]
    for board in greenhouse_boards:
        if board in normalized_query:
            return fetch_greenhouse_jobs(board)
            
    return []


# ---------------------------------------------------------------------------
# Application Automation (Persistent Context + Retry + Screenshots)
# ---------------------------------------------------------------------------

def automate_application_flow(
    apply_url: str,
    first_name: str,
    last_name: str,
    email: str,
    resume_path: str,
    phone: str = "",
    cover_letter: str = "",
    headful: bool = True,
    cookies: Optional[List[Dict[str, Any]]] = None,
    platform: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Fills application forms on Greenhouse, Lever, Workday, Ashby, LinkedIn, and Naukri.
    
    Uses persistent browser context for authentication.
    Includes retry logic, screenshot capture, and proper wait strategies.
    """
    import os
    
    abs_resume_path = os.path.abspath(resume_path)
    if not os.path.exists(abs_resume_path):
        return {"success": False, "error": f"Resume file not found at path: {abs_resume_path}"}
    
    logs = []
    def log(msg: str):
        logger.info(msg)
        logs.append(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")
    
    ats_platform = detect_ats(apply_url)
    
    # Determine which browser profile to use
    if not platform:
        if ats_platform == "LinkedIn":
            platform = "linkedin"
        elif ats_platform == "Naukri":
            platform = "naukri"
        else:
            platform = "generic"
    
    log(f"Starting application automation for URL: {apply_url}")
    log(f"Detected ATS platform: {ats_platform}")
    log(f"Using browser profile: {platform}")
    
    pw = None
    context = None
    
    try:
        pw, context, page = launch_persistent_browser(
            platform=platform,
            headless=not headful,
        )
        
        # Add supplementary cookies if provided
        if cookies:
            try:
                context.add_cookies(cookies)
            except Exception as e:
                log(f"Warning: Could not add supplementary cookies: {e}")
        
        log("Navigating to application page...")
        page.goto(apply_url, timeout=30000, wait_until="domcontentloaded")
        
        # Wait for page to settle (avoid networkidle which hangs on LinkedIn)
        page.wait_for_timeout(3000)
        
        # Dismiss any popups/banners
        dismiss_popups(page)
        
        # Classify application type before clicking Apply
        from backend.app.automation.classifier.app_classifier import classify_application_type
        from backend.app.automation.classifier.external_page_detector import detect_new_external_page
        from backend.app.automation.ats.ats_router import get_ats_plugin, detect_ats

        app_classification = classify_application_type(page, apply_url)
        log(f"Classified Application Type: '{app_classification['type']}' ({app_classification['details']})")
        
        # Target page defaults to current page unless external website opens a new tab
        target_page = page
        
        if app_classification['type'] == 'External Website' or len(context.pages) > 1:
            log("External Website detected. Monitoring for newly opened popup window/tab...")
            try:
                external_btn = page.locator("a:has-text('Apply on Company Site'), a:has-text('Apply'), button:has-text('Apply')")
                if external_btn.count() > 0:
                    target_page = detect_new_external_page(
                        context=context,
                        action_trigger=lambda: external_btn.first.click(),
                        timeout_ms=5000
                    )
            except Exception as ex:
                log(f"New tab listener fallback: {ex}")
                if len(context.pages) > 1:
                    target_page = context.pages[-1]

        # Route page to dedicated modular ATS handler
        if app_classification['type'] == 'Recruiter Chatbot':
            dest_ats_name = 'recruiter_chatbot'
            ats_handler = get_ats_plugin('chatbot')
        else:
            dest_ats_name = detect_ats(target_page.url)
            ats_handler = get_ats_plugin(target_page.url)

        log(f"Routing target page ({target_page.url}) to modular ATS handler '{dest_ats_name}'...")
        
        applicant_info = {
            "first_name": first_name,
            "last_name": last_name,
            "email": email,
            "phone": phone
        }
        
        ats_handler.apply(target_page, applicant_info, abs_resume_path)
        
        # Save session state after application
        save_session_state(context, platform)
        
        # Take a final screenshot for audit trail
        capture_screenshot(page, f"{platform}_apply_complete")
        
        context.close()
        pw.stop()
        
        return {
            "success": True,
            "logs": "\n".join(logs),
            "message": "Form successfully filled."
        }
        
    except Exception as e:
        log(f"Error during Playwright automation: {str(e)}")
        if context:
            try:
                if context.pages:
                    capture_screenshot(context.pages[0], f"{platform}_apply_error")
                context.close()
            except Exception:
                pass
        if pw:
            try:
                pw.stop()
            except Exception:
                pass
        return {
            "success": False,
            "logs": "\n".join(logs),
            "error": str(e)
        }


# ---------------------------------------------------------------------------
# Platform-Specific Apply Handlers
# ---------------------------------------------------------------------------

def _apply_naukri(page, log, resume_path: str):
    """Handles Naukri apply flow with resilient selectors."""
    log("Automating application on Naukri...")
    
    # Use multiple selector strategies for the apply button
    apply_selectors = [
        "#apply-button",
        "button[id*='apply']",
        "button[class*='apply']",
        "button:has-text('Apply')",
        "button:has-text('Apply Now')",
    ]
    
    clicked = False
    for selector in apply_selectors:
        if safe_click(page, selector, timeout=5000, retries=2):
            log(f"Clicked Naukri Apply button: {selector}")
            clicked = True
            break
    
    if clicked:
        # Wait for post-click result
        page.wait_for_timeout(4000)
        
        # Check if a chatbot/questionnaire appeared
        chatbot = page.locator("[class*='chatbot'], [class*='questionnaire'], .apply-form")
        if chatbot.count() > 0:
            log("Post-apply questionnaire detected. Taking screenshot for review.")
            capture_screenshot(page, "naukri_post_apply")
        
        log("Naukri Apply button clicked successfully.")
    else:
        # Check for "Apply on company site" redirect
        redirect_selectors = [
            "button:has-text('Apply on company site')",
            "a:has-text('Apply on company site')",
            "button:has-text('Company Site')",
        ]
        
        for selector in redirect_selectors:
            btn = page.locator(selector)
            if btn.count() > 0 and btn.first.is_visible():
                log("Found company site redirect button. Clicking...")
                try:
                    with page.expect_popup(timeout=10000) as popup_info:
                        btn.first.click()
                    new_page = popup_info.value
                    new_page.wait_for_load_state("domcontentloaded")
                    log(f"Redirected to: {new_page.url}")
                    capture_screenshot(new_page, "naukri_redirect")
                    return
                except Exception as e:
                    log(f"Redirect click failed: {e}")
        
        log("Could not find any Apply button on Naukri page.")
        capture_screenshot(page, "naukri_no_apply_button")


def _apply_linkedin(page, log, first_name: str, last_name: str, email: str, resume_path: str):
    """Handles LinkedIn Easy Apply multi-step flow."""
    log("Automating application on LinkedIn...")
    
    # Check login status
    if "login" in page.url or "authwall" in page.url:
        log("ERROR: Not logged in to LinkedIn. Please verify your session first.")
        capture_screenshot(page, "linkedin_not_logged_in")
        return
    
    # Look for Easy Apply button with multiple selectors
    easy_apply_selectors = [
        "button.jobs-apply-button",
        "button:has-text('Easy Apply')",
        "button[aria-label*='Easy Apply']",
        ".jobs-apply-button--top-card button",
    ]
    
    clicked = False
    for selector in easy_apply_selectors:
        btn = page.locator(selector)
        if btn.count() > 0 and btn.first.is_visible():
            log(f"Found Easy Apply button: {selector}")
            try:
                btn.first.click(timeout=5000)
                clicked = True
                break
            except Exception as e:
                log(f"Click failed for {selector}: {e}")
    
    if not clicked:
        log("LinkedIn Easy Apply button not found. Job may require external application.")
        capture_screenshot(page, "linkedin_no_easy_apply")
        return
    
    # Wait for the Easy Apply modal to open
    try:
        page.wait_for_selector(
            ".jobs-easy-apply-modal, .artdeco-modal, [class*='easy-apply']",
            timeout=8000
        )
        log("Easy Apply modal opened.")
    except Exception:
        log("Easy Apply modal did not appear.")
        capture_screenshot(page, "linkedin_no_modal")
        return
    
    human_delay(page, 500, 1000)
    
    # Multi-step form handler
    for step in range(10):  # LinkedIn Easy Apply can have up to ~8 steps
        log(f"Processing Easy Apply step {step + 1}...")
        
        # Check for file upload fields (resume)
        file_input = page.locator("input[type='file']")
        if file_input.count() > 0:
            try:
                file_input.first.set_input_files(resume_path)
                log("Resume file uploaded.")
                human_delay(page, 1000, 2000)
            except Exception as e:
                log(f"Resume upload failed: {e}")
        
        # Fill empty text fields
        _fill_linkedin_form_fields(page, log, first_name, last_name, email)
        
        # Handle select/dropdown fields
        _handle_linkedin_dropdowns(page, log)
        
        # Handle radio button questions
        _handle_linkedin_radio_buttons(page, log)
        
        # Uncheck "Follow company" if present
        follow_checkbox = page.locator("input[id*='follow-company'], label:has-text('Follow') input[type='checkbox']")
        if follow_checkbox.count() > 0:
            try:
                if follow_checkbox.first.is_checked():
                    follow_checkbox.first.uncheck()
                    log("Unchecked 'Follow company' checkbox.")
            except Exception:
                pass
        
        human_delay(page, 500, 1000)
        
        # Look for navigation buttons
        submit_btn = page.locator(
            "button:has-text('Submit application'), "
            "button:has-text('Submit'), "
            "button[aria-label='Submit application']"
        )
        review_btn = page.locator(
            "button:has-text('Review'), "
            "button[aria-label='Review your application']"
        )
        next_btn = page.locator(
            "button:has-text('Next'), "
            "button[aria-label='Continue to next step']"
        )
        
        if submit_btn.count() > 0 and submit_btn.first.is_enabled():
            log("Clicking Submit button...")
            submit_btn.first.click()
            human_delay(page, 2000, 3000)
            
            # Check for success message
            success = page.locator(
                ".artdeco-inline-feedback--success, "
                "[class*='success'], "
                "h2:has-text('submitted'), "
                ":text('Application submitted')"
            )
            if success.count() > 0:
                log("✅ Easy Apply submitted successfully!")
            else:
                log("Submit clicked. Checking result...")
                capture_screenshot(page, "linkedin_post_submit")
            break
            
        elif review_btn.count() > 0 and review_btn.first.is_enabled():
            log("Clicking Review button...")
            review_btn.first.click()
            human_delay(page, 1000, 2000)
            
        elif next_btn.count() > 0 and next_btn.first.is_enabled():
            log("Clicking Next button...")
            next_btn.first.click()
            human_delay(page, 1000, 2000)
            
        else:
            log(f"No actionable button found on step {step + 1}.")
            capture_screenshot(page, f"linkedin_step{step + 1}_stuck")
            break


def _fill_linkedin_form_fields(page, log, first_name: str, last_name: str, email: str, phone: str = ""):
    """Fills empty text input fields in LinkedIn Easy Apply forms."""
    text_inputs = page.locator(
        ".jobs-easy-apply-modal input[type='text'], "
        ".artdeco-modal input[type='text'], "
        ".jobs-easy-apply-modal input[type='email'], "
        ".jobs-easy-apply-modal input[type='tel']"
    )
    
    for i in range(text_inputs.count()):
        try:
            inp = text_inputs.nth(i)
            if not inp.is_visible():
                continue
                
            current_val = inp.input_value()
            if current_val.strip():
                continue  # Already filled
            
            # Determine what to fill based on label or attributes
            label_text = ""
            label_id = inp.get_attribute("id") or ""
            label_name = inp.get_attribute("name") or ""
            aria_label = inp.get_attribute("aria-label") or ""
            
            # Try to find associated label
            if label_id:
                label_el = page.locator(f"label[for='{label_id}']")
                if label_el.count() > 0:
                    label_text = label_el.first.inner_text().lower()
            
            combined = (label_text + label_id + label_name + aria_label).lower()
            
            if "first" in combined and "name" in combined:
                inp.fill(first_name)
                log(f"Filled first name field.")
            elif "last" in combined and "name" in combined:
                inp.fill(last_name)
                log(f"Filled last name field.")
            elif "email" in combined:
                inp.fill(email)
                log(f"Filled email field.")
            elif ("phone" in combined or "mobile" in combined) and phone:
                inp.fill(phone)
                log(f"Filled phone field.")
            elif "city" in combined or "location" in combined:
                log(f"Location field detected.")
        except Exception:
            pass


def _handle_linkedin_dropdowns(page, log):
    """Handles unfilled select/dropdown fields in LinkedIn Easy Apply."""
    selects = page.locator(
        ".jobs-easy-apply-modal select, .artdeco-modal select"
    )
    
    for i in range(selects.count()):
        try:
            sel = selects.nth(i)
            if not sel.is_visible():
                continue
            
            # If no option is selected, pick the first non-empty option
            current_val = sel.input_value()
            if not current_val:
                options = sel.locator("option")
                for j in range(options.count()):
                    opt_val = options.nth(j).get_attribute("value")
                    if opt_val and opt_val.strip():
                        sel.select_option(value=opt_val)
                        log(f"Selected dropdown option: {opt_val}")
                        break
        except Exception:
            pass


def _handle_linkedin_radio_buttons(page, log):
    """Handles radio button groups in LinkedIn Easy Apply by selecting first option."""
    fieldsets = page.locator(
        ".jobs-easy-apply-modal fieldset, .artdeco-modal fieldset"
    )
    
    for i in range(fieldsets.count()):
        try:
            fieldset = fieldsets.nth(i)
            radios = fieldset.locator("input[type='radio']")
            if radios.count() > 0:
                # Check if any is already selected
                any_checked = False
                for j in range(radios.count()):
                    if radios.nth(j).is_checked():
                        any_checked = True
                        break
                
                if not any_checked and radios.count() > 0:
                    # Select "Yes" if available, otherwise first option
                    yes_label = fieldset.locator("label:has-text('Yes')")
                    if yes_label.count() > 0:
                        yes_label.first.click()
                        log("Selected 'Yes' for a radio question.")
                    else:
                        radios.first.click()
                        log("Selected first radio option.")
        except Exception:
            pass


def _apply_greenhouse(page, log, first_name, last_name, email, resume_path, cover_letter):
    """Handles Greenhouse application form filling."""
    log("Filling Greenhouse application form...")
    
    if page.locator("#first_name").count() > 0:
        page.fill("#first_name", first_name)
        page.fill("#last_name", last_name)
    elif page.locator("#name").count() > 0:
        page.fill("#name", f"{first_name} {last_name}")
        
    if page.locator("#email").count() > 0:
        page.fill("#email", email)
        
    resume_input = page.locator("input[type='file'][accept*='pdf'], input[type='file']#resume_file, input[type='file']")
    if resume_input.count() > 0:
        log("Uploading resume file...")
        resume_input.first.set_input_files(resume_path)
        
    if cover_letter:
        cover_input = page.locator("textarea#cover_letter_text, textarea#cover_letter, textarea[name*='cover']")
        if cover_input.count() > 0:
            log("Filling cover letter text...")
            cover_input.first.fill(cover_letter)
    
    log("Greenhouse form successfully filled. Leaving browser open for Human Review.")
    capture_screenshot(page, "greenhouse_form_filled")
    page.wait_for_timeout(6000)


def _apply_lever(page, log, first_name, last_name, email, resume_path):
    """Handles Lever application form filling."""
    log("Filling Lever application form...")
    
    apply_btn = page.locator("a.postings-btn:has-text('Apply'), a:has-text('Apply for this job')")
    if apply_btn.count() > 0:
        apply_btn.first.click()
        page.wait_for_load_state("domcontentloaded")
    
    resume_input = page.locator("input[type='file']#resume-upload-input, input[type='file']")
    if resume_input.count() > 0:
        log("Uploading resume file...")
        resume_input.first.set_input_files(resume_path)
        human_delay(page, 1500, 2500)
        
    name_input = page.locator("input[name='name']")
    if name_input.count() > 0:
        name_input.fill(f"{first_name} {last_name}")
        
    email_input = page.locator("input[name='email']")
    if email_input.count() > 0:
        email_input.fill(email)
    
    log("Lever form successfully filled. Leaving browser open for Human Review.")
    capture_screenshot(page, "lever_form_filled")
    page.wait_for_timeout(6000)


def _apply_workday_ashby(page, log, ats_platform, first_name, last_name, email, resume_path):
    """Handles Workday and Ashby form filling."""
    log(f"Filling {ats_platform} form (beta automation)...")
    
    inputs = page.locator("input[type='text']")
    for i in range(inputs.count()):
        try:
            name_attr = inputs.nth(i).get_attribute("name") or ""
            id_attr = inputs.nth(i).get_attribute("id") or ""
            combined = (name_attr + id_attr).lower()
            if "first" in combined or "given" in combined:
                inputs.nth(i).fill(first_name)
            elif "last" in combined or "family" in combined:
                inputs.nth(i).fill(last_name)
            elif "email" in combined:
                inputs.nth(i).fill(email)
        except Exception:
            pass
    
    file_inputs = page.locator("input[type='file']")
    if file_inputs.count() > 0:
        log("Uploading resume file...")
        file_inputs.first.set_input_files(resume_path)
    
    log(f"{ats_platform} form filled. Paused for Human review.")
    capture_screenshot(page, f"{ats_platform.lower()}_form_filled")
    page.wait_for_timeout(6000)


def _apply_generic(page, log, first_name, last_name, email):
    """Generic heuristic form filling for unknown ATS platforms."""
    log("Generic job page. Attempting heuristic form filling...")
    
    for label in ["name", "email", "first name", "last name"]:
        input_el = page.locator(
            f"input[placeholder*='{label}' i], "
            f"input[id*='{label}' i], "
            f"input[name*='{label}' i]"
        )
        if input_el.count() > 0:
            val = email if "email" in label else (f"{first_name} {last_name}" if "name" in label else first_name)
            input_el.first.fill(val)
    
    capture_screenshot(page, "generic_form_filled")
    page.wait_for_timeout(6000)
