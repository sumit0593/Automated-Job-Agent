import logging
import re
from typing import Dict, Any, Optional
from playwright.sync_api import Page
from backend.app.automation.browser.playwright_client import PlaywrightClient

logger = logging.getLogger("uvicorn.error")

def verify_application_success(page: Page, platform: str) -> Dict[str, Any]:
    """
    Validates if the current page contains confirmation of successful submission.
    """
    client = PlaywrightClient(page, platform)
    page_text = page.inner_text("body").lower()
    
    # 1. Look for common success keywords
    success_indicators = [
        "thank you for applying", "application submitted", "received your application",
        "successfully submitted", "application received", "thanks for your application",
        "your application was sent", "application is complete", "confirm your application",
        "application has been sent", "check your email"
    ]
    
    success = False
    matched_indicator = ""
    for ind in success_indicators:
        if ind in page_text:
            success = True
            matched_indicator = ind
            break
            
    # 2. Heuristic check: check if redirected to a path indicating submission success
    url = page.url.lower()
    if any(x in url for x in ["thank-you", "thankyou", "submitted", "success", "confirmation"]):
        success = True
        matched_indicator = "URL keyword redirect"

    # 3. Locate Application Reference ID
    app_id = None
    id_patterns = [
        r"(?:application id|reference number|confirmation number|ref id|app id)[:\s#]+([a-z0-9\-]+)",
        r"(?:ref[:\s#]+|#\s*)([0-9]{5,})"
    ]
    for pattern in id_patterns:
        match = re.search(pattern, page_text, re.IGNORECASE)
        if match:
            app_id = match.group(1).strip()
            break

    # Save screenshot of confirmation page as proof
    screenshot_path = client.capture_state_screenshot("submission_proof")

    return {
        "success": success,
        "matched_indicator": matched_indicator,
        "application_id": app_id,
        "screenshot_path": screenshot_path
    }
