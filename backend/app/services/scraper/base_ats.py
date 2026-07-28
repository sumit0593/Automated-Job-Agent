from abc import ABC, abstractmethod
from typing import Dict, Any
from playwright.sync_api import Page

class BaseATS(ABC):
    """
    Abstract base class for all Applicant Tracking Systems (ATS) adapters.
    """
    @abstractmethod
    def fill_application(
        self,
        page: Page,
        apply_url: str,
        resume_path: str,
        user_profile: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Navigate to the application URL and fill out all fields.
        Does NOT click final submit unless validation passes.
        
        Returns:
            Dict: {
                "success": bool,
                "logs": str,
                "error": Optional[str]
            }
        """
        pass
