import logging
from typing import Dict, Any
from playwright.sync_api import Page

logger = logging.getLogger("uvicorn.error")

VALID_APPLICATION_TYPES = [
    "Easy Apply",
    "External Website",
    "Recruiter Chatbot",
    "Assessment/Test",
    "OTP/Login",
    "Resume Required",
    "Unknown"
]

def classify_application_type(page: Page, url: str) -> Dict[str, Any]:
    """
    Analyzes the target page and DOM structure before clicking Apply to determine the application channel type:
    - Easy Apply
    - External Website
    - Recruiter Chatbot
    - Assessment/Test
    - OTP/Login
    - Resume Required
    - Unknown
    """
    url_lower = (url or "").lower()
    
    try:
        page_url = (page.url or url_lower).lower()
        body_text = ""
        try:
            body_text = page.inner_text("body", timeout=3000).lower()[:5000]
        except Exception:
            pass

        # 1. Check for OTP / Login required
        # Password inputs, OTP fields, or explicit sign-in requirement overlays
        if page.locator("input[type='password']").count() > 0 or \
           page.locator("input[name*='otp' i], input[id*='otp' i], input[placeholder*='otp' i]").count() > 0 or \
           ("sign in to apply" in body_text or "please log in" in body_text or "enter verification code" in body_text):
            return {
                "type": "OTP/Login",
                "details": "Page requires authentication, login password, or OTP verification code before proceeding.",
                "confidence": 0.95
            }

        # 2. Check for Recruiter Chatbot
        # Chat container elements, Paradox/Olivia/Mya/Landbot chat widgets
        if page.locator(".chat-container, .chatbot, [class*='chatbot' i], [id*='chatbot' i], [data-testid*='chat' i]").count() > 0 or \
           page.locator("iframe[src*='paradox' i], iframe[src*='mya' i], iframe[src*='landbot' i]").count() > 0 or \
           ("virtual recruiter" in body_text or "chat with us to apply" in body_text or "recruiting assistant" in body_text):
            return {
                "type": "Recruiter Chatbot",
                "details": "Detected conversational recruiter chatbot interface.",
                "confidence": 0.90
            }

        # 3. Check for Assessment / Test
        # HackerRank, CodeSignal, TestGorilla, screening quiz, online test instructions
        if page.locator("a[href*='hackerrank' i], a[href*='codesignal' i], a[href*='testgorilla' i]").count() > 0 or \
           ("take test" in body_text or "assessment required" in body_text or "screening quiz" in body_text or "start assessment" in body_text):
            return {
                "type": "Assessment/Test",
                "details": "Application requires completing a pre-screening assessment or technical test.",
                "confidence": 0.90
            }

        # 4. Check for Easy Apply
        # In-portal modal application (LinkedIn Easy Apply, Naukri Easy Apply, embedded modal form)
        if page.locator("button:has-text('Easy Apply'), a:has-text('Easy Apply'), .jobs-easy-apply-modal, .artdeco-modal, button.jobs-apply-button").count() > 0 or \
           ("easy apply" in body_text and ("linkedin.com" in page_url or "naukri.com" in page_url)):
            return {
                "type": "Easy Apply",
                "details": "In-portal Easy Apply modal application.",
                "confidence": 0.95
            }

        # 5. Check for External Website
        # Application points to external ATS or company career site outside portal
        ats_domains = [
            "greenhouse.io", "lever.co", "myworkdayjobs.com", "ashbyhq.com",
            "icims.com", "smartrecruiters.com", "oraclecloud.com", "taleo.net",
            "bamboohr.com", "jobvite.com", "jazzhr.com"
        ]
        is_known_ats = any(domain in page_url for domain in ats_domains) or any(domain in url_lower for domain in ats_domains)
        
        has_external_apply_btn = page.locator(
            "a:has-text('Apply on company website'), "
            "a:has-text('Apply Externally'), "
            "button:has-text('Apply on company website')"
        ).count() > 0
        
        if is_known_ats or has_external_apply_btn:
            return {
                "type": "External Website",
                "details": "Application redirects to an external company website or ATS portal.",
                "confidence": 0.90
            }

        # 6. Check for Resume Required
        # Form on current page contains direct file upload input for resume
        if page.locator("input[type='file']").count() > 0 or \
           ("upload resume" in body_text or "attach cv" in body_text or "upload cv" in body_text):
            return {
                "type": "Resume Required",
                "details": "Direct job page featuring a resume upload form.",
                "confidence": 0.85
            }

        # 7. Fallback: URL heuristic if page loading was minimal
        if any(domain in url_lower for domain in ats_domains):
            return {
                "type": "External Website",
                "details": "URL belongs to an external ATS provider domain.",
                "confidence": 0.80
            }

        if "linkedin.com" in url_lower or "naukri.com" in url_lower:
            return {
                "type": "Easy Apply",
                "details": "Job post hosted on a job portal.",
                "confidence": 0.70
            }

        return {
            "type": "Unknown",
            "details": "Could not determine application type with high confidence.",
            "confidence": 0.30
        }

    except Exception as e:
        logger.error(f"Error classifying application type for {url}: {e}")
        return {
            "type": "Unknown",
            "details": f"Classification error: {e}",
            "confidence": 0.0
        }
