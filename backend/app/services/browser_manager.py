"""
BrowserManager — Centralized Playwright browser lifecycle management.

Uses launchPersistentContext() to maintain real browser profiles per-platform,
preserving cookies, localStorage, IndexedDB, ServiceWorkers, and all session state.
"""

import logging
import os
from pathlib import Path
from typing import Optional, Dict, Any
from playwright.sync_api import sync_playwright, BrowserContext, Page, Playwright

from backend.app.config import settings, STORAGE_DIR

logger = logging.getLogger("uvicorn.error")

# Per-platform browser profile directories
BROWSER_PROFILES_DIR = STORAGE_DIR / "browser_profiles"
SCREENSHOTS_DIR = STORAGE_DIR / "screenshots"

# Ensure directories exist
BROWSER_PROFILES_DIR.mkdir(parents=True, exist_ok=True)
SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)

# Default Chromium launch arguments for anti-detection
STEALTH_ARGS = [
    "--disable-blink-features=AutomationControlled",
    "--no-first-run",
    "--no-default-browser-check",
    "--disable-infobars",
    "--disable-extensions",
    "--disable-popup-blocking",
    "--disable-notifications",
    "--disable-dev-shm-usage",
    "--window-size=1280,800",
]

# Default arguments to remove from Chromium's default set
IGNORED_DEFAULT_ARGS = [
    "--enable-automation",
]

# Realistic user agent string
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/126.0.0.0 Safari/537.36"
)


def get_profile_dir(platform: str) -> str:
    """Returns the persistent browser profile directory for a given platform."""
    profile_dir = BROWSER_PROFILES_DIR / platform.lower().strip()
    profile_dir.mkdir(parents=True, exist_ok=True)
    return str(profile_dir)


def get_storage_state_path(platform: str) -> str:
    """Returns the storage state JSON file path for a given platform."""
    return str(BROWSER_PROFILES_DIR / f"{platform.lower().strip()}_storage_state.json")


def launch_persistent_browser(
    platform: str,
    headless: bool = False,
    extra_args: list = None,
) -> tuple:
    """
    Launches a Playwright persistent browser context for the specified platform.
    
    Uses launchPersistentContext() which retains ALL browser state:
    - Cookies (including HttpOnly, SameSite=Strict)
    - localStorage and sessionStorage
    - IndexedDB databases
    - ServiceWorker registrations
    - Cache storage
    - Browser history and autofill
    
    Returns:
        tuple: (playwright_instance, context, page)
        
    IMPORTANT: Caller must close context and stop playwright when done:
        context.close()
        playwright.stop()
    """
    user_data_dir = get_profile_dir(platform)
    
    args = list(STEALTH_ARGS)
    if extra_args:
        args.extend(extra_args)
    
    logger.info(
        f"Launching persistent browser context for '{platform}' "
        f"(profile: {user_data_dir}, headless: {headless})"
    )
    
    pw = sync_playwright().start()
    
    context = pw.chromium.launch_persistent_context(
        user_data_dir=user_data_dir,
        headless=headless,
        args=args,
        ignore_default_args=IGNORED_DEFAULT_ARGS,
        viewport={"width": 1280, "height": 800},
        user_agent=DEFAULT_USER_AGENT,
        locale="en-US",
        timezone_id="Asia/Kolkata",
        accept_downloads=True,
        # Permissions that a real browser would grant
        permissions=["geolocation"],
    )
    
    # Restore additional storage state if available (supplements the profile)
    storage_state_path = get_storage_state_path(platform)
    if os.path.exists(storage_state_path):
        try:
            import json
            with open(storage_state_path, "r", encoding="utf-8") as f:
                state = json.load(f)
            # Add any cookies from saved state that may not be in the profile
            cookies = state.get("cookies", [])
            if cookies:
                context.add_cookies(cookies)
                logger.info(f"Restored {len(cookies)} supplementary cookies from storage state.")
        except Exception as e:
            logger.warning(f"Could not restore storage state for {platform}: {e}")
    
    # Get or create the first page
    if context.pages:
        page = context.pages[0]
    else:
        page = context.new_page()
    
    return pw, context, page


def save_session_state(context: BrowserContext, platform: str) -> dict:
    """
    Saves the current browser context's full session state to disk.
    
    This captures:
    - All cookies (including HttpOnly)
    - localStorage for all origins
    - sessionStorage entries
    
    Returns the storage state dict (also useful for DB storage).
    """
    storage_state_path = get_storage_state_path(platform)
    
    try:
        state = context.storage_state(path=storage_state_path)
        logger.info(
            f"Saved session state for '{platform}': "
            f"{len(state.get('cookies', []))} cookies, "
            f"{len(state.get('origins', []))} origins with localStorage"
        )
        return state
    except Exception as e:
        logger.error(f"Failed to save session state for {platform}: {e}")
        return {"cookies": [], "origins": []}


