"""
Website liveness checker, HTTP probe, and metadata/company-type detection.
"""

import json
from datetime import datetime
from typing import Tuple, Optional, Dict, Any
import httpx
from bs4 import BeautifulSoup
from config.settings import settings
from utils.logger import get_logger
from utils.url_utils import clean_url, extract_domain
from utils.text_utils import sanitize_text

logger = get_logger("website_scraper")


class WebsiteChecker:
    """Checks website availability, fetches HTML, and detects company type."""

    def __init__(self, timeout: Optional[int] = None):
        self.timeout = timeout or settings.get_config().request_timeout
        self.headers = {
            "User-Agent": settings.get_config().user_agent,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9"
        }

    def check_liveness(self, url: str) -> Tuple[str, Optional[str], Optional[str]]:
        """
        Tests whether a website is reachable and live.
        Returns: (status: 'LIVE'|'OFFLINE'|'TIMEOUT'|'BLOCKED'|'UNKNOWN', resolved_url, html_content).
        """
        cleaned = clean_url(url)
        if not cleaned:
            return "OFFLINE", None, None

        logger.debug(f"Probing website liveness for: {cleaned}")
        try:
            with httpx.Client(
                timeout=self.timeout,
                follow_redirects=True,
                headers=self.headers,
                verify=False  # Allow self-signed or unverified SSL certs safely for checking
            ) as client:
                response = client.get(cleaned)

                if response.status_code in [200, 201, 202, 301, 302, 307, 308]:
                    final_url = str(response.url)
                    html_content = response.text
                    return "LIVE", final_url, html_content
                elif response.status_code in [401, 403, 429]:
                    return "BLOCKED", str(response.url), response.text
                elif response.status_code in [404, 410, 500, 502, 503, 504]:
                    return "OFFLINE", str(response.url), None
                else:
                    return "UNKNOWN", str(response.url), None

        except httpx.TimeoutException:
            logger.warning(f"Connection timeout for {cleaned}")
            return "TIMEOUT", cleaned, None
        except httpx.ConnectError:
            logger.warning(f"Connection/DNS failure for {cleaned}")
            return "OFFLINE", cleaned, None
        except Exception as e:
            logger.warning(f"Website probe error for {cleaned}: {e}")
            return "OFFLINE", cleaned, None

    def detect_company_type_and_meta(self, html_content: str, current_type: Optional[str] = None) -> Dict[str, Any]:
        """
        Parses page title, meta description, and Schema.org JSON-LD to classify company type.
        """
        result = {
            "title": "",
            "description": "",
            "detected_type": current_type,
            "type_source": "google_maps" if current_type else None,
            "keywords": []
        }

        if not html_content:
            return result

        try:
            soup = BeautifulSoup(html_content, "html.parser")

            # 1. Title
            title_tag = soup.find("title")
            if title_tag and title_tag.string:
                result["title"] = sanitize_text(title_tag.string)

            # 2. Meta description
            desc_tag = soup.find("meta", attrs={"name": "description"}) or soup.find("meta", attrs={"property": "og:description"})
            if desc_tag and desc_tag.get("content"):
                result["description"] = sanitize_text(desc_tag["content"])

            # 3. Meta keywords
            kw_tag = soup.find("meta", attrs={"name": "keywords"})
            if kw_tag and kw_tag.get("content"):
                result["keywords"] = [k.strip() for k in kw_tag["content"].split(",") if k.strip()]

            # 4. Schema.org JSON-LD
            for script in soup.find_all("script", type="application/ld+json"):
                try:
                    if not script.string:
                        continue
                    data = json.loads(script.string)
                    if isinstance(data, list):
                        data = data[0]
                    schema_type = data.get("@type", "")
                    if schema_type in ["Organization", "Corporation", "LocalBusiness", "MedicalOrganization", "EducationalOrganization"]:
                        if not result["detected_type"]:
                            result["detected_type"] = schema_type
                            result["type_source"] = "schema.org"
                except Exception:
                    pass

            # 5. Fallback heuristics from title / meta
            if not result["detected_type"]:
                combined_text = (result["title"] + " " + result["description"]).lower()
                industry_indicators = {
                    "Software Company": ["software", "saas", "app development", "mobile apps", "cloud solutions"],
                    "IT Company": ["it services", "it solutions", "information technology", "managed services"],
                    "Marketing Company": ["digital marketing", "seo", "branding", "advertising agency", "media"],
                    "Consulting Company": ["consulting", "advisory", "strategy", "management consulting"],
                    "Healthcare": ["hospital", "clinic", "healthcare", "pharma", "medical"],
                    "E-commerce": ["shop", "store", "buy online", "ecommerce", "retail"],
                    "Finance Company": ["fintech", "financial", "investment", "banking", "wealth management"],
                    "Education": ["academy", "institute", "school", "training", "university", "learning"],
                    "Real Estate": ["real estate", "properties", "realtors", "builders", "housing"]
                }
                for ind_name, kws in industry_indicators.items():
                    if any(kw in combined_text for kw in kws):
                        result["detected_type"] = ind_name
                        result["type_source"] = "meta_heuristics"
                        break

        except Exception as e:
            logger.debug(f"Metadata parsing error: {e}")

        return result
