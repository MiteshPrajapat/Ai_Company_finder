"""
Social media profile link extractor from website HTML and anchor tags.
"""

import re
from typing import Dict, Optional
from bs4 import BeautifulSoup
from utils.url_utils import clean_url

SOCIAL_PATTERNS = {
    "linkedin": re.compile(r"https?://(?:www\.)?linkedin\.com/(?:company|school|in)/[a-zA-Z0-9_\-\.%]+/?", re.I),
    "facebook": re.compile(r"https?://(?:www\.)?facebook\.com/[a-zA-Z0-9_\-\.%]+/?", re.I),
    "instagram": re.compile(r"https?://(?:www\.)?instagram\.com/[a-zA-Z0-9_\-\.%]+/?", re.I),
    "twitter": re.compile(r"https?://(?:www\.)?(?:twitter|x)\.com/[a-zA-Z0-9_\-\.%]+/?", re.I),
    "youtube": re.compile(r"https?://(?:www\.)?youtube\.com/(?:c/|channel/|user/|@)[a-zA-Z0-9_\-\.%]+/?", re.I),
    "github": re.compile(r"https?://(?:www\.)?github\.com/[a-zA-Z0-9_\-\.%]+/?", re.I)
}


def extract_social_links(html_content: str) -> Dict[str, Optional[str]]:
    """
    Scans HTML content and anchor hrefs for company social media profile URLs.
    """
    profiles: Dict[str, Optional[str]] = {
        "linkedin": None,
        "facebook": None,
        "instagram": None,
        "twitter": None,
        "youtube": None,
        "github": None
    }

    if not html_content:
        return profiles

    try:
        soup = BeautifulSoup(html_content, "html.parser")
        hrefs = [a.get("href") for a in soup.find_all("a", href=True)]

        # Check anchor links first
        for href in hrefs:
            cleaned = clean_url(href)
            if not cleaned:
                continue

            for platform, pattern in SOCIAL_PATTERNS.items():
                if not profiles[platform] and pattern.search(cleaned):
                    # Filter out share/intent links
                    if "share" not in cleaned and "intent" not in cleaned:
                        profiles[platform] = cleaned

        # Fallback search raw text if any platform is missing
        for platform, pattern in SOCIAL_PATTERNS.items():
            if not profiles[platform]:
                match = pattern.search(html_content)
                if match:
                    cleaned = clean_url(match.group(0))
                    if cleaned and "share" not in cleaned:
                        profiles[platform] = cleaned

    except Exception:
        pass

    return profiles
