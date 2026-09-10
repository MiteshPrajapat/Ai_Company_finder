"""
Contact page discovery, email extraction, and business contact parser.
"""

import re
from typing import List, Tuple, Optional, Set
import httpx
from bs4 import BeautifulSoup
from config.settings import settings
from database.models import Contact
from utils.email_utils import extract_emails_from_text
from utils.logger import get_logger
from utils.url_utils import clean_url, make_absolute_url
from utils.text_utils import sanitize_text

logger = get_logger("contacts_scraper")

CONTACT_KEYWORDS = [
    "contact", "contact us", "contact-us", "get in touch", "get-in-touch",
    "reach us", "reach-us", "about", "about us", "about-us", "connect"
]

COMMON_CONTACT_PATHS = [
    "/contact", "/contact-us", "/contactus", "/get-in-touch",
    "/about", "/about-us", "/reach-us", "/support"
]


class ContactsScraper:
    """Discovers contact pages and extracts classified business email addresses."""

    def __init__(self, timeout: Optional[int] = None):
        self.timeout = timeout or settings.get_config().request_timeout
        self.headers = {
            "User-Agent": settings.get_config().user_agent,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
        }

    def discover_contact_url(
        self,
        base_url: str,
        homepage_html: Optional[str] = None
    ) -> Optional[str]:
        """Locates the company's dedicated contact page URL."""
        if homepage_html:
            try:
                soup = BeautifulSoup(homepage_html, "html.parser")
                for a in soup.find_all("a", href=True):
                    href = a["href"]
                    text = sanitize_text(a.get_text() or "").lower()
                    href_lower = href.lower()

                    for kw in CONTACT_KEYWORDS:
                        if kw in text or kw in href_lower:
                            abs_url = make_absolute_url(base_url, href)
                            if abs_url and not abs_url.endswith("#"):
                                return abs_url
            except Exception:
                pass

        # Try common paths
        for path in COMMON_CONTACT_PATHS:
            test_url = make_absolute_url(base_url, path)
            if not test_url:
                continue
            try:
                with httpx.Client(timeout=6, follow_redirects=True, headers=self.headers, verify=False) as client:
                    resp = client.get(test_url)
                    if resp.status_code == 200:
                        return str(resp.url)
            except Exception:
                continue

        return None

    def extract_contacts(
        self,
        company_id: int,
        base_url: str,
        homepage_html: Optional[str] = None,
        contact_page_url: Optional[str] = None,
        career_page_html: Optional[str] = None
    ) -> List[Contact]:
        """
        Extracts and classifies business contact emails from homepage, contact page, and career page.
        """
        contacts: List[Contact] = []
        seen_emails: Set[str] = set()

        # 1. Check Homepage HTML
        if homepage_html:
            for email, cat in extract_emails_from_text(homepage_html):
                if email not in seen_emails:
                    seen_emails.add(email)
                    contacts.append(Contact(
                        company_id=company_id,
                        email=email,
                        email_type=cat,
                        source_url=base_url
                    ))

        # 2. Check Career page HTML if available
        if career_page_html:
            for email, cat in extract_emails_from_text(career_page_html):
                if email not in seen_emails:
                    seen_emails.add(email)
                    contacts.append(Contact(
                        company_id=company_id,
                        email=email,
                        email_type=cat,
                        source_url=base_url
                    ))

        # 3. Check Contact page if found
        if contact_page_url and contact_page_url != base_url:
            try:
                with httpx.Client(timeout=self.timeout, follow_redirects=True, headers=self.headers, verify=False) as client:
                    resp = client.get(contact_page_url)
                    if resp.status_code == 200:
                        for email, cat in extract_emails_from_text(resp.text):
                            if email not in seen_emails:
                                seen_emails.add(email)
                                contacts.append(Contact(
                                    company_id=company_id,
                                    email=email,
                                    email_type=cat,
                                    source_url=contact_page_url
                                ))
            except Exception as e:
                logger.debug(f"Error fetching contact page {contact_page_url}: {e}")

        logger.info(f"Extracted {len(contacts)} business emails for company ID {company_id}")
        return contacts
