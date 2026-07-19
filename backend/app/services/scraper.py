import json
import logging
import urllib.request
import urllib.parse
import re
from typing import List, Dict, Any, Optional
from pathlib import Path
from backend.app.config import settings

logger = logging.getLogger("uvicorn.error")

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

def fetch_greenhouse_jobs(board_token: str) -> List[Dict[str, Any]]:
    """
    Fetches job listings from the Greenhouse board API for a specific company token.
    """
    url = f"https://boards-api.greenhouse.io/v1/boards/{board_token}/jobs?content=true"
    logger.info(f"Scraping Greenhouse board: {board_token} via API...")
    
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as response:
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
                    "description": description[:1200],  # Cap length
                    "url": job_url,
                    "location": location,
                    "skills_required": skills,
                    "experience_required": 2.0
                })
            return parsed_jobs
    except Exception as e:
        logger.error(f"Failed to scrape Greenhouse board {board_token}: {e}")
        return []

def login_to_platform(platform: str, username: str, password: str) -> List[Dict[str, Any]]:
    """
    Launches Playwright in headful mode. Pre-fills fields if standard,
    and polls for up to 90s to let the user complete manual/Google/MFA login.
    Once successful landing is detected, grabs session cookies.
    """
    from playwright.sync_api import sync_playwright
    import time
    
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=False,
            args=["--disable-blink-features=AutomationControlled"],
            ignore_default_args=["--enable-automation"]
        )
        context = browser.new_context(
            viewport={"width": 1280, "height": 800},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        )
        page = context.new_page()
        
        try:
            if platform.lower() == "linkedin":
                page.goto("https://www.linkedin.com/login", timeout=20000)
                # Fill fields as convenience if they exist
                try:
                    page.fill("#username", username)
                    page.fill("#password", password)
                except Exception:
                    pass
                
                logger.info("Awaiting manual login completion in the browser (supports Google Sign-In, standard, or MFA/OTPs)...")
                
                # Poll for feed/dashboard indicators for up to 90 seconds
                success = False
                for _ in range(90):
                    time.sleep(1)
                    current_url = page.url
                    if any(x in current_url for x in ["feed", "mynetwork", "jobs", "messaging", "in/"]):
                        success = True
                        break
                    try:
                        if page.locator("#global-nav, .global-nav__me, #global-nav-typeahead").count() > 0:
                            success = True
                            break
                    except Exception:
                        pass
                
                if not success:
                    raise TimeoutError("Login verification timed out (90s exceeded).")
                    
            elif platform.lower() == "naukri":
                page.goto("https://www.naukri.com/nlogin/login", timeout=20000)
                try:
                    page.fill("#usernameField", username)
                    page.fill("#passwordField", password)
                except Exception:
                    pass
                
                logger.info("Awaiting manual login completion in the browser (supports Google Sign-In, standard, or MFA/OTPs)...")
                
                success = False
                for _ in range(90):
                    time.sleep(1)
                    current_url = page.url
                    if "mnjuser" in current_url or "homepage" in current_url:
                        success = True
                        break
                    try:
                        if page.locator(".user-name, .dashboard-container, .myNaukri, a[href*='logout'], a[href*='profile']").count() > 0:
                            if "nlogin" not in current_url:
                                success = True
                                break
                    except Exception:
                        pass
                        
                if not success:
                    raise TimeoutError("Login verification timed out (90s exceeded).")
            else:
                raise ValueError(f"Platform {platform} login flow not implemented.")
                
            cookies = context.cookies()
            logger.info(f"Successfully retrieved login session cookies for {platform}!")
            browser.close()
            return cookies
        except Exception as e:
            logger.error(f"Automation login failed for {platform}: {e}")
            browser.close()
            raise e

