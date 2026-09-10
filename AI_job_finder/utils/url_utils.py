"""
URL manipulation, normalization, and validation utilities.
"""

import re
from urllib.parse import urlparse, urljoin, urlunparse
from typing import Optional, Set

# Social domains to filter out when checking for company official websites
SOCIAL_DOMAINS: Set[str] = {
    "linkedin.com", "facebook.com", "instagram.com", "twitter.com", "x.com",
    "youtube.com", "github.com", "pinterest.com", "tiktok.com", "medium.com",
    "reddit.com", "quora.com", "yelp.com", "tripadvisor.com", "glassdoor.com",
    "indeed.com", "wikipedia.org", "crunchbase.com", "google.com", "maps.google.com",
    "justdial.com", "indiamart.com", "yellowpages.com", "sulekha.com"
}


def clean_url(url: Optional[str]) -> Optional[str]:
    """Cleans, strips whitespace, and ensures scheme on URL."""
    if not url:
        return None
    url = url.strip()
    if not url or url.startswith("javascript:") or url.startswith("mailto:") or url.startswith("tel:"):
        return None

    # Handle protocol relative or scheme-less URLs
    if url.startswith("//"):
        url = "https:" + url
    elif not url.startswith("http://") and not url.startswith("https://"):
        url = "https://" + url

    try:
        parsed = urlparse(url)
        # Normalize lowercase scheme and host
        scheme = parsed.scheme.lower()
        netloc = parsed.netloc.lower()
        if not netloc:
            return None
        # Remove default port
        if netloc.endswith(":80") and scheme == "http":
            netloc = netloc[:-3]
        elif netloc.endswith(":443") and scheme == "https":
            netloc = netloc[:-4]

        # Reconstruct clean URL
        path = parsed.path or "/"
        clean = urlunparse((scheme, netloc, path, parsed.params, parsed.query, ""))
        return clean
    except Exception:
        return None


def extract_domain(url: Optional[str]) -> Optional[str]:
    """Extracts base domain (e.g., example.com) from any URL."""
    if not url:
        return None
    cleaned = clean_url(url)
    if not cleaned:
        return None
    try:
        parsed = urlparse(cleaned)
        netloc = parsed.netloc.lower()
        # Remove www. prefix if present
        if netloc.startswith("www."):
            netloc = netloc[4:]
        return netloc if "." in netloc else None
    except Exception:
        return None


def is_social_url(url: Optional[str]) -> bool:
    """Checks if the URL belongs to a social media / directory site."""
    domain = extract_domain(url)
    if not domain:
        return False
    for social in SOCIAL_DOMAINS:
        if domain == social or domain.endswith("." + social):
            return True
    return False


def make_absolute_url(base_url: str, link: Optional[str]) -> Optional[str]:
    """Converts a relative link to an absolute URL based on base_url."""
    if not link:
        return None
    link = link.strip()
    if not link or link.startswith("#") or link.startswith("javascript:") or link.startswith("mailto:") or link.startswith("tel:"):
        return None

    try:
        resolved = urljoin(base_url, link)
        return clean_url(resolved)
    except Exception:
        return None


def is_same_domain(url1: Optional[str], url2: Optional[str]) -> bool:
    """Checks if two URLs share the same root domain."""
    d1 = extract_domain(url1)
    d2 = extract_domain(url2)
    if not d1 or not d2:
        return False
    return d1 == d2 or d1.endswith("." + d2) or d2.endswith("." + d1)
