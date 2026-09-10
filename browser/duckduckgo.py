"""
DuckDuckGo search scraper for career page and official website discovery.
Uses lightweight HTTP requests with HTML parsing.
"""

import urllib.parse
from typing import List, Optional
import httpx
from bs4 import BeautifulSoup
from config.settings import settings
from utils.logger import get_logger
from utils.url_utils import clean_url, is_social_url

logger = get_logger("duckduckgo")


class DuckDuckGoSearcher:
    """Performs search queries on DuckDuckGo HTML endpoint."""

    def __init__(self, timeout: int = 15):
        self.timeout = timeout
        self.headers = {
            "User-Agent": settings.get_config().user_agent,
            "Accept-Language": "en-US,en;q=0.9",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
        }

    def search(self, query: str, max_results: int = 5) -> List[str]:
        """
        Executes a DuckDuckGo search and extracts organic result URLs.
        """
        results: List[str] = []
        try:
            url = f"https://html.duckduckgo.com/html/?q={urllib.parse.quote(query)}"
            logger.debug(f"DuckDuckGo search query: {query}")
            with httpx.Client(timeout=self.timeout, follow_redirects=True, headers=self.headers) as client:
                response = client.get(url)
                if response.status_code != 200:
                    logger.warning(f"DuckDuckGo returned status {response.status_code}")
                    return []

                soup = BeautifulSoup(response.text, "html.parser")
                links = soup.select(".result__url, .result__snippet, .result__a")
                
                for a_tag in soup.select("a.result__url, a.result__title"):
                    href = a_tag.get("href")
                    if not href:
                        continue
                    # DuckDuckGo wraps target in /l/?kh=-1&uddg=TARGET_URL
                    if "uddg=" in href:
                        parsed = urllib.parse.parse_qs(urllib.parse.urlparse(href).query)
                        target = parsed.get("uddg", [None])[0]
                    else:
                        target = href

                    cleaned = clean_url(target)
                    if cleaned and cleaned not in results:
                        results.append(cleaned)
                        if len(results) >= max_results:
                            break

        except Exception as e:
            logger.warning(f"DuckDuckGo search failed for query '{query}': {e}")

        return results

    def find_career_page(self, company_name: str, domain: Optional[str] = None) -> Optional[str]:
        """Discovers career page using targeted site or company search."""
        queries = []
        if domain:
            queries.append(f"site:{domain} careers OR jobs OR openings")
        queries.append(f"{company_name} careers jobs opportunities")

        for query in queries:
            links = self.search(query, max_results=5)
            for link in links:
                lower = link.lower()
                if any(kw in lower for kw in ["career", "careers", "job", "jobs", "opening", "openings", "join", "hiring", "work-with-us", "vacancies"]):
                    return link
            if links:
                # Return first relevant result if no direct career keyword
                return links[0]
        return None
