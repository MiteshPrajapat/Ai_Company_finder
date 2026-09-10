"""
Email parsing, classification, and validation utilities.
"""

import re
from typing import List, Tuple, Set

# Regex pattern for valid email extraction
EMAIL_REGEX = re.compile(
    r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+",
    re.IGNORECASE
)

# Invalid file extensions or substrings mistakenly matched as emails
INVALID_EMAIL_EXTENSIONS = {
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".css", ".js",
    ".woff", ".woff2", ".ttf", ".eot", ".mp4", ".mp3", ".pdf", ".zip"
}

# Generic bot/tracking/dummy emails to filter out
IGNORE_EMAIL_PATTERNS = [
    r"sentry\.", r"wixpress\.com",
    r"yourname@", r"username@", r"email@email\.com",
    r"noreply@", r"no-reply@", r"donotreply@", r"mailer-daemon@",
    r"webpack", r"bootstrap", r"cloudflare"
]

# Classification keywords
CATEGORY_KEYWORDS = {
    "Careers": ["career", "careers", "talent", "hire", "hiring", "recruit", "recruitment", "intern", "internship"],
    "HR": ["hr", "humanresources", "people", "peopleops", "work"],
    "Jobs": ["job", "jobs", "apply", "vacancies", "vacancy", "opening", "openings"],
    "Sales": ["sales", "business", "bd", "bizdev", "deals", "growth", "partnerships", "commercial"],
    "Support": ["support", "help", "care", "service", "customerservice", "helpdesk"],
    "General": ["info", "contact", "hello", "hi", "office", "team", "inquiry", "enquiry", "admin", "mail"]
}


def classify_email(email: str) -> str:
    """Classifies an email address into a category (Careers, HR, Jobs, Sales, Support, General, Other)."""
    user_part = email.split("@")[0].lower().replace(".", "").replace("-", "").replace("_", "")

    for category, keywords in CATEGORY_KEYWORDS.items():
        for kw in keywords:
            if kw in user_part:
                return category

    return "General"


def extract_emails_from_text(text: str) -> List[Tuple[str, str]]:
    """
    Extracts, deduplicates, filters, and classifies emails from arbitrary text/HTML.
    Returns a list of tuples: (email_address, email_type).
    """
    if not text:
        return []

    raw_matches = EMAIL_REGEX.findall(text)
    seen_emails: Set[str] = set()
    results: List[Tuple[str, str]] = []

    for raw in raw_matches:
        email = raw.strip().lower()

        # Remove trailing dot or punctuation
        email = re.sub(r"[.,;:'\">]+$", "", email)
        email = re.sub(r"^[<'\"]+", "", email)

        if not email or "@" not in email:
            continue

        # Check for invalid extensions
        if any(email.endswith(ext) for ext in INVALID_EMAIL_EXTENSIONS):
            continue

        # Check for ignored patterns
        if any(re.search(pat, email) for pat in IGNORE_EMAIL_PATTERNS):
            continue

        # Check length & basic syntax validity
        parts = email.split("@")
        if len(parts) != 2:
            continue
        user, domain = parts
        if len(user) < 1 or len(domain) < 3 or "." not in domain:
            continue

        # Validate that domain ends with an alphabet-only TLD of 2-12 letters (rejects version strings like @1.19.1)
        tld = domain.split(".")[-1]
        if not tld.isalpha() or len(tld) < 2 or len(tld) > 14:
            continue

        # Reject common package or script identifiers
        if any(pkg in user for pkg in ["jquery", "npm", "bootstrap", "polyfill", "webpack", "fontawesome", "lodash", "react-"]):
            continue

        # Domain must have valid alphanumeric structure
        if not re.match(r"^[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$", domain):
            continue

        if email in seen_emails:
            continue

        seen_emails.add(email)
        category = classify_email(email)
        results.append((email, category))

    # Sort so Careers / HR / Jobs emails appear first
    priority = {"Careers": 0, "HR": 1, "Jobs": 2, "General": 3, "Sales": 4, "Support": 5}
    results.sort(key=lambda item: priority.get(item[1], 99))
    return results
