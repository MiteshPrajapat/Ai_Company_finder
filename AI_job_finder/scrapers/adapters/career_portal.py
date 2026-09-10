"""
Career Portal Adapter.
Scrapes direct company career portals discovered via Google Maps or direct domain exploration.
"""

from typing import List, Optional, Dict, Any
from scrapers.adapters.base import BaseJobSourceAdapter
from scrapers.careers import CareersScraper
from database.models import NormalizedJob, Company
from core.normalizer import JobNormalizer
from utils.logger import get_logger

logger = get_logger("career_portal_adapter")


class CareerPortalAdapter(BaseJobSourceAdapter):
    """Adapter for official direct company career portals."""

    def __init__(self, careers_scraper: Optional[CareersScraper] = None, timeout: Optional[int] = None):
        super().__init__(source_name="career_portal", timeout=timeout)
        self.scraper = careers_scraper or CareersScraper(timeout=self.timeout)
        self.normalizer = JobNormalizer()

    def search_jobs(
        self,
        profession: str,
        location: str,
        limit: int = 10,
        companies: Optional[List[Company]] = None,
        **kwargs
    ) -> List[NormalizedJob]:
        """
        Extracts jobs from the career portals of discovered companies.
        """
        normalized_jobs: List[NormalizedJob] = []
        if not companies:
            return normalized_jobs

        for comp in companies:
            if len(normalized_jobs) >= limit:
                break
            if not comp.career_url and not comp.website_url:
                continue

            try:
                # Discover career url if needed
                career_url = comp.career_url
                if not career_url and comp.website_url:
                    career_url, _ = self.scraper.discover_career_url(comp.website_url, comp.name)

                if not career_url:
                    continue

                raw_jobs = self.scraper.extract_jobs_from_career_page(
                    career_url=career_url,
                    company_name=comp.name,
                    domain=comp.website_domain
                )

                for rj in raw_jobs:
                    if len(normalized_jobs) >= limit:
                        break
                    
                    skills = self.normalizer.extract_skills(f"{rj.title} {rj.description or ''} {rj.requirements or ''}")
                    norm_job = NormalizedJob(
                        company_name=comp.name,
                        job_title=rj.title,
                        source="career_portal",
                        source_url=rj.job_url or career_url,
                        company_domain=comp.website_domain,
                        company_website=comp.website_url,
                        location=rj.location or comp.city or location,
                        remote_type=self.normalizer.normalize_remote_type(rj.work_mode, rj.location),
                        employment_type=self.normalizer.normalize_employment_type(rj.employment_type),
                        experience=rj.requirements,
                        salary=self.normalizer.normalize_salary(rj.salary),
                        description=rj.description,
                        requirements=rj.requirements,
                        skills=skills,
                        posted_date=rj.posted_date,
                        department=rj.department
                    )
                    normalized_jobs.append(norm_job)

            except Exception as e:
                logger.debug(f"Career portal error for {comp.name}: {e}")

        return normalized_jobs
