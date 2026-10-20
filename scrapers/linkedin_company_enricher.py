"""
LinkedIn Company & Website Contact Enrichment Pipeline.
Implements:
1. LinkedIn Company "About" page scraping (Website, Phone, Industry, Size, Headquarters).
2. Intelligent Fallback: Search engine discovery + Industry validation if website not on LinkedIn.
3. Website Scraping: Crawls homepage, /contact, /about, /careers to extract all business & HR emails.
"""

import re
import urllib.parse
from typing import Dict, Any, List, Optional, Tuple
import httpx
from bs4 import BeautifulSoup
from config.settings import settings
from utils.logger import get_logger
from utils.url_utils import clean_url, extract_domain, is_social_url
from utils.email_utils import extract_emails_from_text

logger = get_logger("linkedin_company_enricher")

NON_COMPANY_DOMAINS = {
    "linkedin.com", "facebook.com", "instagram.com", "twitter.com",
    "x.com", "youtube.com", "glassdoor.com", "indeed.com", "ambitionbox.com",
    "naukri.com", "zaubacorp.com", "instafinancials.com", "zoominfo.com",
    "justdial.com", "crunchbase.com", "wikipedia.org", "yellowpages.com"
}


class LinkedInCompanyEnricher:
    """Enriches company profile from LinkedIn About tab or verified search fallback."""

    def __init__(self, timeout: int = 10):
        self.timeout = timeout
        self.headers = {
            "User-Agent": settings.get_config().user_agent,
            "Accept-Language": "en-US,en;q=0.9",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
        }

    def discover_linkedin_url(
        self,
        company_name: str,
        location: Optional[str] = None,
        driver: Optional[Any] = None
    ) -> Optional[str]:
        """
        Discovers the official LinkedIn company page URL using live browser search or DDGS search.
        """
        loc_term = f" {location}" if location else ""
        query = f'site:linkedin.com/company "{company_name}"{loc_term}'

        # Method A: Use live browser if available so user sees search on screen
        if driver:
            try:
                import time
                google_url = f"https://www.google.com/search?q={urllib.parse.quote(query)}"
                logger.info(f"Opening live browser to search LinkedIn company: {google_url}")
                driver.get(google_url)
                time.sleep(1.8)
                links = driver.find_elements("css selector", "a[href*='linkedin.com/company/']")
                for link in links:
                    href = link.get_attribute("href")
                    if href and "linkedin.com/company/" in href:
                        clean = href.split("?")[0].rstrip("/")
                        logger.info(f"Live browser discovered LinkedIn URL: {clean}")
                        return clean
            except Exception as e:
                logger.debug(f"Live browser search for LinkedIn failed: {e}")

        # Method B: Search via DDGS
        try:
            from ddgs import DDGS
            ddgs = DDGS(timeout=self.timeout)
            results = list(ddgs.text(query, max_results=5))
            for item in results:
                href = item.get("href", "")
                if "linkedin.com/company/" in href:
                    clean = href.split("?")[0].rstrip("/")
                    logger.info(f"DDGS discovered LinkedIn URL: {clean}")
                    return clean
        except Exception as e:
            logger.debug(f"DDGS search error for LinkedIn URL: {e}")

        # Method C: Slug fallback
        slug = re.sub(r"[^a-zA-Z0-9]+", "-", company_name.lower()).strip("-")
        if slug:
            return f"https://www.linkedin.com/company/{slug}"
        return None

    def enrich_from_linkedin_about(
        self,
        company_name: str,
        company_linkedin_url: Optional[str] = None,
        driver: Optional[Any] = None
    ) -> Dict[str, Any]:
        """
        Extracts Website, Phone, Industry, Company Size, and Headquarters
        from LinkedIn company 'About' section.
        """
        result = {
            "website": None,
            "phone": None,
            "industry": None,
            "company_size": None,
            "headquarters": None,
            "linkedin_url": company_linkedin_url,
            "success": False
        }

        # Step 1: Discover real LinkedIn URL if not provided
        if not company_linkedin_url or "linkedin.com/company" not in company_linkedin_url:
            discovered = self.discover_linkedin_url(company_name, driver=driver)
            if discovered:
                company_linkedin_url = discovered
                result["linkedin_url"] = company_linkedin_url

        about_url = self._build_about_url(company_name, company_linkedin_url)
        if not about_url:
            return result

        logger.info(f"Navigating to LinkedIn About page for '{company_name}': {about_url}")

        # Method A: Use live browser driver if provided
        if driver:
            try:
                import time
                driver.get(about_url)
                time.sleep(2.5)  # Allow page to render visibly on screen
                html = driver.page_source
                parsed = self._parse_linkedin_about_html(html)
                parsed["linkedin_url"] = company_linkedin_url
                if parsed.get("website") or parsed.get("phone") or parsed.get("company_size") or parsed.get("industry"):
                    parsed["success"] = True
                    return parsed
            except Exception as e:
                logger.debug(f"Live browser navigation to LinkedIn about failed: {e}")

        # Method B: Public HTTP request
        try:
            with httpx.Client(timeout=self.timeout, follow_redirects=True, headers=self.headers, verify=False) as client:
                resp = client.get(about_url)
                if resp.status_code == 200:
                    parsed = self._parse_linkedin_about_html(resp.text)
                    parsed["linkedin_url"] = company_linkedin_url
                    if parsed.get("website") or parsed.get("phone") or parsed.get("company_size") or parsed.get("industry"):
                        parsed["success"] = True
                        return parsed
        except Exception as e:
            logger.debug(f"HTTP request to LinkedIn about page failed: {e}")

        return result

    def fallback_search_and_verify_website(
        self,
        company_name: str,
        location: Optional[str] = None,
        industry_hint: Optional[str] = None
    ) -> Optional[str]:
        """
        Fallback Method:
        1. Searches for company official website via DDGS.
        2. Inspects top search results and filters out job boards/directories.
        3. Verifies that the website matches the company and industry (Software, IT, etc.).
        """
        logger.info(f"Executing Fallback Search for company website: '{company_name}' ({location or ''})")
        loc_term = f" {location}" if location else ""
        query = f'"{company_name}"{loc_term} official website'

        try:
            from ddgs import DDGS
            ddgs = DDGS(timeout=self.timeout)
            results = list(ddgs.text(query, max_results=6))

            for item in results:
                href = item.get("href", "")
                title = item.get("title", "")
                body = item.get("body", "")

                domain = extract_domain(href)
                if not domain or any(d in domain.lower() for d in NON_COMPANY_DOMAINS):
                    continue

                # Verify relevancy
                combined_text = f"{title} {body} {href}".lower()
                clean_name = re.sub(r"[^a-zA-Z0-9]", "", company_name.lower())

                # Check if company name token appears in domain or title
                if clean_name in domain.lower() or company_name.lower() in combined_text:
                    # Industry / type verification
                    if self._verify_industry_match(combined_text, industry_hint):
                        logger.info(f"Verified official company website found: {href} ({title})")
                        return clean_url(href)

            # Secondary pass: less strict if top result contains company name in domain
            for item in results[:3]:
                href = item.get("href", "")
                domain = extract_domain(href)
                if domain and not any(d in domain.lower() for d in NON_COMPANY_DOMAINS):
                    clean_name = re.sub(r"[^a-zA-Z0-9]", "", company_name.lower())
                    if clean_name[:5] in domain.lower():
                        return clean_url(href)

        except Exception as e:
            logger.warning(f"Fallback search error for '{company_name}': {e}")

        return None

    def scrape_website_emails(self, website_url: str) -> List[Dict[str, str]]:
        """
        Crawls the company website (homepage, /contact, /about, /careers)
        and extracts all corporate & HR emails.
        """
        if not website_url:
            return []

        logger.info(f"Scraping company website for emails: {website_url}")
        emails_found: Dict[str, str] = {}
        target_paths = ["", "/contact", "/contact-us", "/about", "/about-us", "/careers"]

        domain = extract_domain(website_url)

        for path in target_paths:
            test_url = website_url.rstrip("/") + path
            try:
                with httpx.Client(timeout=8, follow_redirects=True, headers=self.headers, verify=False) as client:
                    resp = client.get(test_url)
                    if resp.status_code == 200:
                        for email, cat in extract_emails_from_text(resp.text):
                            if email not in emails_found:
                                emails_found[email] = cat
            except Exception:
                continue

        result = [{"email": em, "type": cat, "source": website_url} for em, cat in emails_found.items()]
        logger.info(f"Scraped {len(result)} email(s) from {website_url}")
        return result

    def full_enrichment_flow(
        self,
        company_name: str,
        company_linkedin_url: Optional[str] = None,
        location: Optional[str] = None,
        industry_hint: Optional[str] = None,
        driver: Optional[Any] = None
    ) -> Dict[str, Any]:
        """
        Executes complete end-to-end workflow:
        1. Extract LinkedIn About (Website, Phone, Industry, etc.)
        2. If website missing, execute search fallback with industry match check
        3. Scrape discovered website for all emails
        """
        # Step 1: LinkedIn About
        li_data = self.enrich_from_linkedin_about(company_name, company_linkedin_url, driver=driver)
        website = li_data.get("website")
        phone = li_data.get("phone")
        industry = li_data.get("industry") or industry_hint
        source = "linkedin_about" if website else None

        # Step 2: Fallback Search if website missing
        if not website:
            logger.info(f"Website not found on LinkedIn for '{company_name}'. Running search fallback...")
            website = self.fallback_search_and_verify_website(company_name, location, industry_hint=industry)
            if website:
                source = "search_fallback_verified"

        # Step 3: Scrape website for emails
        emails = []
        if website:
            emails = self.scrape_website_emails(website)

        return {
            "company_name": company_name,
            "website": website,
            "phone": phone,
            "industry": industry,
            "headquarters": li_data.get("headquarters") or location,
            "company_size": li_data.get("company_size"),
            "linkedin_url": li_data.get("linkedin_url"),
            "emails": emails,
            "source": source
        }

    # -------------------------------------------------------------------------
    # Internal Helpers
    # -------------------------------------------------------------------------
    def _build_about_url(self, company_name: str, linkedin_url: Optional[str]) -> Optional[str]:
        if linkedin_url:
            clean = linkedin_url.split("?")[0].rstrip("/")
            if "/about" not in clean:
                clean = clean + "/about/"
            return clean

        # Slugify company name
        slug = re.sub(r"[^a-zA-Z0-9]+", "-", company_name.lower()).strip("-")
        if slug:
            return f"https://www.linkedin.com/company/{slug}/about/"
        return None

    def _parse_linkedin_about_html(self, html: str) -> Dict[str, Any]:
        """Parses Overview definition lists in LinkedIn About page."""
        data = {
            "website": None,
            "phone": None,
            "industry": None,
            "company_size": None,
            "headquarters": None
        }
        soup = BeautifulSoup(html, "html.parser")

        # Approach 1: Check <dt> and <dd> pairs
        dts = soup.find_all("dt")
        for dt in dts:
            label = dt.get_text().strip().lower()
            dd = dt.find_next_sibling("dd")
            if not dd:
                continue
            val = dd.get_text().strip()

            if "website" in label:
                link = dd.find("a")
                data["website"] = link["href"] if link and "href" in link.attrs else val
            elif "phone" in label:
                data["phone"] = val
            elif "industry" in label:
                data["industry"] = val
            elif "company size" in label:
                data["company_size"] = val
            elif "headquarters" in label:
                data["headquarters"] = val

        # Approach 2: Regex fallback over visible text if structure differs
        if not data["website"]:
            web_match = re.search(r"Website\s*\n*\s*(https?://[^\s\"'<>]+)", html, re.I)
            if web_match:
                data["website"] = web_match.group(1).strip()

        if not data["phone"]:
            phone_match = re.search(r"Phone\s*\n*\s*([\+0-9\s\-()]{8,20})", html, re.I)
            if phone_match:
                data["phone"] = phone_match.group(1).strip()

        # Clean external redirect wrappers (e.g. linkedin.com/redir/redirect?url=...)
        if data["website"] and "linkedin.com/redir" in data["website"]:
            parsed = urllib.parse.parse_qs(urllib.parse.urlparse(data["website"]).query)
            data["website"] = parsed.get("url", [data["website"]])[0]

        return data

    def _verify_industry_match(self, text: str, hint: Optional[str]) -> bool:
        """Verifies if the scraped page text matches target business/IT/software keywords."""
        keywords = [
            "software", "technology", "tech", "it services", "solutions",
            "consulting", "legal", "fintech", "developer", "digital",
            "platform", "products", "careers", "company", "services"
        ]
        if hint:
            keywords.extend(hint.lower().split())

        matched_count = sum(1 for kw in set(keywords) if kw in text)
        return matched_count >= 1


# Global instance
linkedin_enricher = LinkedInCompanyEnricher()
