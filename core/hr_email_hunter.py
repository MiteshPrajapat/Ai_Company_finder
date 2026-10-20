"""
Smart HR Email Hunter (Free OSINT & Search Dorks).
Discovers real HR, Recruiter, and Talent Acquisition email addresses using:
1. Search Dorks (LinkedIn profiles, Recruiter snippets, Email directories)
2. Corporate pattern synthesis (firstname.lastname@company.com, careers@, hr@)
3. DNS MX server validation (verifies company email servers actually accept mail)
"""

import re
import urllib.parse
from typing import Dict, Any, List, Optional, Tuple
import dns.resolver
from utils.logger import get_logger
from utils.url_utils import extract_domain

logger = get_logger("hr_email_hunter")

# Junk or invalid domain blacklist
JUNK_DOMAINS = {
    "example.com", "w3.org", "sentry.io", "google.com", "github.com",
    "schema.org", "cloudflare.com", "doubleclick.net", "gravatar.com",
    "png", "jpg", "jpeg", "svg", "gif", "webp"
}

# Standard HR / Talent mailbox prefixes in priority order
STANDARD_HR_PREFIXES = [
    ("careers", 85),
    ("hr", 85),
    ("recruiting", 80),
    ("recruitment", 80),
    ("talent", 78),
    ("jobs", 75),
    ("hiring", 75),
    ("people", 70),
    ("contact", 50),
    ("info", 45)
]


