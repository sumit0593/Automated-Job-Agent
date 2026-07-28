from abc import ABC, abstractmethod
from typing import List, Dict, Any
from playwright.sync_api import Page

class BasePortal(ABC):
    """
    Abstract base class for all job board portal plugins.
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
        Search for jobs on this portal. Returns a list of standard job dicts.
        """
        pass

    @abstractmethod
    def login(self, page: Page, username: str, password: str) -> List[Dict[str, Any]]:
        """
        Execute login flow on this portal and return cookies.
        """
        pass

    @abstractmethod
    def apply_job(
        self,
        page: Page,
        apply_url: str,
        resume_path: str,
        user_profile: Dict[str, Any],
        candidate_profile: Dict[str, Any],
        resume_id: int
    ) -> Dict[str, Any]:
        """
        Apply to a job listing. Should handle internal apply or handoff to ATS.
        """
        pass