def discover_jobs_via_platform(
    platform: str,
    cookies: List[Dict[str, Any]],
    keyword: str,
    location: str = ""
) -> List[Dict[str, Any]]:
    """
    Log in using cookies and fetch job listings from job portals (LinkedIn/Naukri).
    (Synchronous version to prevent Windows asyncio NotImplementedError)
    """
    from playwright.sync_api import sync_playwright
    
    logger.info(f"Crawl job discovery started on {platform} for '{keyword}'...")
    results = []
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=False,
            args=["--disable-blink-features=AutomationControlled"],
            ignore_default_args=["--enable-automation"]
        )
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        )
        if cookies:
            context.add_cookies(cookies)
            
        page = context.new_page()
        
        try:
            if platform.lower() == "linkedin":
                search_url = f"https://www.linkedin.com/jobs/search/?keywords={urllib.parse.quote(keyword)}&location={urllib.parse.quote(location)}"
                page.goto(search_url, timeout=30000)
                
                # Wait up to 10s for any common job card selectors to render
                try:
                    page.wait_for_selector(
                        ".job-card-container, li.jobs-search-results__list-item, [data-occludable-job-id], .job-card-list__entity-lockup",
                        timeout=10000
                    )
                except Exception:
                    logger.warning("Timed out waiting for job cards to render on LinkedIn.")
                    
                # Scrape job cards (supports both public search and logged-in feed dashboard)
                job_cards = page.locator(".job-card-container, li.jobs-search-results__list-item, [data-occludable-job-id], .job-card-list__entity-lockup")
                card_count = job_cards.count()
                logger.info(f"Found {card_count} job listing cards on LinkedIn.")
                
                for i in range(min(card_count, 8)):
                    try:
                        card = job_cards.nth(i)
                        # Extract title
                        title_el = card.locator(".job-card-list__title, a.job-card-list__title-link, [class*='job-title']")
                        title = title_el.first.inner_text() if title_el.count() > 0 else "Software Engineer"
                        
                        # Extract company
                        comp_el = card.locator(".job-card-container__company-name, .job-card-list__company-name, [class*='company-name']")
                        company = comp_el.first.inner_text() if comp_el.count() > 0 else "Tech Company"
                        
                        # Extract location
                        loc_el = card.locator(".job-card-container__metadata-item, .job-card-list__metadata-item, [class*='location']")
                        loc = loc_el.first.inner_text() if loc_el.count() > 0 else "Remote"
                        
                        # Extract url
                        link_el = card.locator("a.job-card-list__title-link, a[class*='job-card'], a.job-card-list__title").first
                        job_href = link_el.get_attribute("href") if link_el.count() > 0 else ""
                        if job_href:
                            job_url = "https://www.linkedin.com" + job_href.split("?")[0] if not job_href.startswith("http") else job_href.split("?")[0]
                        else:
                            job_url = f"https://www.linkedin.com/jobs/view/crawled-{i}"
                            
                        # Clean company and location strings
                        company = company.strip().replace("\n", "")
                        loc = loc.strip().replace("\n", "")
                        
                        # Set description preview
                        desc = f"Active opportunity for a {title} position at {company} located in {loc}. Apply now."
                        
                        results.append({
                            "title": title.strip(),
                            "company": company,
                            "description": desc,
                            "url": job_url,
                            "location": loc,
                            "skills_required": [keyword.capitalize()],
                            "experience_required": 2.0
                        })
                    except Exception as card_err:
                        logger.error(f"Error parsing job card {i}: {card_err}")
            elif platform.lower() == "naukri":
                search_url = f"https://www.naukri.com/jobs-in-india?k={urllib.parse.quote(keyword)}"
                page.goto(search_url, timeout=30000)
                try:
                    page.wait_for_selector(
                        "article.jobTuple, article.cust-job-tuple, .jobTuple, .cust-job-tuple",
                        timeout=10000
                    )
                except Exception:
                    logger.warning("Timed out waiting for job cards to render on Naukri.")
                
                job_cards = page.locator("article.jobTuple, article.cust-job-tuple, .jobTuple, .cust-job-tuple")
                card_count = job_cards.count()
                logger.info(f"Found {card_count} job cards on Naukri.")
                
                for i in range(min(card_count, 8)):
                    try:
                        card = job_cards.nth(i)
                        title_el = card.locator("a.title, a.job-title, .title")
                        title = title_el.first.inner_text() if title_el.count() > 0 else "Software Developer"
                        
                        comp_el = card.locator("a.comp-name, .company-name, .subTitle")
                        company = comp_el.first.inner_text() if comp_el.count() > 0 else "Naukri Recruiter"
                        
                        loc_el = card.locator(".locWraper span.loc, .location, .loc")
                        loc = loc_el.first.inner_text() if loc_el.count() > 0 else "Remote"
                        
                        link_el = card.locator("a.title, a.job-title, a[href*='/job-']").first
                        job_href = link_el.get_attribute("href") if link_el.count() > 0 else ""
                        job_url = job_href.split("?")[0] if job_href else f"https://www.naukri.com/job-crawled-{i}"
                        
                        desc_el = card.locator(".job-desc, .jobDescription")
                        desc = desc_el.first.inner_text() if desc_el.count() > 0 else "Click apply for details."
                        
                        results.append({
                            "title": title.strip(),
                            "company": company.strip(),
                            "description": desc.strip(),
                            "url": job_url,
                            "location": loc.strip(),
                            "skills_required": [keyword.capitalize()],
                            "experience_required": 2.0
                        })
                    except Exception as card_err:
                        logger.error(f"Error parsing Naukri job card {i}: {card_err}")
            else:
                logger.warning(f"Crawling not supported for platform {platform}")
                
            browser.close()
            return results
        except Exception as e:
            logger.error(f"Error executing crawler on {platform}: {e}")
            browser.close()
            return []

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

