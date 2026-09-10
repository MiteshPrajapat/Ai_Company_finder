"""
Text processing, sanitization, and normalization utilities.
"""

import re
import html
from typing import List, Optional


def sanitize_text(text: Optional[str]) -> str:
    """Cleans up text by unescaping HTML entities, removing excessive whitespace, and trimming."""
    if not text:
        return ""
    # Unescape HTML entities
    unescaped = html.unescape(text)
    # Strip HTML tags
    stripped = re.sub(r"<[^>]+>", " ", unescaped)
    # Normalize multiple whitespace characters
    cleaned = re.sub(r"\s+", " ", stripped).strip()
    return cleaned


def normalize_company_name(name: Optional[str]) -> str:
    """
    Normalizes company names for deduplication.
    E.g., "ABC Technologies Pvt. Ltd." -> "abc technologies"
    """
    if not name:
        return ""
    name = name.lower().strip()

    # Remove common suffixes and company legal terms
    legal_terms = [
        r"\bpvt\.?\s*ltd\.?\b",
        r"\bprivate\s+limited\b",
        r"\blimited\b",
        r"\bltd\.?\b",
        r"\binc\.?\b",
        r"\bllc\b",
        r"\bcorp\.?\b",
        r"\bcorporation\b",
        r"\bco\.?\b",
        r"\btechnologies\b",
        r"\btechnology\b",
        r"\bsolutions\b",
        r"\bservices\b",
        r"\bgroup\b",
        r"\benterprises\b"
    ]

    for term in legal_terms:
        name = re.sub(term, "", name)

    # Remove punctuation & symbols
    name = re.sub(r"[^a-z0-9\s]", "", name)
    # Collapse whitespace
    name = re.sub(r"\s+", " ", name).strip()
    return name


def extract_keywords(text: str) -> List[str]:
    """Extracts alphanumeric words of length >= 2 from text."""
    if not text:
        return []
    words = re.findall(r"\b[a-zA-Z0-9+#.-]{2,}\b", text.lower())
    return list(dict.fromkeys(words))


def clean_location_display(raw_loc: Optional[str]) -> str:
    """
    Parses stringified JSON/dict addresses or raw strings into clean human-readable locations.
    e.g. "{'@type': 'PostalAddress', 'streetAddress': '108, First Floor...', 'addressLocality': 'Jaipur'}"
    -> "108, First Floor, Jaipur, IN"
    """
    if not raw_loc:
        return "Location unavailable"

    raw_loc = str(raw_loc).strip()
    if not raw_loc or raw_loc in ["None", "null", "{}"]:
        return "Location unavailable"

    # If it looks like a dict/JSON string
    if raw_loc.startswith("{") or "@type" in raw_loc:
        try:
            import ast
            parsed = ast.literal_eval(raw_loc)
            if isinstance(parsed, dict):
                parts = []
                for k in ["streetAddress", "addressLocality", "addressRegion", "postalCode", "addressCountry"]:
                    val = parsed.get(k)
                    if val and isinstance(val, str) and not val.startswith("{"):
                        parts.append(val.strip())
                if parts:
                    return ", ".join(parts)
        except Exception:
            pass

        # Fallback regex extraction of address parts if AST fails
        clean = re.sub(r"['\"\{\}]", "", raw_loc)
        clean = re.sub(r"@type\s*:\s*\w+,?", "", clean)
        clean = re.sub(r"(streetAddress|addressLocality|addressRegion|postalCode|addressCountry)\s*:\s*", "", clean)
        clean = re.sub(r"\s+", " ", clean).strip(", ")
        return clean or "Location unavailable"

    return raw_loc


def format_employment_type(emp_type: Optional[str]) -> str:
    """Formats employment type strings like FULL_TIME -> Full Time."""
    if not emp_type:
        return "Full Time"
    s = str(emp_type).replace("_", " ").strip().title()
    return s if s else "Full Time"


def is_valid_contact_email(email: Optional[str]) -> bool:
    """Validates if an email is a real business email and not a technical string / package name."""
    if not email:
        return False
    email = str(email).strip().lower()
    if "@" not in email:
        return False

    # Check for unwanted version strings or package names
    if any(bad in email for bad in ["jquery", "npm", "webpack", "bootstrap", "wght@", "polyfill", "fontawesome"]):
        return False

    parts = email.split("@")
    if len(parts) != 2:
        return False
    user, domain = parts
    if not user or not domain or "." not in domain:
        return False

    # Domain TLD must be alphabetic
    tld = domain.split(".")[-1]
    if not tld.isalpha() or len(tld) < 2 or len(tld) > 14:
        return False

    # Must match valid email regex
    if not re.match(r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$", email):
        return False

    return True

