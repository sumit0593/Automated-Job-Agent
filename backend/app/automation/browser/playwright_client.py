import logging
import time
import random
from pathlib import Path
from typing import Optional, List, Dict, Any
from playwright.sync_api import Page, ElementHandle, Frame

from backend.app.config import settings

logger = logging.getLogger("uvicorn.error")

class PlaywrightClient:
    """
    Advanced Playwright Page wrapper implementing selector retries, custom wait strategies,
    shadow DOM traversing, iframe interactions, and pop-up handling.
    """
    def __init__(self, page: Page, platform: str = "generic"):
        self.page = page
        self.platform = platform
        self.screenshots_dir = Path(settings.STORAGE_PATH) / "screenshots"
        self.screenshots_dir.mkdir(parents=True, exist_ok=True)

    def human_delay(self, min_ms: int = 400, max_ms: int = 1500):
        """Adds a human-like delay to avoid bot detection."""
        delay = random.randint(min_ms, max_ms)
        self.page.wait_for_timeout(delay)

    def dismiss_popups(self):
        """Dismisses common overlays, alerts, and consent banners."""
        popup_selectors = [
            "button:has-text('Accept')", "button:has-text('Accept All')", 
            "button:has-text('Accept Cookies')", "button:has-text('I agree')", 
            "button:has-text('Got it')", "button:has-text('OK')", "button:has-text('Not now')", 
            "button:has-text('No thanks')", "button:has-text('Maybe later')", 
            "button[aria-label='Dismiss']", "button[aria-label='Close']", 
            ".artdeco-modal__dismiss", "button.msg-overlay-bubble-header__control--new-convo-btn"
        ]
        for sel in popup_selectors:
            try:
                # Find elements within frames too
                for frame in self.page.frames:
                    elements = frame.locator(sel)
                    if elements.count() > 0 and elements.first.is_visible():
                        elements.first.click(timeout=1000)
                        logger.info(f"PlaywrightClient: Dismissed popup selector '{sel}' in frame '{frame.name or 'main'}'")
                        self.page.wait_for_timeout(300)
            except Exception:
                pass

    def find_element(self, selector: str, timeout: int = 8000) -> Optional[ElementHandle]:
        """
        Locates an element, checking main DOM, iframes, and shadow DOM.
        """
        try:
            # 1. Check main page DOM
            loc = self.page.locator(selector).first
            loc.wait_for(state="attached", timeout=timeout)
            if loc.is_visible():
                return loc.element_handle()
        except Exception:
            pass

        # 2. Check iframes
        for frame in self.page.frames:
            if frame == self.page.main_frame:
                continue
            try:
                loc = frame.locator(selector).first
                if loc.count() > 0 and loc.is_visible():
                    return loc.element_handle()
            except Exception:
                pass

        # 3. Handle Shadow DOM (Playwright's default locator automatically penetrates shadow DOM for CSS selectors,
        # but as a backup we can try checking elements manually)
        try:
            shadow_handle = self.page.evaluate_handle(
                f"() => document.querySelector('{selector}')"
            )
            element = shadow_handle.as_element()
            if element and element.is_visible():
                return element
        except Exception:
            pass

        return None

    def safe_click(self, selector: str, timeout: int = 10000, retries: int = 3) -> bool:
        """Clicks an element with retry logic and dynamic popup dismissal."""
        self.dismiss_popups()
        for attempt in range(retries):
            try:
                element = self.find_element(selector, timeout=timeout)
                if element:
                    element.scroll_into_view_if_needed()
                    self.human_delay(200, 500)
                    element.click(timeout=timeout)
                    return True
            except Exception as e:
                logger.warning(f"PlaywrightClient: Click attempt {attempt + 1}/{retries} failed for '{selector}': {e}")
                self.dismiss_popups()
                self.page.wait_for_timeout(500)
        return False

    def safe_fill(self, selector: str, text: str, timeout: int = 10000, retries: int = 3) -> bool:
        """Fills an input field with typing simulation to emulate human input."""
        for attempt in range(retries):
            try:
                element = self.find_element(selector, timeout=timeout)
                if element:
                    element.scroll_into_view_if_needed()
                    # Clear field first
                    element.fill("")
                    self.human_delay(100, 300)
                    
                    # Emulate typing
                    for char in text:
                        self.page.keyboard.type(char)
                        self.page.wait_for_timeout(random.randint(30, 80))
                    
                    self.page.keyboard.press("Tab")
                    return True
            except Exception as e:
                logger.warning(f"PlaywrightClient: Fill attempt {attempt + 1}/{retries} failed for '{selector}': {e}")
                self.page.wait_for_timeout(500)
        return False

    def safe_upload_file(self, selector: str, file_path: str, timeout: int = 10000) -> bool:
        """Uploads a file safely checking main page and iframes."""
        try:
            # Verify file exists
            if not Path(file_path).exists():
                logger.error(f"PlaywrightClient: File to upload does not exist: {file_path}")
                return False
                
            element = self.find_element(selector, timeout=timeout)
            if element:
                element.set_input_files(file_path)
                logger.info(f"PlaywrightClient: Successfully uploaded {file_path} to '{selector}'")
                return True
        except Exception as e:
            logger.error(f"PlaywrightClient: File upload failed for '{selector}': {e}")
        return False

    def scroll_to_bottom(self, pause_ms: int = 1000, max_scrolls: int = 20) -> int:
        """Scrolls down a page incrementally to trigger lazy loads and pagination elements."""
        previous_height = 0
        scrolls = 0
        for i in range(max_scrolls):
            current_height = self.page.evaluate("document.body.scrollHeight")
            if current_height == previous_height:
                self.page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                self.page.wait_for_timeout(pause_ms)
                if self.page.evaluate("document.body.scrollHeight") == current_height:
                    break
            previous_height = current_height
            self.page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            self.page.wait_for_timeout(pause_ms)
            scrolls += 1
        return scrolls

    def capture_state_screenshot(self, state_name: str) -> Optional[str]:
        """Captures a screenshot for debugging, named after the current state."""
        from datetime import datetime
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{self.platform}_{state_name.lower().strip()}_{timestamp}.png"
        filepath = self.screenshots_dir / filename
        try:
            self.page.screenshot(path=str(filepath), full_page=False)
            logger.info(f"PlaywrightClient: Screenshot saved to {filepath}")
            return str(filepath)
        except Exception as e:
            logger.warning(f"PlaywrightClient: Failed to capture screenshot for state {state_name}: {e}")
            return None

    def wait_for_network_idle(self, timeout: int = 5000):
        """Waits for network to settle."""
        try:
            self.page.wait_for_load_state("networkidle", timeout=timeout)
        except Exception:
            pass

    def check_for_new_tab(self, trigger_action) -> Optional[Page]:
        """Executes a click or action, detects if a new tab opened, and returns it."""
        try:
            with self.page.context.expect_popup(timeout=8000) as popup_info:
                trigger_action()
            new_page = popup_info.value
            new_page.wait_for_load_state("domcontentloaded")
            return new_page
        except Exception as e:
            logger.debug(f"PlaywrightClient: No new tab opened: {e}")
            return None