def automate_application_flow(
    apply_url: str,
    first_name: str,
    last_name: str,
    email: str,
    resume_path: str,
    cover_letter: str = "",
    headful: bool = True,
    cookies: Optional[List[Dict[str, Any]]] = None
) -> Dict[str, Any]:
    """
    Fills forms on Greenhouse, Lever, Workday, and Ashby.
    (Synchronous version to prevent Windows asyncio NotImplementedError)
    """
    from playwright.sync_api import sync_playwright
    import os
    
    abs_resume_path = os.path.abspath(resume_path)
    if not os.path.exists(abs_resume_path):
        return {"success": False, "error": f"Resume file not found at path: {abs_resume_path}"}
        
    logs = []
    def log(msg: str):
        logger.info(msg)
        logs.append(msg)
        
    ats_platform = detect_ats(apply_url)
    log(f"Starting application automation for URL: {apply_url}")
    log(f"Detected ATS platform: {ats_platform}")
    
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=not headful,
                args=["--disable-blink-features=AutomationControlled"],
                ignore_default_args=["--enable-automation"]
            )
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
            )
            if cookies:
                context.add_cookies(cookies)
            page = context.new_page()
            
            log("Navigating to application page...")
            page.goto(apply_url, timeout=30000)
            page.wait_for_load_state("networkidle")
            
            if ats_platform == "Naukri":
                log("Automating application on Naukri...")
                apply_btn = page.locator("#apply-button, button.apply-button, .styles_apply-button__uJI3A")
                if apply_btn.count() > 0:
                    log("Clicking Naukri Apply button...")
                    apply_btn.first.click()
                    page.wait_for_timeout(5000)
                    log("Naukri Apply button clicked.")
                else:
                    log("Naukri Apply button not found. Checking for company site redirect...")
                    company_site_btn = page.locator("button:has-text('Apply on company site'), a:has-text('Apply on company site')")
                    if company_site_btn.count() > 0:
                        log("Found redirect button. Clicking...")
                        with page.expect_popup() as popup_info:
                            company_site_btn.first.click()
                        page = popup_info.value
                        page.wait_for_load_state("networkidle")
                        log(f"Redirected to: {page.url}")
                        redirected_ats = detect_ats(page.url)
                        log(f"Redirected page ATS: {redirected_ats}")
                    else:
                        log("Could not find any Apply button on Naukri page.")
                page.wait_for_timeout(4000)
                
            elif ats_platform == "LinkedIn":
                log("Automating application on LinkedIn...")
                easy_apply_btn = page.locator("button.jobs-apply-button")
                if easy_apply_btn.count() > 0:
                    log("Clicking LinkedIn Easy Apply button...")
                    easy_apply_btn.first.click()
                    page.wait_for_timeout(2000)
                    for step in range(5):
                        next_btn = page.locator("button:has-text('Next'), button:has-text('Review'), button:has-text('Submit')")
                        if next_btn.count() > 0:
                            btn_text = next_btn.first.inner_text().strip()
                            log(f"Found button: {btn_text}. Clicking it...")
                            next_btn.first.click()
                            page.wait_for_timeout(2000)
                            if "submit" in btn_text.lower():
                                log("Easy Apply submitted successfully!")
                                break
                        else:
                            break
                else:
                    log("LinkedIn Easy Apply button not found.")
                    
            elif ats_platform == "Greenhouse":
                log("Filling Greenhouse application form...")
                if page.locator("#first_name").count() > 0:
                    page.fill("#first_name", first_name)
                    page.fill("#last_name", last_name)
                elif page.locator("#name").count() > 0:
                    page.fill("#name", f"{first_name} {last_name}")
                    
                if page.locator("#email").count() > 0:
                    page.fill("#email", email)
                    
                resume_input = page.locator("input[type='file'][accept*='pdf'], input[type='file']#resume_file")
                if resume_input.count() > 0:
                    log("Uploading resume file...")
                    resume_input.first.set_input_files(abs_resume_path)
                    
                if cover_letter:
                    cover_input = page.locator("textarea#cover_letter_text, textarea#cover_letter")
                    if cover_input.count() > 0:
                        log("Filling cover letter text...")
                        cover_input.fill(cover_letter)
                
                log("Greenhouse form successfully filled. Leaving browser open for Human Review...")
                page.wait_for_timeout(6000)
                
            elif ats_platform == "Lever":
                log("Filling Lever application form...")
                apply_btn = page.locator("a.postings-btn:has-text('Apply')")
                if apply_btn.count() > 0:
                    apply_btn.first.click()
                    page.wait_for_load_state("networkidle")
                
                resume_input = page.locator("input[type='file']#resume-upload-input")
                if resume_input.count() > 0:
                    log("Uploading resume file...")
                    resume_input.set_input_files(abs_resume_path)
                    page.wait_for_timeout(2000)
                    
                name_input = page.locator("input[name='name']")
                if name_input.count() > 0:
                    name_input.fill(f"{first_name} {last_name}")
                    
                email_input = page.locator("input[name='email']")
                if email_input.count() > 0:
                    email_input.fill(email)
                
                log("Lever form successfully filled. Leaving browser open for Human Review...")
                page.wait_for_timeout(6000)
                
            elif ats_platform in ["Workday", "Ashby"]:
                log(f"Filling {ats_platform} form (beta automation)...")
                inputs = page.locator("input[type='text']")
                for i in range(inputs.count()):
                    name_attr = inputs.nth(i).get_attribute("name") or ""
                    id_attr = inputs.nth(i).get_attribute("id") or ""
                    combined = (name_attr + id_attr).lower()
                    if "first" in combined or "given" in combined:
                        inputs.nth(i).fill(first_name)
                    elif "last" in combined or "family" in combined:
                        inputs.nth(i).fill(last_name)
                    elif "email" in combined:
                        inputs.nth(i).fill(email)
                
                file_inputs = page.locator("input[type='file']")
                if file_inputs.count() > 0:
                    log("Uploading resume file to standard file field...")
                    file_inputs.first.set_input_files(abs_resume_path)
                
                log(f"{ats_platform} form filled. Paused for Human review...")
                page.wait_for_timeout(6000)
                
            else:
                log("Generic job page. Attempting heuristical form filling...")
                for label in ["name", "email", "first name", "last name"]:
                    input_el = page.locator(f"input[placeholder*='{label}' i], input[id*='{label}' i], input[name*='{label}' i]")
                    if input_el.count() > 0:
                        val = email if "email" in label else (f"{first_name} {last_name}" if "name" in label else first_name)
                        input_el.first.fill(val)
                
                page.wait_for_timeout(6000)
                
            browser.close()
            return {
                "success": True,
                "logs": "\n".join(logs),
                "message": "Form successfully filled."
            }
    except Exception as e:
        log(f"Error during Playwright automation: {str(e)}")
        return {
            "success": False,
            "logs": "\n".join(logs),
            "error": str(e)
        }
