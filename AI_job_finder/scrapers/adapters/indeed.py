"""
Indeed Job Source Adapter.
Extracts public Indeed listings and RSS search feeds using standard HTTP requests.
"""

import urllib.parse
import xml.etree.ElementTree as ET
from typing import List, Optional, Dict, Any
import httpx
from bs4 import BeautifulSoup
from scrapers.adapters.base import BaseJobSourceAdapter
from database.models import NormalizedJob
from core.normalizer import JobNormalizer
from utils.logger import get_logger
from utils.text_utils import sanitize_text

logger = get_logger("indeed_adapter")


class IndeedAdapter(BaseJobSourceAdapter):
    """Adapter for Indeed public job listings and RSS feeds."""

    def __init__(self, timeout: Optional[int] = None):
        super().__init__(source_name="indeed", timeout=timeout)
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
        query_str = urllib.parse.quote(f"{clean_prof}".strip())
        loc_str = urllib.parse.quote(location.strip())

        # 1. Try Indeed RSS Feed (reliable, public, non-blocking)
        rss_urls = [
            f"https://in.indeed.com/rss?q={query_str}&l={loc_str}",
            f"https://www.indeed.com/rss?q={query_str}&l={loc_str}"
        ]

        for feed_url in rss_urls:
            if len(results) >= limit:
                break
            try:
                with httpx.Client(timeout=self.timeout, follow_redirects=True, headers=self.headers, verify=False) as client:
                    resp = client.get(feed_url)
                    if resp.status_code == 200 and "<rss" in resp.text:
                        root = ET.fromstring(resp.text)
                        channel = root.find("channel")
                        if channel is not None:
                            for item in channel.findall("item"):
                                if len(results) >= limit:
                                    break
                                title_elem = item.find("title")
                                link_elem = item.find("link")
                                desc_elem = item.find("description")
                                pub_elem = item.find("pubDate")
                                guid_elem = item.find("guid")

                                raw_title = title_elem.text if title_elem is not None else ""
                                raw_link = link_elem.text if link_elem is not None else ""
                                raw_desc = desc_elem.text if desc_elem is not None else ""
                                posted = pub_elem.text if pub_elem is not None else None
                                guid = guid_elem.text if guid_elem is not None else None

                                # Title format in Indeed RSS is often: "Job Title - Company Name - Location"
                                company_name = ""
                                job_title = raw_title
                                job_loc = location

                                parts = raw_title.split(" - ")
                                if len(parts) >= 3:
                                    job_title = parts[0].strip()
                                    company_name = parts[1].strip()
                                    job_loc = parts[2].strip()
                                elif len(parts) == 2:
                                    job_title = parts[0].strip()
                                    company_name = parts[1].strip()

                                if not company_name or not job_title:
                                    continue

                                # Clean description HTML
                                desc_clean = BeautifulSoup(raw_desc, "html.parser").get_text(separator=" ").strip()
                                skills = self.normalizer.extract_skills(f"{job_title} {desc_clean}")

                                norm = NormalizedJob(
                                    company_name=company_name,
                                    job_title=job_title,
                                    source="indeed",
                                    source_url=raw_link,
                                    source_job_id=guid,
                                    location=job_loc,
                                    remote_type=self.normalizer.normalize_remote_type(desc_clean, job_loc),
                                    employment_type=self.normalizer.normalize_employment_type(desc_clean),
                                    description=desc_clean,
                                    skills=skills,
                                    posted_date=posted
                                )
                                results.append(norm)
            except Exception as e:
                logger.debug(f"Indeed RSS search error for {feed_url}: {e}")

        logger.info(f"Indeed adapter collected {len(results)} jobs.")
        return results
