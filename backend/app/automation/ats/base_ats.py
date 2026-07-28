from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
from playwright.sync_api import Page

class BaseATS(ABC):
    """
    Abstract base class for all Applicant Tracking Systems (ATS) adapters.
    """
    @abstractmethod
    def apply(
        self,
        page: Page,
        applicant_info: Dict[str, Any],
        resume_path: str = None
    ) -> bool:
        """Fills and submits application form on the target page."""
        pass