def capture_screenshot(page: Page, name: str) -> Optional[str]:
    """
    Captures a debug screenshot and saves it to the screenshots directory.
    
    Args:
        page: The Playwright page to screenshot
        name: Descriptive name for the screenshot (e.g., 'linkedin_login_failed')
        
    Returns:
        The file path of the saved screenshot, or None on failure.
    """
    from datetime import datetime
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{name}_{timestamp}.png"
    filepath = str(SCREENSHOTS_DIR / filename)
    
    try:
        page.screenshot(path=filepath, full_page=False)
        logger.info(f"Screenshot saved: {filepath}")
        return filepath
    except Exception as e:
        logger.warning(f"Failed to capture screenshot '{name}': {e}")
        return None


def dismiss_popups(page: Page):
    """
    Attempts to dismiss common popups, cookie banners, and notification dialogs
    that could block form interactions.
    """
    popup_selectors = [
        # Cookie consent banners
        "button:has-text('Accept')",
        "button:has-text('Accept All')",
        "button:has-text('Accept Cookies')",
        "button:has-text('I agree')",
        "button:has-text('Got it')",
        "button:has-text('OK')",
        # Notification permission prompts
        "button:has-text('Not now')",
        "button:has-text('No thanks')",
        "button:has-text('Maybe later')",
        # Generic close buttons
        "button[aria-label='Dismiss']",
        "button[aria-label='Close']",
        "button.artdeco-modal__dismiss",
        # LinkedIn specific
        "button.msg-overlay-bubble-header__control--new-convo-btn",
    ]
    
    for selector in popup_selectors:
        try:
            el = page.locator(selector)
            if el.count() > 0 and el.first.is_visible():
                el.first.click(timeout=2000)
                logger.info(f"Dismissed popup: {selector}")
                page.wait_for_timeout(500)
        except Exception:
            pass


def human_delay(page: Page, min_ms: int = 800, max_ms: int = 2500):
    """
    Adds a randomized human-like delay between actions to avoid bot detection.
    """
    import random
    delay = random.randint(min_ms, max_ms)
    page.wait_for_timeout(delay)


def safe_click(page: Page, selector: str, timeout: int = 10000, retries: int = 3) -> bool:
    """
    Clicks an element with retry logic and popup dismissal.
    
    Returns True if click succeeded, False otherwise.
    """
    for attempt in range(retries):
        try:
            locator = page.locator(selector)
            locator.first.wait_for(state="visible", timeout=timeout)
            locator.first.scroll_into_view_if_needed()
            human_delay(page, 200, 600)
            locator.first.click(timeout=timeout)
            return True
        except Exception as e:
            logger.warning(f"Click attempt {attempt + 1}/{retries} failed for '{selector}': {e}")
            if attempt < retries - 1:
                dismiss_popups(page)
                human_delay(page, 500, 1500)
    
    return False


def scroll_to_bottom(page: Page, pause_ms: int = 1500, max_scrolls: int = 30) -> int:
    """
    Scrolls the page to the bottom incrementally, waiting for new content to load.
    Used for infinite scroll pages like LinkedIn job search.
    
    Returns the number of scroll iterations performed.
    """
    previous_height = 0
    scroll_count = 0
    
    for i in range(max_scrolls):
        # Get current scroll height
        current_height = page.evaluate("document.body.scrollHeight")
        
        if current_height == previous_height:
            # Try one more scroll to be sure
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            page.wait_for_timeout(pause_ms)
            final_height = page.evaluate("document.body.scrollHeight")
            if final_height == current_height:
                logger.info(f"Reached end of page after {scroll_count} scrolls.")
                break
        
        previous_height = current_height
        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        page.wait_for_timeout(pause_ms)
        scroll_count += 1
        
        if scroll_count % 5 == 0:
            logger.info(f"Scrolled {scroll_count} times, page height: {current_height}px")
    
    return scroll_count


def check_if_logged_in(page: Page, platform: str) -> bool:
    """
    Checks if the current page shows a logged-in state for the given platform.
    
    Returns True if authenticated indicators are found, False otherwise.
    """
    try:
        if platform.lower() == "linkedin":
            # Navigate to feed to check login status
            current_url = page.url
            if "linkedin.com" not in current_url:
                page.goto("https://www.linkedin.com/feed/", timeout=15000, wait_until="domcontentloaded")
            
            page.wait_for_timeout(3000)
            final_url = page.url
            
            # If redirected to login page, not authenticated
            if "login" in final_url or "authwall" in final_url or "signup" in final_url:
                return False
            
            # Check for nav elements that only appear when logged in
            nav_indicators = page.locator(
                "#global-nav, .global-nav__me, .feed-identity-module, "
                "img.global-nav__me-photo, .search-global-typeahead"
            )
            if nav_indicators.count() > 0:
                return True
            
            return False
            
        elif platform.lower() == "naukri":
            current_url = page.url
            if "naukri.com" not in current_url:
                page.goto("https://www.naukri.com/mnjuser/homepage", timeout=15000, wait_until="domcontentloaded")
            
            page.wait_for_timeout(3000)
            final_url = page.url
            
            if "nlogin" in final_url:
                return False
            
            user_indicators = page.locator(
                ".nI-gNb-drawer__toggle, .user-name, .dashboard-container, "
                "a[href*='logout'], .nI-gNb-header__wrapper"
            )
            if user_indicators.count() > 0:
                return True
            
            return False
    except Exception as e:
        logger.warning(f"Login check failed for {platform}: {e}")
        return False
    
    return False
