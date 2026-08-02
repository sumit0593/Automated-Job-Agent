# Centralized Scraper Dispatcher and Package Registration

import logging
from typing import List, Dict, Any, Optional

from backend.app.services.browser_manager import (
    launch_persistent_browser,
    save_session_state,
    capture_screenshot,
)

logger = logging.getLogger("uvicorn.error")

# Import base classes and registry utilities
from backend.app.services.scraper.base_portal import BasePortal
from backend.app.services.scraper.base_ats import BaseATS
from backend.app.services.scraper.registry import (
    PORTAL_REGISTRY,
    ATS_REGISTRY,
    register_portal,
    register_ats,
    detect_ats as registry_detect_ats,
    get_portal_plugin,
    get_ats_plugin,
)

# Import all portal plugins to trigger registration decorators
import backend.app.services.scraper.portals.linkedin
import backend.app.services.scraper.portals.naukri
import backend.app.services.scraper.portals.indeed
import backend.app.services.scraper.portals.portals_extra
import backend.app.services.scraper.portals.portals_stubs

# Import all ATS adapters to trigger registration decorators
import backend.app.services.scraper.ats.generic_ats
import backend.app.services.scraper.ats.greenhouse_lever_ashby
import backend.app.services.scraper.ats.workday_smart_icims
import backend.app.services.scraper.ats.enterprise_ats

def detect_ats(url: str) -> str:
    """
    Analyzes job URL to detect the underlying ATS provider.
    Returns capitalised name for compatibility.
    """
    ats_name = registry_detect_ats(url)
    if ats_name == "generic":
        return "Generic"
    return ats_name.capitalize()


def login_to_platform(platform: str, username: str, password: str) -> List[Dict[str, Any]]:
    """
    Delegates login flow to the platform-specific plugin using persistent context.
    """
    pw = None
    context = None
    
    logger.info(f"Scraper: Launching login flow for platform '{platform}'...")
    plugin = get_portal_plugin(platform)
    if not plugin:
        raise ValueError(f"No login plugin registered for platform: {platform}")
        
    try:
        pw, context, page = launch_persistent_browser(
            platform=platform,
            headless=False,
        )
        
        cookies = plugin.login(page, username, password)
        save_session_state(context, platform)
        
        context.close()
        pw.stop()
        return cookies
    except Exception as e:
        logger.error(f"Scraper: Login failed for {platform}: {e}")
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


