import re
import logging
from typing import Optional, Dict, Any, Type

from backend.app.services.scraper.base_portal import BasePortal
from backend.app.services.scraper.base_ats import BaseATS

logger = logging.getLogger("uvicorn.error")

# Global registries
PORTAL_REGISTRY: Dict[str, Type[BasePortal]] = {}
ATS_REGISTRY: Dict[str, Type[BaseATS]] = {}

def register_portal(name: str):
    """Decorator to register a job portal plugin."""
    def decorator(cls: Type[BasePortal]):
        PORTAL_REGISTRY[name.lower().strip()] = cls
        return cls
    return decorator

def register_ats(name: str):
    """Decorator to register an ATS adapter plugin."""
    def decorator(cls: Type[BaseATS]):
        ATS_REGISTRY[name.lower().strip()] = cls
        return cls
    return decorator

def detect_ats(url: str) -> str:
    """
    Analyzes job URL to detect the underlying ATS provider.
    Returns the lowercased registration name of the ATS, or 'generic'.
    """
    url_lower = url.lower()
    
    if "greenhouse.io" in url_lower:
        return "greenhouse"
    elif "lever.co" in url_lower:
        return "lever"
    elif "ashbyhq.com" in url_lower or "ashby" in url_lower:
        return "ashby"
    elif "myworkdayjobs.com" in url_lower or "workday" in url_lower:
        return "workday"
    elif "smartrecruiters.com" in url_lower:
        return "smartrecruiters"
    elif "icims.com" in url_lower:
        return "icims"
    elif "oraclecloud.com" in url_lower or "oraclerecruiting" in url_lower or "oracle" in url_lower:
        return "oracle"
    elif "successfactors" in url_lower or "sfshare" in url_lower:
        return "successfactors"
    elif "taleo.net" in url_lower:
        return "taleo"
    elif "bamboohr.com" in url_lower:
        return "bamboohr"
    elif "naukri.com" in url_lower:
        return "naukri"
    elif "linkedin.com" in url_lower:
        return "linkedin"
        
    return "generic"

def get_portal_plugin(name: str) -> Optional[BasePortal]:
    """Instantiates and returns the portal plugin for the given name."""
    cls = PORTAL_REGISTRY.get(name.lower().strip())
    if cls:
        return cls()
    return None

def get_ats_plugin(url: str) -> BaseATS:
    """Detects ATS from URL and returns the instantiated ATS plugin."""
    ats_name = detect_ats(url)
    cls = ATS_REGISTRY.get(ats_name)
    if not cls:
        cls = ATS_REGISTRY.get("generic")
    return cls()
