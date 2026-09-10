"""
Base abstract adapter class for all job search sources.
Enforces standard NormalizedJob outputs, error handling, and rate limiting.
"""

from abc import ABC, abstractmethod
from typing import List, Optional, Dict, Any
from database.models import NormalizedJob
from config.settings import settings
from utils.logger import get_logger

logger = get_logger("source_adapter")


class BaseJobSourceAdapter(ABC):
    """Abstract interface for all multi-source job platforms."""

    def __init__(self, source_name: str, timeout: Optional[int] = None):
        self.source_name = source_name
        self.timeout = timeout or settings.get_config().request_timeout
        self.headers = {
            "User-Agent": settings.get_config().user_agent,
            "Accept-Language": "en-US,en;q=0.9",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
        }

    @abstractmethod
    def search_jobs(
        self,
        profession: str,
        location: str,
        limit: int = 10,
        **kwargs
    ) -> List[NormalizedJob]:
        """
        Executes search for a given profession and location on the platform.
        Returns a list of NormalizedJob instances.
        """
        pass
