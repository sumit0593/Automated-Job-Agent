from abc import ABC, abstractmethod
from typing import List, Dict, Any
from playwright.sync_api import Page

class BasePortal(ABC):
    """
    Abstract base class for all job board portals.
    """
    @abstractmethod
    def search_jobs(
        self,
        page: Page,
        keyword: str,
        location: str,
        filters: Dict[str, Any],
        max_jobs: int
    ) -> List[Dict[str, Any]]:
        """
        Search for jobs on this portal and return a list of standard job dicts:
        {
            "title": str,
            "company": str,
            "description": str,
            "url": str,
            "location": str,
            "skills_required": List[str],
            "experience_required": float
        }
        """
        pass

    @abstractmethod
    def login(self, page: Page, username: str, password: str) -> List[Dict[str, Any]]:
        """
        Execute login flow on this portal and return the list of session cookies.
        """
        pass

    @abstractmethod
    def apply_job(
        self,
        page: Page,
        apply_url: str,
        resume_path: str,
        user_profile: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Apply to a job listing. Should handle internal apply flow or detect external ATS redirect
        and delegate to the appropriate ATS adapter.
        
        Returns:
            Dict: {
                "success": bool,
                "logs": str,
                "error": Optional[str],
                "redirected_url": Optional[str]
            }
        """
        pass
