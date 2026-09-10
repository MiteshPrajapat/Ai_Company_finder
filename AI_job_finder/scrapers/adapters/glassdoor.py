"""
Glassdoor Job Source Adapter.
Extracts public listings from Glassdoor search endpoints with fallback discovery.
"""

import urllib.parse
from typing import List, Optional, Dict, Any
import httpx
from bs4 import BeautifulSoup
from scrapers.adapters.base import BaseJobSourceAdapter
from database.models import NormalizedJob
from core.normalizer import JobNormalizer
from browser.duckduckgo import DuckDuckGoSearcher
from utils.logger import get_logger
from utils.text_utils import sanitize_text

logger = get_logger("glassdoor_adapter")


class GlassdoorAdapter(BaseJobSourceAdapter):
    """Adapter for Glassdoor public job postings."""

    def __init__(self, timeout: Optional[int] = None):
        super().__init__(source_name="glassdoor", timeout=timeout)
        self.normalizer = JobNormalizer()
        self.ddg = DuckDuckGoSearcher()

    def search_jobs(
        self,
        profession: str,
        location: str,
        limit: int = 10,
        **kwargs
    ) -> List[NormalizedJob]:
        results: List[NormalizedJob] = []
        clean_prof = "" if profession.lower() == "all" else profession
        query_str = f"site:glassdoor.com/Job {clean_prof} jobs in {location}".strip()

        try:
            # Discover public glassdoor links
            links = self.ddg.search(query_str, max_results=limit * 2)
            for link in links:
                if len(results) >= limit:
                    break
                if "glassdoor.com" not in link or "/Job/" not in link and "/job-listing/" not in link:
                    continue

                # Fetch page content or parse title from URL / search
                try:
                    with httpx.Client(timeout=8, follow_redirects=True, headers=self.headers, verify=False) as client:
                        resp = client.get(link)
                        if resp.status_code == 200:
                            soup = BeautifulSoup(resp.text, "html.parser")
                            title_elem = soup.find("h1") or soup.find("title")
                            raw_title = sanitize_text(title_elem.get_text() if title_elem else "")

                            # Extract company and job title from standard Glassdoor title format:
                            # "Job Title at Company Name" or "Company Name hiring Job Title in Location"
                            company_name = ""
                            job_title = raw_title

                            if " at " in raw_title:
                                parts = raw_title.split(" at ")
                                job_title = parts[0].strip()
                                company_name = parts[1].split("|")[0].split("-")[0].strip()
                            elif " hiring " in raw_title:
                                parts = raw_title.split(" hiring ")
                                company_name = parts[0].strip()
                                job_title = parts[1].split(" in ")[0].split("|")[0].strip()
                            elif " - " in raw_title:
                                parts = raw_title.split(" - ")
                                job_title = parts[0].strip()
                                company_name = parts[1].strip()

                            if not company_name or not job_title:
                                continue

                            desc = ""
                            desc_elem = soup.find("div", class_="jobDescriptionContent") or soup.find("div", id="JobDescriptionContainer")
                            if desc_elem:
                                desc = sanitize_text(desc_elem.get_text(separator=" "))

                            skills = self.normalizer.extract_skills(f"{job_title} {desc}")

                            norm = NormalizedJob(
                                company_name=company_name,
                                job_title=job_title,
                                source="glassdoor",
                                source_url=link,
                                location=location,
                                remote_type=self.normalizer.normalize_remote_type(desc, location),
                                employment_type=self.normalizer.normalize_employment_type(desc),
                                description=desc,
                                skills=skills
                            )
                            results.append(norm)
                except Exception:
                    continue

        except Exception as e:
            logger.debug(f"Glassdoor adapter search error: {e}")

        logger.info(f"Glassdoor adapter collected {len(results)} jobs.")
        return results
