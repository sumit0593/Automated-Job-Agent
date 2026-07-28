import logging
from typing import Dict, Type
from backend.app.automation.ats.base_ats import BaseATS

from backend.app.automation.ats.handlers.greenhouse_handler import GreenhouseHandler
from backend.app.automation.ats.handlers.lever_handler import LeverHandler
from backend.app.automation.ats.handlers.workday_handler import WorkdayHandler
from backend.app.automation.ats.handlers.darwin_handler import DarwinHandler
from backend.app.automation.ats.handlers.zoho_handler import ZohoRecruitHandler
from backend.app.automation.ats.handlers.oracle_handler import OracleHandler
from backend.app.automation.ats.handlers.successfactors_handler import SuccessFactorsHandler
from backend.app.automation.ats.handlers.smartrecruiters_handler import SmartRecruitersHandler
from backend.app.automation.ats.handlers.ashby_handler import AshbyHandler
from backend.app.automation.ats.handlers.custom_ats_handler import CustomATSHandler

from backend.app.automation.ats.handlers.recruiter_chatbot_handler import RecruiterChatbotHandler

logger = logging.getLogger("uvicorn.error")

ATS_HANDLERS_REGISTRY: Dict[str, Type[BaseATS]] = {
    "greenhouse": GreenhouseHandler,
    "lever": LeverHandler,
    "workday": WorkdayHandler,
    "darwinbox": DarwinHandler,
    "zohorecruit": ZohoRecruitHandler,
    "oracle": OracleHandler,
    "successfactors": SuccessFactorsHandler,
    "smartrecruiters": SmartRecruitersHandler,
    "ashby": AshbyHandler,
    "chatbot": RecruiterChatbotHandler,
    "recruiter_chatbot": RecruiterChatbotHandler,
    "paradox": RecruiterChatbotHandler,
    "mya": RecruiterChatbotHandler,
    "landbot": RecruiterChatbotHandler,
    "custom": CustomATSHandler,
    "generic": CustomATSHandler,
    "unknown": CustomATSHandler
}

def detect_ats(url: str) -> str:
    """Classifies application URL into destination ATS platform."""
    if not url:
        return "custom"
        
    url_lower = url.lower()
    
    if "greenhouse.io" in url_lower:
        return "greenhouse"
    elif "lever.co" in url_lower:
        return "lever"
    elif "myworkdayjobs.com" in url_lower or "workday" in url_lower:
        return "workday"
    elif "darwinbox" in url_lower:
        return "darwinbox"
    elif "zohorecruit" in url_lower or "zoho.com/recruit" in url_lower:
        return "zohorecruit"
    elif "oraclecloud.com" in url_lower or "oraclerecruiting" in url_lower or "taleo.net" in url_lower:
        return "oracle"
    elif "successfactors" in url_lower or "sfshare" in url_lower:
        return "successfactors"
    elif "smartrecruiters.com" in url_lower:
        return "smartrecruiters"
    elif "ashbyhq.com" in url_lower or "ashby" in url_lower:
        return "ashby"
    elif any(cb in url_lower for cb in ["paradox", "olivia", "mya", "landbot", "chatbot", "chatspot"]):
        return "chatbot"
        
    return "custom"

def get_ats_plugin(url: str) -> BaseATS:
    """Returns the dedicated modular ATS handler instance for the given URL."""
    name = detect_ats(url)
    handler_cls = ATS_HANDLERS_REGISTRY.get(name, CustomATSHandler)
    logger.info(f"ATSRouter: Selected {handler_cls.__name__} for URL platform '{name}' ({url})")
    return handler_cls()
