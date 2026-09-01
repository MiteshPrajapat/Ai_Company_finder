"""
LinkedIn Guest Jobs Source Adapter.
Extracts public listings via LinkedIn's guest job search API endpoints without requiring login.
"""

import urllib.parse
from typing import List, Optional, Dict, Any
import httpx
from bs4 import BeautifulSoup
from scrapers.adapters.base import BaseJobSourceAdapter
from database.models import NormalizedJob
from core.normalizer import JobNormalizer
from utils.logger import get_logger
from utils.text_utils import sanitize_text

logger = get_logger("linkedin_adapter")


class LinkedInAdapter(BaseJobSourceAdapter):
    """Adapter for public LinkedIn job postings."""

    def __init__(self, timeout: Optional[int] = None):
        super().__init__(source_name="linkedin", timeout=timeout)
        self.normalizer = JobNormalizer()

    def search_jobs(
        self,
        profession: str,
        location: str,
        limit: int = 10,
        **kwargs
    ) -> List[NormalizedJob]:
        results: List[NormalizedJob] = []
        clean_prof = "" if profession.lower() == "all" else profession
        keywords = urllib.parse.quote(clean_prof.strip())
        loc_str = urllib.parse.quote(location.strip())

        url = f"https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search?keywords={keywords}&location={loc_str}&start=0"

        try:
            with httpx.Client(timeout=self.timeout, follow_redirects=True, headers=self.headers, verify=False) as client:
                resp = client.get(url)
                if resp.status_code == 200:
                    soup = BeautifulSoup(resp.text, "html.parser")
                    cards = soup.find_all("li") or soup.find_all("div", class_="base-card")

                    for card in cards:
                        if len(results) >= limit:
                            break

                        title_elem = card.find("h3", class_="base-search-card__title") or card.find("h3")
                        comp_elem = card.find("h4", class_="base-search-card__subtitle") or card.find("a", class_="hidden-nested-link") or card.find("h4")
                        loc_elem = card.find("span", class_="job-search-card__location")
                        link_elem = card.find("a", class_="base-card__full-link") or card.find("a", href=True)
                        time_elem = card.find("time")

                        if not title_elem or not comp_elem:
                            continue

                        job_title = sanitize_text(title_elem.get_text() or "")
                        company_name = sanitize_text(comp_elem.get_text() or "")
                        job_loc = sanitize_text(loc_elem.get_text() or "") if loc_elem else location
                        job_url = link_elem["href"] if link_elem and "href" in link_elem.attrs else ""
                        posted_date = time_elem.get("datetime") if time_elem else None

                        if not job_title or not company_name:
                            continue

                        # Clean LinkedIn tracking parameters from URL
                        if "?" in job_url:
                            job_url = job_url.split("?")[0]

                        skills = self.normalizer.extract_skills(f"{job_title} {job_loc}")

                        norm = NormalizedJob(
                            company_name=company_name,
                            job_title=job_title,
                            source="linkedin",
                            source_url=job_url,
                            location=job_loc,
                            remote_type=self.normalizer.normalize_remote_type(job_title, job_loc),
                            employment_type="Full-time",
                            skills=skills,
                            posted_date=posted_date
                        )
                        results.append(norm)

        except Exception as e:
            logger.debug(f"LinkedIn adapter query error: {e}")

        logger.info(f"LinkedIn adapter collected {len(results)} jobs.")
        return results
