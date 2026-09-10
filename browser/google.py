"""
Google search scraper fallback for discovering career URLs.
"""

import urllib.parse
from typing import List, Optional
import httpx
from bs4 import BeautifulSoup
from config.settings import settings
from utils.logger import get_logger
from utils.url_utils import clean_url, is_social_url

logger = get_logger("google_search")


class GoogleSearcher:
    """Performs public search requests on Google."""

    def __init__(self, timeout: int = 15):
        self.timeout = timeout
        self.headers = {
            "User-Agent": settings.get_config().user_agent,
            "Accept-Language": "en-US,en;q=0.9",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
        }

    def search(self, query: str, max_results: int = 5) -> List[str]:
        results: List[str] = []
        try:
            url = f"https://www.google.com/search?q={urllib.parse.quote(query)}&num={max_results}"
            with httpx.Client(timeout=self.timeout, follow_redirects=True, headers=self.headers) as client:
                resp = client.get(url)
                if resp.status_code != 200:
                    logger.debug(f"Google returned status {resp.status_code}")
                    return []

                soup = BeautifulSoup(resp.text, "html.parser")
                for a in soup.find_all("a", href=True):
                    href = a["href"]
                    if href.startswith("/url?q="):
                        target = href.split("/url?q=")[1].split("&")[0]
                        cleaned = clean_url(target)
                        if cleaned and "google.com" not in cleaned and cleaned not in results:
                            results.append(cleaned)
                            if len(results) >= max_results:
                                break
        except Exception as e:
            logger.debug(f"Google search fallback error: {e}")
        return results

    def find_career_page(self, company_name: str, domain: Optional[str] = None) -> Optional[str]:
        query = f"site:{domain} careers OR jobs" if domain else f"{company_name} careers jobs"
        links = self.search(query, max_results=3)
        for link in links:
            if any(kw in link.lower() for kw in ["career", "job", "opening", "work", "join"]):
                return link
        return links[0] if links else None
