"""
Unstop Job & Opportunity Source Adapter.
Extracts public tech jobs, internships, and hiring challenges from Unstop.
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

logger = get_logger("unstop_adapter")


class UnstopAdapter(BaseJobSourceAdapter):
    """Adapter for Unstop public jobs and hiring listings."""

    def __init__(self, timeout: Optional[int] = None):
        super().__init__(source_name="unstop", timeout=timeout)
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
        query_str = urllib.parse.quote(f"{clean_prof} {location}".strip())

        # Unstop public API search endpoint
        api_url = f"https://unstop.com/api/public/opportunity/search-result?opportunity=jobs&searchTerm={query_str}&per_page={limit}"
        web_url = f"https://unstop.com/jobs?searchTerm={query_str}"

        try:
            with httpx.Client(timeout=self.timeout, follow_redirects=True, headers=self.headers, verify=False) as client:
                resp = client.get(api_url)
                if resp.status_code == 200:
                    try:
                        data = resp.json()
                        items = data.get("data", {}).get("data", []) or data.get("data", [])
                        for item in items:
                            if len(results) >= limit:
                                break
                            title = item.get("title") or item.get("name")
                            org = item.get("organisation", {})
                            company_name = org.get("name") if isinstance(org, dict) else str(org)
                            if not company_name:
                                company_name = item.get("company_name") or "Unstop Partner"

                            job_slug = item.get("public_url") or item.get("seo_url") or ""
                            source_url = f"https://unstop.com/{job_slug}" if job_slug and not job_slug.startswith("http") else job_slug or web_url
                            
                            loc_info = item.get("job_location") or item.get("city") or location
                            desc = sanitize_text(item.get("description") or item.get("details") or "")
                            skills = self.normalizer.extract_skills(f"{title} {desc}")

                            norm = NormalizedJob(
                                company_name=company_name,
                                job_title=title,
                                source="unstop",
                                source_url=source_url,
                                source_job_id=str(item.get("id") or ""),
                                location=loc_info,
                                remote_type=self.normalizer.normalize_remote_type(desc, loc_info),
                                employment_type="Full-time" if "intern" not in (item.get("type") or "").lower() else "Internship",
                                description=desc,
                                skills=skills,
                                posted_date=item.get("created_at") or item.get("start_date")
                            )
                            results.append(norm)
                    except Exception as json_err:
                        logger.debug(f"Unstop JSON parse error: {json_err}")

        except Exception as e:
            logger.debug(f"Unstop adapter query error: {e}")

        logger.info(f"Unstop adapter collected {len(results)} jobs.")
        return results
