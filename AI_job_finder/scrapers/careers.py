"""
Career page discovery and job opening parser.
Extracts open positions, job descriptions, metadata, and structured JobPosting schema.
"""

import json
import re
from typing import List, Optional, Tuple, Dict, Any
import httpx
from bs4 import BeautifulSoup
from config.settings import settings
from database.models import Job
from core.job_matcher import JobMatcher
from browser.browser_manager import BrowserManager
from browser.duckduckgo import DuckDuckGoSearcher
from browser.google import GoogleSearcher
from utils.logger import get_logger
from utils.url_utils import clean_url, make_absolute_url, extract_domain, is_same_domain
from utils.text_utils import sanitize_text

logger = get_logger("careers_scraper")

CAREER_KEYWORDS = [
    "career", "careers", "job", "jobs", "opening", "openings",
    "join us", "join-us", "work with us", "work-with-us",
    "opportunities", "vacancies", "vacancy", "we are hiring", "hiring"
]

COMMON_CAREER_PATHS = [
    "/careers", "/career", "/jobs", "/job", "/join-us", "/joinus",
    "/work-with-us", "/vacancies", "/opportunities", "/about/careers"
]


class CareersScraper:
    """Discovers career portals and extracts structured job postings."""

    def __init__(self, timeout: Optional[int] = None, browser_manager: Optional[BrowserManager] = None):
        self.timeout = timeout or settings.get_config().request_timeout
        self.browser_manager = browser_manager
        self.headers = {
            "User-Agent": settings.get_config().user_agent,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
        }
        self.ddg = DuckDuckGoSearcher()
        self.google = GoogleSearcher()

    def discover_career_url(
        self,
        base_url: str,
        company_name: str,
        homepage_html: Optional[str] = None
    ) -> Tuple[Optional[str], Optional[str]]:
        """
        Locates the company's career page URL.
        Returns: (career_url, source_method).
        """
        domain = extract_domain(base_url)
        logger.debug(f"Discovering career page for: {company_name} ({base_url})")

        # 1. Search homepage links if HTML provided
        if homepage_html:
            try:
                soup = BeautifulSoup(homepage_html, "html.parser")
                for a in soup.find_all("a", href=True):
                    href = a["href"]
                    link_text = sanitize_text(a.get_text() or "").lower()
                    href_lower = href.lower()

                    for kw in CAREER_KEYWORDS:
                        if kw in link_text or kw in href_lower:
                            abs_url = make_absolute_url(base_url, href)
                            if abs_url and not abs_url.endswith("#"):
                                logger.info(f"Career link found on homepage for {company_name}: {abs_url}")
                                return abs_url, "homepage_link"
            except Exception as e:
                logger.debug(f"Error checking homepage links: {e}")

        # 2. Try common URL endpoints
        for path in COMMON_CAREER_PATHS:
            test_url = make_absolute_url(base_url, path)
            if not test_url:
                continue
            try:
                with httpx.Client(timeout=8, follow_redirects=True, headers=self.headers, verify=False) as client:
                    resp = client.get(test_url)
                    if resp.status_code == 200 and len(resp.text) > 500:
                        logger.info(f"Career page confirmed via path {path}: {test_url}")
                        return str(resp.url), "common_path"
            except Exception:
                continue

        # 3. Search Engine Fallback (DuckDuckGo / Google)
        pref = settings.get_config().search_engine_fallback
        found_url = None

        if pref in ["duckduckgo", "auto"]:
            found_url = self.ddg.find_career_page(company_name, domain)
            if found_url:
                logger.info(f"Career page found via DuckDuckGo: {found_url}")
                return found_url, "duckduckgo_search"

        if not found_url and pref in ["google", "auto"]:
            found_url = self.google.find_career_page(company_name, domain)
            if found_url:
                logger.info(f"Career page found via Google: {found_url}")
                return found_url, "google_search"

        return None, None

    def extract_jobs(
        self,
        career_url: str,
        company_id: int,
        job_matcher: JobMatcher,
        html_content: Optional[str] = None
    ) -> List[Job]:
        """
        Parses career page HTML to extract job listings and scores them with job_matcher.
        """
        if not html_content:
            if self.browser_manager:
                try:
                    html_content = self.browser_manager.navigate(career_url, wait_seconds=2.0)
                except Exception as e:
                    logger.debug(f"Browser navigation for career URL {career_url} returned: {e}")

            if not html_content:
                try:
                    with httpx.Client(timeout=self.timeout, follow_redirects=True, headers=self.headers, verify=False) as client:
                        resp = client.get(career_url)
                        if resp.status_code == 200:
                            html_content = resp.text
                except Exception as e:
                    logger.warning(f"Failed to fetch career page {career_url}: {e}")
                    return []

        if not html_content:
            return []

        jobs: List[Job] = []
        soup = BeautifulSoup(html_content, "html.parser")

        # 1. Parse JSON-LD Schema.org JobPosting
        schema_jobs = self._extract_jsonld_jobs(soup, career_url, company_id, job_matcher)
        jobs.extend(schema_jobs)

        # 2. Parse HTML cards / elements
        html_jobs = self._extract_html_job_cards(soup, career_url, company_id, job_matcher)
        
        # Merge & deduplicate by title
        seen_titles = {j.title.lower() for j in jobs}
        for hj in html_jobs:
            if hj.title.lower() not in seen_titles:
                jobs.append(hj)
                seen_titles.add(hj.title.lower())

        logger.info(f"Extracted {len(jobs)} relevant jobs from {career_url}")
        return jobs

    def _extract_jsonld_jobs(
        self,
        soup: BeautifulSoup,
        career_url: str,
        company_id: int,
        job_matcher: JobMatcher
    ) -> List[Job]:
        """Extracts jobs structured with Schema.org JobPosting."""
        jobs: List[Job] = []
        for script in soup.find_all("script", type="application/ld+json"):
            try:
                if not script.string:
                    continue
                data = json.loads(script.string)
                items = data if isinstance(data, list) else [data]

                for item in items:
                    if item.get("@type") == "JobPosting":
                        title = sanitize_text(item.get("title", ""))
                        if not title:
                            continue

                        desc = sanitize_text(item.get("description", ""))
                        loc = ""
                        raw_loc = item.get("jobLocation")
                        if isinstance(raw_loc, dict):
                            addr = raw_loc.get("address", raw_loc)
                            if isinstance(addr, dict):
                                parts = [
                                    addr.get("streetAddress"),
                                    addr.get("addressLocality"),
                                    addr.get("addressRegion"),
                                    addr.get("addressCountry")
                                ]
                                loc = ", ".join([str(p).strip() for p in parts if p and not str(p).startswith("{")])
                            else:
                                loc = str(addr).strip()
                        elif isinstance(raw_loc, list) and raw_loc:
                            loc = sanitize_text(str(raw_loc[0]))
                        elif isinstance(raw_loc, str):
                            loc = sanitize_text(raw_loc)

                        # Clean out any stray JSON residue
                        if "{" in loc or "@type" in loc:
                            loc = re.sub(r"[{'\"}\]]", "", loc).strip()

                        emp_type = item.get("employmentType", "Full Time")
                        if isinstance(emp_type, list):
                            emp_type = ", ".join(emp_type)

                        job_url = clean_url(item.get("url")) or career_url
                        score = job_matcher.calculate_relevance(title=title, description=desc)

                        if job_matcher.is_relevant(score):
                            jobs.append(Job(
                                company_id=company_id,
                                title=title,
                                job_url=job_url,
                                location=loc or None,
                                employment_type=str(emp_type) if emp_type else None,
                                description=desc[:1000] if desc else None,
                                source="json_ld_schema",
                                relevance_score=score
                            ))
            except Exception:
                pass
        return jobs

    def _extract_html_job_cards(
        self,
        soup: BeautifulSoup,
        career_url: str,
        company_id: int,
        job_matcher: JobMatcher
    ) -> List[Job]:
        """Extracts job openings from generic HTML tags, lists, cards, and tables."""
        jobs: List[Job] = []

        # Candidate containers with job-like classes or attributes
        candidates = soup.find_all(
            ["div", "li", "tr", "article", "section"],
            class_=re.compile(r"job|career|position|vacancy|opening|role|listing", re.I)
        )

        for el in candidates:
            # Look for header or link inside candidate
            title_tag = el.find(["h2", "h3", "h4", "h5", "a", "strong"])
            if not title_tag:
                continue

            title = sanitize_text(title_tag.get_text())
            if not title or len(title) < 3 or len(title) > 80:
                continue

            # Must contain at least some common role word or match target profession
            score = job_matcher.calculate_relevance(title=title)
            if not job_matcher.is_relevant(score):
                continue

            # Find job link
            link_tag = el.find("a", href=True) if el.name != "a" else el
            job_url = career_url
            if link_tag and link_tag.get("href"):
                abs_job_url = make_absolute_url(career_url, link_tag["href"])
                if abs_job_url:
                    job_url = abs_job_url

            # Extract snippet / location if present
            el_text = sanitize_text(el.get_text())
            location = None
            work_mode = None
            if "remote" in el_text.lower():
                work_mode = "Remote"
            elif "hybrid" in el_text.lower():
                work_mode = "Hybrid"
            elif "on-site" in el_text.lower() or "onsite" in el_text.lower():
                work_mode = "On-site"

            jobs.append(Job(
                company_id=company_id,
                title=title,
                job_url=job_url,
                location=location,
                work_mode=work_mode,
                description=el_text[:500] if len(el_text) > len(title) else None,
                source="career_page_html",
                relevance_score=score
            ))

        return jobs
