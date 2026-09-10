"""
Multi-source job adapters package.
"""

from scrapers.adapters.base import BaseJobSourceAdapter
from scrapers.adapters.career_portal import CareerPortalAdapter
from scrapers.adapters.indeed import IndeedAdapter
from scrapers.adapters.unstop import UnstopAdapter
from scrapers.adapters.linkedin import LinkedInAdapter
from scrapers.adapters.glassdoor import GlassdoorAdapter

__all__ = [
    "BaseJobSourceAdapter",
    "CareerPortalAdapter",
    "IndeedAdapter",
    "UnstopAdapter",
    "LinkedInAdapter",
    "GlassdoorAdapter"
]
