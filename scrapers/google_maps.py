"""
Google Maps scraper for discovering companies based on location and company type.
Utilizes Selenium WebDriver for dynamic scrolling and comprehensive data extraction.
"""

import time
import re
import urllib.parse
from typing import List, Optional, Callable
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from browser.browser_manager import BrowserManager
from database.models import Company
from core.normalizer import JobNormalizer
from utils.logger import get_logger
from utils.url_utils import clean_url, extract_domain, is_social_url
from utils.text_utils import normalize_company_name, sanitize_text

logger = get_logger("google_maps_scraper")


class GoogleMapsScraper:
    """Scrapes Google Maps place listings for company discovery."""

    def __init__(self, browser_manager: Optional[BrowserManager] = None):
        self.browser_manager = browser_manager or BrowserManager()

    def build_search_query(self, city: str, state: str, country: str, company_type: str) -> str:
        """Constructs an optimized search query for Google Maps."""
        location_parts = [p.strip() for p in [city, state, country] if p.strip()]
        location_str = ", ".join(location_parts) if location_parts else "Jaipur, Rajasthan, India"
        
        type_str = company_type.strip() if company_type and company_type != "Other" else "IT Company"
        # If type does not end in 'companies' or 'company', format nicely
        query = f"{type_str} in {location_str}"
        return query

    def search_companies(
        self,
        query: str,
        limit: int = 10,
        progress_callback: Optional[Callable[[int, int, str], None]] = None,
        is_stopped: Optional[Callable[[], bool]] = None
    ) -> List[Company]:
        """
        Executes Google Maps search and extracts up to `limit` companies.
        Progress callback receives: (found_count, target_count, latest_company_name).
        """
        logger.info(f"Starting Google Maps search for query: '{query}' (Target limit: {limit})")
        driver = self.browser_manager.get_driver()
        encoded_query = urllib.parse.quote(query)
        maps_url = f"https://www.google.com/maps/search/{encoded_query}"

        companies: List[Company] = []
        seen_names = set()
        seen_urls = set()

        try:
            driver.get(maps_url)
            time.sleep(2.5)

            # Wait for results or feed container
            wait = WebDriverWait(driver, 15)
            try:
                wait.until(
                    EC.presence_of_element_located((By.XPATH, "//div[@role='feed'] | //div[contains(@class, 'Nv2PK')] | //a[contains(@href, '/maps/place/')]"))
                )
            except Exception:
                logger.warning("Google Maps container wait timed out, attempting extraction on whatever loaded.")

            # Scroll and collect listings
            scroll_attempts = 0
            max_scroll_attempts = max(20, limit * 4)

            while len(companies) < limit and scroll_attempts < max_scroll_attempts:
                if is_stopped and is_stopped():
                    logger.info("Search stopped by user request.")
                    break

                # Extract company cards currently rendered (prioritize top-level card containers)
                cards = driver.find_elements(By.XPATH, "//div[contains(@class, 'Nv2PK')]")
                if not cards:
                    cards = driver.find_elements(By.XPATH, "//div[@role='article'] | //a[contains(@href, '/maps/place/')]")
                
                new_found_in_pass = 0
                for card in cards:
                    if len(companies) >= limit:
                        break
                    if is_stopped and is_stopped():
                        break

                    try:
                        comp = self._parse_card_element(card)
                        if comp and comp.name and comp.normalized_name:
                            name_key = comp.normalized_name
                            url_key = comp.maps_url

                            # Check for duplicates
                            if name_key in seen_names or (url_key and url_key in seen_urls):
                                # Update website info if previously missing
                                if comp.website_url:
                                    for existing in companies:
                                        if existing.normalized_name == name_key or (url_key and existing.maps_url == url_key):
                                            if not existing.website_url:
                                                existing.website_url = comp.website_url
                                                existing.website_domain = comp.website_domain
                                            break
                                continue

                            seen_names.add(name_key)
                            if url_key:
                                seen_urls.add(url_key)
                            companies.append(comp)
                            new_found_in_pass += 1
                            logger.info(f"[{len(companies)}/{limit}] Found: {comp.name} ({comp.website_url or 'No website'})")
                            if progress_callback:
                                progress_callback(len(companies), limit, comp.name)
                    except Exception as e:
                        logger.debug(f"Error parsing listing card: {e}")

                # Scroll the feed container to load more items
                scroll_attempts += 1
                try:
                    feed = driver.find_element(By.XPATH, "//div[@role='feed']")
                    driver.execute_script("arguments[0].scrollTop = arguments[0].scrollHeight", feed)
                except Exception:
                    # Fallback scroll on body / window
                    driver.execute_script("window.scrollBy(0, 1200);")

                time.sleep(1.5)

                # Check if end of list reached
                if "You've reached the end of the list" in driver.page_source or "No results found" in driver.page_source:
                    logger.info("Reached end of Google Maps results.")
                    break

        except Exception as e:
            logger.error(f"Google Maps scraper error: {e}", exc_info=True)

        logger.info(f"Google Maps search completed. Total unique companies collected: {len(companies)}")
        return companies

    def _parse_card_element(self, card) -> Optional[Company]:
        """Extracts structured company information from a Google Maps listing element."""
        try:
            # 1. Company Name & Maps Link
            name = ""
            maps_url = None

            # Look for link with aria-label
            try:
                if card.tag_name == "a":
                    link_elem = card
                else:
                    link_elem = card.find_element(By.XPATH, ".//a[contains(@href, '/maps/place/')]")
                maps_url = link_elem.get_attribute("href")
                name = link_elem.get_attribute("aria-label") or link_elem.text
            except Exception:
                pass

            if not name:
                try:
                    title_elem = card.find_element(By.XPATH, ".//div[contains(@class, 'fontHeadlineSmall')] | .//div[contains(@class, 'qBF1Pd')]")
                    name = title_elem.text.strip()
                except Exception:
                    pass

            if not name:
                return None

            name = sanitize_text(name)
            norm_name = normalize_company_name(name)
            if not norm_name:
                return None

            # 2. Rating & Reviews
            rating: Optional[float] = None
            review_count: Optional[int] = None
            try:
                rating_elem = card.find_element(By.XPATH, ".//span[contains(@class, 'MW4etd')] | .//span[@aria-hidden='true' and contains(text(), '.')]")
                rating_text = rating_elem.text.strip().replace(",", ".")
                rating = float(rating_text)
            except Exception:
                pass

            try:
                reviews_elem = card.find_element(By.XPATH, ".//span[contains(@class, 'UY7F9')] | .//span[contains(text(), '(') and contains(text(), ')')]")
                reviews_text = reviews_elem.text.strip()
                match = re.search(r"\(?(\d[\d,.]*)\)?", reviews_text)
                if match:
                    review_count = int(match.group(1).replace(",", "").replace(".", ""))
            except Exception:
                pass

            # 3. Category, Address & Phone
            category: Optional[str] = None
            address: Optional[str] = None
            phone: Optional[str] = None

            try:
                sub_elems = card.find_elements(By.XPATH, ".//div[contains(@class, 'W4Efsd')]")
                for elem in sub_elems:
                    text = elem.text.strip()
                    if not text:
                        continue
                    parts = [p.strip() for p in text.split("·") if p.strip()]
                    if parts and not category:
                        category = parts[0]
                    for part in parts:
                        # Detect phone number pattern
                        if re.search(r"(\+?\d{1,4}[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}|\+?\d{10,12}", part):
                            phone = part
                        elif len(part) > 10 and not address and part != category:
                            address = part
            except Exception:
                pass

            # 4. Official Website URL
            website_url: Optional[str] = None
            website_domain: Optional[str] = None
            try:
                web_elem = card.find_element(By.XPATH, ".//a[@data-value='Website' or contains(@href, 'http') and not(contains(@href, 'google.com'))]")
                raw_href = web_elem.get_attribute("href")
                cleaned_web = clean_url(raw_href)
                if cleaned_web and not is_social_url(cleaned_web):
                    website_url = cleaned_web
                    website_domain = extract_domain(cleaned_web)
            except Exception:
                pass

            # 5. Extract Coordinates & Generate Company Key
            lat, lng = JobNormalizer.extract_coordinates_from_url(maps_url)
            comp_key = JobNormalizer.generate_company_key(name, lat, lng, website_domain)

            return Company(
                company_key=comp_key,
                name=name,
                normalized_name=norm_name,
                latitude=lat,
                longitude=lng,
                company_type=category,
                company_type_source="google_maps" if category else None,
                address=address,
                phone=phone,
                maps_url=maps_url,
                rating=rating,
                review_count=review_count,
                category=category,
                website_url=website_url,
                website_domain=website_domain,
                official_domain=website_domain,
                website=website_url,
                enrichment_status="PENDING"
            )

        except Exception as e:
            logger.debug(f"Card extraction error: {e}")
            return None