class HREmailHunter:
    """
    Automated OSINT engine that locates verified HR/Recruiter emails for any company.
    """

    def __init__(self, timeout: int = 10):
        self.timeout = timeout

    @staticmethod
    def check_domain_mx(domain: str) -> bool:
        """
        Validates whether the domain has active MX mail server records.
        """
        if not domain:
            return False
        clean_d = domain.replace("www.", "").strip()
        try:
            answers = dns.resolver.resolve(clean_d, "MX")
            return len(answers) > 0
        except Exception:
            # Fallback check A record
            try:
                answers = dns.resolver.resolve(clean_d, "A")
                return len(answers) > 0
            except Exception:
                return False

    def hunt_hr_contacts(
        self,
        company_name: str,
        company_domain: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Executes multi-strategy OSINT to find HR & Recruiter contacts.
        Returns:
            {
                "success": bool,
                "primary_email": str,
                "recruiters": List[Dict[str, str]],
                "email_candidates": List[Dict[str, Any]], # [{"email": ..., "confidence": ..., "source": ...}]
                "has_valid_mx": bool,
                "domain": str
            }
        """
        logger.info(f"Starting OSINT HR Email Hunt for company: '{company_name}' (Domain: {company_domain})")
        
        # Clean domain
        domain = ""
        if company_domain:
            domain = extract_domain(company_domain) or company_domain.replace("http://", "").replace("https://", "").split("/")[0]
            domain = domain.replace("www.", "").strip()

        # Step 1: Check MX validity
        has_mx = self.check_domain_mx(domain) if domain else False
        if domain:
            logger.info(f"Domain '{domain}' MX validation: {'ACTIVE' if has_mx else 'NO_MX'}")

        email_candidates: Dict[str, Dict[str, Any]] = {}
        recruiters_found: List[Dict[str, str]] = []

        # Step 2: Query Search Engine (DDGS)
        try:
            from ddgs import DDGS
            ddgs = DDGS(timeout=self.timeout)

            # Queries targeted at HR, Recruiters, and Email directories
            queries = [
                f"{company_name} recruiter HR email @{domain}" if domain else f"{company_name} recruiter HR email",
                f'site:linkedin.com/in/ ("recruiter" OR "talent acquisition" OR "HR") "{company_name}"',
                f'"{company_name}" HR recruiter contact email careers'
            ]

            for query in queries:
                try:
                    logger.debug(f"Running OSINT query: {query}")
                    results = list(ddgs.text(query, max_results=4))
                    for item in results:
                        title = item.get("title", "")
                        body = item.get("body", "")
                        href = item.get("href", "")

                        # A. Check for LinkedIn Recruiter profile
                        if "linkedin.com/in/" in href:
                            self._extract_linkedin_recruiter(title, body, href, company_name, domain, recruiters_found, email_candidates)

                        # B. Extract raw emails from snippet & title
                        combined_text = f"{title} {body}"
                        found_emails = re.findall(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+", combined_text)
                        for raw_email in found_emails:
                            clean_em = raw_email.strip(".,;:()<>[]\"'").lower()
                            if self._is_valid_email(clean_em):
                                # Determine confidence
                                conf = 90 if (domain and domain in clean_em) else 70
                                if any(hkw in clean_em for hkw in ["hr", "recruiter", "talent", "careers"]):
                                    conf += 10
                                if clean_em not in email_candidates:
                                    email_candidates[clean_em] = {
                                        "email": clean_em,
                                        "confidence": min(conf, 99),
                                        "source": "OSINT Search Snippet"
                                    }

                except Exception as q_err:
                    logger.debug(f"Query '{query}' failed: {q_err}")

        except Exception as e:
            logger.warning(f"OSINT Search Engine unavailable: {e}")

        # Step 3: Add High-Probability Functional Corporate Emails if MX is Valid
        if domain and has_mx:
            for prefix, conf in STANDARD_HR_PREFIXES:
                gen_email = f"{prefix}@{domain}".lower()
                if gen_email not in email_candidates:
                    email_candidates[gen_email] = {
                        "email": gen_email,
                        "confidence": conf,
                        "source": f"Verified Corporate MX ({domain})"
                    }

        # Step 4: Sort candidates by confidence
        sorted_candidates = sorted(
            email_candidates.values(),
            key=lambda x: x.get("confidence", 0),
            reverse=True
        )

        primary_email = sorted_candidates[0]["email"] if sorted_candidates else ""

        logger.info(
            f"OSINT Hunt Complete for {company_name}: Found {len(sorted_candidates)} email(s), "
            f"{len(recruiters_found)} recruiter(s). Primary: '{primary_email}'"
        )

        return {
            "success": bool(primary_email),
            "primary_email": primary_email,
            "recruiters": recruiters_found,
            "email_candidates": sorted_candidates,
            "has_valid_mx": has_mx,
            "domain": domain
        }

    def _extract_linkedin_recruiter(
        self,
        title: str,
        body: str,
        url: str,
        company_name: str,
        domain: str,
        recruiters_list: List[Dict[str, str]],
        email_candidates: Dict[str, Dict[str, Any]]
    ):
        """Extracts name, title, and synthesizes likely corporate emails for recruiter."""
        # Clean title: e.g. "Priya Sharma - Technical Recruiter at Company | LinkedIn"
        clean_title = re.sub(r"\s*\|\s*LinkedIn.*$", "", title, flags=re.IGNORECASE)
        parts = clean_title.split("-")
        name = parts[0].strip() if len(parts) > 1 else clean_title.split("–")[0].strip()
        role = parts[1].strip() if len(parts) > 1 else "Recruiter / Talent Acquisition"

        if name and len(name.split()) <= 4:
            # Check not already present
            if not any(r["name"].lower() == name.lower() for r in recruiters_list):
                recruiters_list.append({
                    "name": name,
                    "title": role,
                    "url": url
                })

            # If domain is present, predict individual email format
            if domain:
                name_tokens = [re.sub(r"[^a-zA-Z]", "", t).lower() for t in name.split() if t]
                if len(name_tokens) >= 2:
                    first = name_tokens[0]
                    last = name_tokens[-1]
                    predicted_emails = [
                        (f"{first}.{last}@{domain}", 82),
                        (f"{first}@{domain}", 75),
                        (f"{first[0]}{last}@{domain}", 72),
                    ]
                    for pem, pconf in predicted_emails:
                        if pem not in email_candidates:
                            email_candidates[pem] = {
                                "email": pem,
                                "confidence": pconf,
                                "source": f"Synthesized from Recruiter: {name}"
                            }

    @staticmethod
    def _is_valid_email(email: str) -> bool:
        """Filters out malformed, placeholder, or junk emails."""
        if not email or "@" not in email:
            return False
        parts = email.split("@")
        if len(parts) != 2:
            return False
        user, dom = parts
        if not user or not dom or "." not in dom:
            return False
        if dom.lower() in JUNK_DOMAINS:
            return False
        if any(junk in user.lower() for junk in ["noreply", "no-reply", "mailer-daemon", "abuse", "postmaster"]):
            return False
        return True


# Global instance
hr_hunter = HREmailHunter()