def discover_jobs_via_platform(
    platform: str,
    cookies: List[Dict[str, Any]],
    keyword: str,
    location: str = "",
    max_jobs: int = 100,
    filters: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    """
    Delegates job search/crawling to the platform-specific plugin.
    """
    pw = None
    context = None
    
    logger.info(f"Scraper: Starting job discovery on '{platform}' for '{keyword}'...")
    plugin = get_portal_plugin(platform)
    if not plugin:
        logger.warning(f"No portal plugin registered for platform: {platform}")
        return []
        
    if filters is None:
        filters = {}
        
    try:
        pw, context, page = launch_persistent_browser(
            platform=platform,
            headless=False,
        )
        
        if cookies:
            try:
                context.add_cookies(cookies)
            except Exception as e:
                logger.warning(f"Scraper: Could not add supplementary cookies: {e}")
                
        results = plugin.search_jobs(page, keyword, location, filters, max_jobs)
        save_session_state(context, platform)
        
        context.close()
        pw.stop()
        return results
    except Exception as e:
        logger.error(f"Scraper: Job discovery failed on {platform}: {e}")
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
        return []


def search_jobs_on_web(query: str, location: str = "") -> List[Dict[str, Any]]:
    """
    Public Job Discovery engine:
    1. If query is a specific company (e.g. 'stripe', 'figma'), queries company Greenhouse API.
    2. If query is a job keyword (e.g. 'GenAI', 'Python', 'Full Stack'), scans active public tech boards
       (Stripe, Figma, Reddit, Scale AI, Cloudflare, etc.) and filters matching role titles & descriptions.
    """
    import json
    import urllib.request
    import re
    from backend.app.services.parser import EXPANDED_SKILLS_DICTIONARY

    normalized_query = query.lower().strip()
    known_boards = [
        "stripe", "figma", "airbnb", "reddit", "lyft", "github", 
        "cloudflare", "coinbase", "datadog", "instacart", "scaleai", 
        "cohere", "door-dash", "discord", "canva", "roblox", "robinhood"
    ]

    target_boards = []
    if normalized_query in known_boards:
        target_boards = [normalized_query]
    else:
        # Check if any known board is inside the query
        matching_single = [b for b in known_boards if b in normalized_query]
        if matching_single:
            target_boards = matching_single
        else:
            # Query keyword across top tech company boards!
            target_boards = known_boards

    logger.info(f"Scraper: Searching public job boards across {len(target_boards)} companies for '{query}'...")
    all_found_jobs = []
    
    for board in target_boards:
        url = f"https://boards-api.greenhouse.io/v1/boards/{board}/jobs?content=true"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=8) as response:
                data = json.loads(response.read().decode("utf-8"))
                jobs = data.get("jobs", [])
                
                for j in jobs:
                    title = j.get("title", "")
                    job_url = j.get("absolute_url", "")
                    loc_name = j.get("location", {}).get("name", "Remote")
                    description_html = j.get("content", "")
                    description = re.sub('<[^<]+?>', '', description_html)
                    
                    title_lower = title.lower()
                    desc_lower = description.lower()
                    loc_lower = loc_name.lower()

                    # Keyword match check
                    keyword_match = (
                        normalized_query in title_lower or 
                        normalized_query in desc_lower or 
                        any(term in title_lower for term in normalized_query.split())
                    )
                    
                    # Location match check (if specified)
                    loc_match = True
                    if location:
                        loc_terms = [t.strip().lower() for t in location.split(",") if t.strip()]
                        loc_match = any(lt in loc_lower or "remote" in loc_lower for lt in loc_terms)

                    if keyword_match and loc_match:
                        extracted_skills = []
                        for sk in EXPANDED_SKILLS_DICTIONARY:
                            if re.search(r"\b" + re.escape(sk) + r"\b", desc_lower, re.IGNORECASE):
                                extracted_skills.append(sk.capitalize())
                        if not extracted_skills:
                            extracted_skills = [query.capitalize()]

                        all_found_jobs.append({
                            "title": title,
                            "company": board.capitalize(),
                            "description": description[:1200],
                            "url": job_url,
                            "location": loc_name,
                            "skills_required": extracted_skills,
                            "experience_required": 2.0
                        })
        except Exception:
            continue

    logger.info(f"Scraper: Found {len(all_found_jobs)} matching job listings for '{query}'.")
    return all_found_jobs


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
    Main entry point for application submission. Detects ATS or delegates to portal plugin,
    preserving full context redirection.
    """
    import os
    abs_resume_path = os.path.abspath(resume_path)
    if not os.path.exists(abs_resume_path):
        return {"success": False, "error": f"Resume file not found at path: {abs_resume_path}"}
        
    logs = []
    def log(msg: str):
        logger.info(msg)
        logs.append(msg)
        
    log(f"Scraper: Starting application for URL: {apply_url}")
    
    ats_platform = registry_detect_ats(apply_url)
    log(f"Scraper: Detected ATS/Portal key: {ats_platform}")
    
    if not platform:
        if ats_platform in ["linkedin", "naukri", "indeed"]:
            platform = ats_platform
        else:
            platform = "generic"
            
    pw = None
    context = None
    
    try:
        pw, context, page = launch_persistent_browser(
            platform=platform,
            headless=not headful,
        )
        
        if cookies:
            try:
                context.add_cookies(cookies)
            except Exception as e:
                log(f"Warning: Could not add supplementary cookies: {e}")
                
        user_profile = {
            "first_name": first_name,
            "last_name": last_name,
            "email": email,
            "phone": phone,
            "cover_letter": cover_letter
        }
        
        portal_plugin = get_portal_plugin(ats_platform)
        if portal_plugin:
            log(f"Scraper: Handing off to Portal Plugin: {ats_platform}")
            res = portal_plugin.apply_job(page, apply_url, abs_resume_path, user_profile)
        else:
            log(f"Scraper: Handing off directly to ATS Adapter: {ats_platform}")
            ats_plugin = get_ats_plugin(apply_url)
            res = ats_plugin.fill_application(page, apply_url, abs_resume_path, user_profile)
            
        save_session_state(context, platform)
        
        context.close()
        pw.stop()
        
        return {
            "success": res.get("success", False),
            "logs": "\n".join(logs) + "\n" + res.get("logs", ""),
            "error": res.get("error")
        }
    except Exception as e:
        log(f"Scraper Error: {e}")
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
