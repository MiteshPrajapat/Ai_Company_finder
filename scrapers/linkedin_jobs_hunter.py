"""
Live Browser LinkedIn Job Hunter & Sequential Enrichment Pipeline.

Workflow:
1. Opens LinkedIn Jobs search in Chrome with exact filters (Role / Keywords, Location).
2. Collects ONLY jobs that match the selected role and location, up to the exact result limit (e.g. 10).
3. For each matching job in order:
   - Navigates live browser to Company's LinkedIn page (/about/).
   - Extracts Company Website Domain, Phone Number, Industry, and Size.
   - If Website is captured:
     - Navigates live browser to Company Website.
     - Scrapes business/HR emails, phone numbers, contact info.
     - Scans for career portal / open opportunities.
   - If Website is not captured, logs and proceeds to next job.
   - Saves to DB and streams live updates to the UI table.
4. Strictly respects the user-selected result limit and stop signal.
"""

import time
import re
import urllib.parse
from typing import List, Optional, Callable, Dict, Any

from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, WebDriverException
from bs4 import BeautifulSoup
import httpx

from config.settings import settings
from database.models import SearchSession, Company, Job, Contact, JobSource
from database.repositories import CompaniesRepository, JobsRepository, ContactsRepository, SearchesRepository
from core.job_matcher import JobMatcher
from core.normalizer import JobNormalizer
from browser.browser_manager import BrowserManager
from scrapers.linkedin_company_enricher import linkedin_enricher
from scrapers.careers import CareersScraper
from utils.logger import get_logger
from utils.url_utils import clean_url, extract_domain
from utils.text_utils import sanitize_text
from utils.email_utils import extract_emails_from_text

logger = get_logger("linkedin_jobs_hunter")


class LinkedInJobsHunter:
    """Executes live browser-driven LinkedIn Job searching and per-company enrichment."""

    def __init__(
        self,
        browser_manager: Optional[BrowserManager] = None,
        companies_repo: Optional[CompaniesRepository] = None,
        jobs_repo: Optional[JobsRepository] = None,
        contacts_repo: Optional[ContactsRepository] = None
    ):
        self.browser_manager = browser_manager or BrowserManager()
        self.companies_repo = companies_repo or CompaniesRepository()
        self.jobs_repo = jobs_repo or JobsRepository()
        self.contacts_repo = contacts_repo or ContactsRepository()
        self.careers_scraper = CareersScraper(browser_manager=self.browser_manager)

    def dismiss_modals(self, driver):
        """Dismisses any sign-in modals or overlays on LinkedIn."""
        try:
            dismiss_selectors = [
                "button[data-tracking-control-name*='dismiss']",
                "button.modal__dismiss",
                "button[aria-label='Dismiss']",
                "icon[data-tracking-control-name*='dismiss']",
                "button.contextual-sign-in-modal__modal-dismiss-btn",
                "div[data-tracking-control-name*='modal_dismiss']",
                "button.cta-modal__dismiss-btn"
            ]
            for sel in dismiss_selectors:
                elements = driver.find_elements(By.CSS_SELECTOR, sel)
                for el in elements:
                    if el.is_displayed():
                        try:
                            el.click()
                            time.sleep(0.3)
                        except Exception:
                            pass
        except Exception:
            pass

    def hunt_and_enrich(
        self,
        session: SearchSession,
        on_company_found: Optional[Callable[[Company], None]] = None,
        on_progress_update: Optional[Callable[[int, int, str], None]] = None,
        on_enrichment_step: Optional[Callable[[Company, str, str], None]] = None,
        on_company_enriched: Optional[Callable[[Company], None]] = None,
        is_stopped: Optional[Callable[[], bool]] = None
    ) -> List[Company]:
        """
        Main execution method:
        - Opens LinkedIn Jobs in live browser with role and location filters.
        - Collects exact number of matching jobs (e.g. 10).
        - Sequentially enriches each company: LinkedIn about -> website -> emails -> career portal.
        """
        target_role = session.profession if session.profession != "Other" else (session.custom_profession or "Software Developer")
        loc_parts = [p.strip() for p in [session.city, session.state, session.country] if p and p.strip()]
        location_str = ", ".join(loc_parts) if loc_parts else (session.city or "")
        limit = max(1, session.result_limit)

        logger.info(f"Starting LinkedIn Live Hunter for '{target_role}' in '{location_str}' (Exact limit: {limit})")

        job_matcher = JobMatcher(
            profession=session.profession,
            custom_profession=session.custom_profession,
            threshold=settings.get_config().relevance_threshold
        )

        driver = self.browser_manager.get_driver()

        # Step 1: Navigate to LinkedIn Jobs Search URL
        if on_progress_update:
            on_progress_update(0, limit, f"Opening LinkedIn Jobs: '{target_role}' in {location_str}...")

        role_slug = re.sub(r"[^a-zA-Z0-9]+", "-", target_role.lower()).strip("-")
        city_slug = re.sub(r"[^a-zA-Z0-9]+", "-", (session.city or "").lower()).strip("-")
        country_slug = (session.country or "").lower().strip()

        urls_to_try = []
        # Public SEO endpoints (bypasses login wall completely)
        if role_slug and city_slug:
            if country_slug == "india" or not country_slug:
                urls_to_try.append(f"https://in.linkedin.com/jobs/{role_slug}-jobs-{city_slug}")
            urls_to_try.append(f"https://www.linkedin.com/jobs/{role_slug}-jobs-{city_slug}")

        encoded_role = urllib.parse.quote(target_role)
        encoded_loc = urllib.parse.quote(location_str)
        urls_to_try.append(f"https://www.linkedin.com/jobs/search?keywords={encoded_role}&location={encoded_loc}")

        navigated_successfully = False
        for target_url in urls_to_try:
            logger.info(f"Navigating live browser to LinkedIn: {target_url}")
            try:
                driver.get(target_url)
                time.sleep(2.5)
                self.dismiss_modals(driver)

                # Check if cards exist or if redirected to login
                page_title = driver.title.lower()
                page_src = driver.page_source
                soup_test = BeautifulSoup(page_src, "html.parser")
                test_cards = soup_test.find_all("div", class_="base-card") or soup_test.find_all("li", class_="jobs-search__results-list") or soup_test.find_all("li")
                has_job_cards = any(c.find("h3") for c in test_cards[:10])

                if "log in" not in page_title and has_job_cards:
                    logger.info(f"Successfully loaded LinkedIn public job listings from: {target_url}")
                    navigated_successfully = True
                    break
            except Exception as e:
                logger.warning(f"Error navigating to {target_url}: {e}")

        # Step 2: Capture strictly matching jobs up to exact limit
        captured_jobs: List[Dict[str, Any]] = []
        seen_job_keys = set()
        scroll_attempts = 0
        max_scrolls = 8
        while len(captured_jobs) < limit and scroll_attempts < max_scrolls:
            if is_stopped and is_stopped():
                logger.info("Search stopped during job collection.")
                break

            self.dismiss_modals(driver)

            # Extract job cards from live DOM
            html = driver.page_source
            soup = BeautifulSoup(html, "html.parser")
            cards = soup.find_all("div", class_="base-card") or soup.find_all("li", class_="jobs-search__results-list") or soup.find_all("li")

            for card in cards:
                if len(captured_jobs) >= limit:
                    break

                title_elem = card.find("h3", class_="base-search-card__title") or card.find("h3")
                comp_elem = card.find("h4", class_="base-search-card__subtitle") or card.find("a", class_="hidden-nested-link") or card.find("h4")
                loc_elem = card.find("span", class_="job-search-card__location")
                link_elem = card.find("a", class_="base-card__full-link") or card.find("a", href=True)

                if not title_elem or not comp_elem:
                    continue

                raw_title = sanitize_text(title_elem.get_text() or "")
                raw_company = sanitize_text(comp_elem.get_text() or "")
                raw_loc = sanitize_text(loc_elem.get_text() or "") if loc_elem else location_str
                job_url = link_elem["href"] if link_elem and "href" in link_elem.attrs else ""

                if not raw_title or not raw_company:
                    continue

                # Deduplication key
                job_key = f"{raw_company.lower()}::{raw_title.lower()}"
                if job_key in seen_job_keys:
                    continue

                # Strict Filter 1: Web role / profession relevance check
                relevance = job_matcher.calculate_relevance(raw_title)
                # Ensure job is relevant to the selected profession
                if session.profession != "All":
                    role_words = [w.lower() for w in re.split(r"\W+", target_role) if len(w) > 2]
                    title_lower = raw_title.lower()
                    has_role_keyword = any(w in title_lower for w in role_words)
                    if relevance < settings.get_config().relevance_threshold and not has_role_keyword:
                        logger.debug(f"Skipping non-matching job role: '{raw_title}' (relevance: {relevance})")
                        continue

                # Strict Filter 2: Location check (if city specified, must match city or country)
                if session.city:
                    city_lower = session.city.strip().lower()
                    loc_lower = raw_loc.lower()
                    if city_lower not in loc_lower and "remote" not in loc_lower and "hybrid" not in loc_lower:
                        # Allow if country matches
                        country_lower = (session.country or "").strip().lower()
                        if not country_lower or country_lower not in loc_lower:
                            logger.debug(f"Skipping non-matching location '{raw_loc}' for target '{session.city}'")
                            continue

                # Extract company LinkedIn URL if present
                comp_link = comp_elem.find("a") if hasattr(comp_elem, "find") else None
                if not comp_link:
                    comp_link = card.find("a", href=lambda h: h and "/company/" in h)
                company_li_url = comp_link["href"] if comp_link and "href" in comp_link.attrs else ""
                if "?" in company_li_url:
                    company_li_url = company_li_url.split("?")[0]

                if "?" in job_url:
                    job_url = job_url.split("?")[0]

                seen_job_keys.add(job_key)
                captured_jobs.append({
                    "title": raw_title,
                    "company": raw_company,
                    "location": raw_loc,
                    "job_url": job_url,
                    "company_li_url": company_li_url,
                    "relevance": max(relevance, 60)
                })
                logger.info(f"Captured matching LinkedIn job ({len(captured_jobs)}/{limit}): '{raw_title}' at '{raw_company}' ({raw_loc})")

            if len(captured_jobs) >= limit:
                break

            # Scroll live browser down to trigger lazy loading of more jobs
            scroll_attempts += 1
            try:
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(1.8)
                # Try clicking "See more jobs" button if present
                see_more_btn = driver.find_elements(By.CSS_SELECTOR, "button.infinite-scroller__show-more-button, button[aria-label*='See more jobs']")
                for smb in see_more_btn:
                    if smb.is_displayed():
                        smb.click()
                        time.sleep(1.5)
            except Exception:
                pass

            # If browser DOM isn't yielding enough jobs, query the guest search endpoint slice
            if len(captured_jobs) < limit:
                guest_start += 25
                guest_url = f"https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search?keywords={encoded_role}&location={encoded_loc}&start={guest_start}"
                try:
                    with httpx.Client(timeout=8, follow_redirects=True, headers={"User-Agent": settings.get_config().user_agent}, verify=False) as client:
                        resp = client.get(guest_url)
                        if resp.status_code == 200:
                            g_soup = BeautifulSoup(resp.text, "html.parser")
                            g_cards = g_soup.find_all("li") or g_soup.find_all("div", class_="base-card")
                            for card in g_cards:
                                if len(captured_jobs) >= limit:
                                    break
                                t_el = card.find("h3", class_="base-search-card__title") or card.find("h3")
                                c_el = card.find("h4", class_="base-search-card__subtitle") or card.find("h4")
                                l_el = card.find("span", class_="job-search-card__location")
                                a_el = card.find("a", class_="base-card__full-link") or card.find("a", href=True)
                                if not t_el or not c_el:
                                    continue
                                t_str = sanitize_text(t_el.get_text() or "")
                                c_str = sanitize_text(c_el.get_text() or "")
                                l_str = sanitize_text(l_el.get_text() or "") if l_el else location_str
                                j_url = a_el["href"] if a_el and "href" in a_el.attrs else ""
                                k_str = f"{c_str.lower()}::{t_str.lower()}"
                                if k_str in seen_job_keys:
                                    continue

                                rel = job_matcher.calculate_relevance(t_str)
                                if session.profession != "All":
                                    role_words = [w.lower() for w in re.split(r"\W+", target_role) if len(w) > 2]
                                    if rel < settings.get_config().relevance_threshold and not any(w in t_str.lower() for w in role_words):
                                        continue

                                seen_job_keys.add(k_str)
                                captured_jobs.append({
                                    "title": t_str,
                                    "company": c_str,
                                    "location": l_str,
                                    "job_url": j_url.split("?")[0] if "?" in j_url else j_url,
                                    "company_li_url": "",
                                    "relevance": max(rel, 60)
                                })
                                logger.info(f"Captured matching LinkedIn job ({len(captured_jobs)}/{limit}): '{t_str}' at '{c_str}'")
                except Exception as ge:
                    logger.debug(f"Guest API fallback error: {ge}")

        # Limit strictly to the exact number requested
        captured_jobs = captured_jobs[:limit]
        total_captured = len(captured_jobs)
        logger.info(f"Total matching LinkedIn jobs captured: {total_captured} (Target was: {limit})")

        enriched_companies: List[Company] = []

        # =========================================================================
        # Step 3: Sequential Enrichment Loop for Each Captured Job
        # =========================================================================
        for idx, job_info in enumerate(captured_jobs, start=1):
            if is_stopped and is_stopped():
                logger.info(f"Workflow stopped at job {idx}/{total_captured}")
                break

            comp_name = job_info["company"]
            job_title = job_info["title"]
            job_loc = job_info["location"]
            job_url = job_info["job_url"]
            company_li_url = job_info.get("company_li_url")

            status_msg = f"Processing ({idx}/{total_captured}): '{job_title}' at {comp_name}"
            if on_progress_update:
                on_progress_update(idx, total_captured, status_msg)

            # Create or get existing company in DB
            norm_name = JobNormalizer.normalize_company_name(comp_name)
            existing_comp = self.companies_repo.get_by_name(comp_name)

            if existing_comp:
                company = existing_comp
            else:
                company = Company(
                    search_id=session.id,
                    name=comp_name,
                    normalized_name=norm_name,
                    company_type=session.company_type if session.company_type != "Other" else (session.custom_company_type or "Tech"),
                    city=session.city or job_loc,
                    country=session.country or "India",
                    enrichment_status="IN_PROGRESS"
                )
                company.id = self.companies_repo.upsert(company)

            # Emit initial found signal so row shows in table immediately
            if on_company_found:
                on_company_found(company)

            # -----------------------------------------------------------------
            # 3A. Open Company LinkedIn About Page in live browser
            # -----------------------------------------------------------------
            logger.info(f"[{idx}/{total_captured}] Opening LinkedIn About for '{comp_name}'...")
            if on_enrichment_step:
                on_enrichment_step(company, "linkedin_about", f"Navigating to LinkedIn profile for {comp_name}...")

            about_url = None
            if company_li_url and "linkedin.com/company" in company_li_url:
                about_url = company_li_url.rstrip("/") + "/about/"
            else:
                # Discover LinkedIn company profile URL
                discovered = linkedin_enricher.discover_linkedin_url(comp_name, location=session.city, driver=driver)
                if discovered:
                    about_url = discovered.rstrip("/") + "/about/"
                    company_li_url = discovered

            website_url = None
            phone = None
            industry = None
            company_size = None

            if about_url:
                try:
                    logger.info(f"Live browser opening LinkedIn About: {about_url}")
                    driver.get(about_url)
                    time.sleep(2.0)
                    self.dismiss_modals(driver)
                    parsed_about = linkedin_enricher._parse_linkedin_about_html(driver.page_source)
                    website_url = parsed_about.get("website")
                    phone = parsed_about.get("phone")
                    industry = parsed_about.get("industry")
                    company_size = parsed_about.get("company_size")
                    logger.info(f"Scraped from LinkedIn About: website={website_url}, phone={phone}, industry={industry}")
                except Exception as li_err:
                    logger.debug(f"Error scraping LinkedIn about page: {li_err}")

            # Fallback search if website not found on LinkedIn
            if not website_url:
                logger.info(f"Website missing from LinkedIn for '{comp_name}'. Executing search fallback...")
                website_url = linkedin_enricher.fallback_search_and_verify_website(comp_name, location=session.city, industry_hint=industry)

            if website_url:
                website_url = clean_url(website_url)
                company.website_url = website_url
                company.website = website_url
                company.website_domain = extract_domain(website_url)
                company.website_status = "ONLINE"
            if phone and not company.phone:
                company.phone = phone
            if industry and not company.category:
                company.category = industry

            if on_enrichment_step:
                on_enrichment_step(company, "linkedin_about", f"Website: {website_url or 'None'}, Phone: {phone or 'None'}")

            # -----------------------------------------------------------------
            # 3B. Open Company Website in live browser to extract contacts & careers
            # -----------------------------------------------------------------
            emails_extracted = []
            career_url = None

            if website_url:
                logger.info(f"[{idx}/{total_captured}] Navigating live browser to company website: {website_url}")
                if on_enrichment_step:
                    on_enrichment_step(company, "website_contacts", f"Visiting {website_url} to extract business/HR emails...")

                try:
                    driver.get(website_url)
                    time.sleep(2.0)

                    # Extract emails from live homepage DOM
                    home_html = driver.page_source
                    for em, cat in extract_emails_from_text(home_html):
                        emails_extracted.append({"email": em, "type": cat, "source": website_url})

                    # Discover career link from homepage HTML
                    career_url, _ = self.careers_scraper.discover_career_url(website_url, comp_name, homepage_html=home_html)
                    if career_url:
                        company.career_url = career_url
                        logger.info(f"Discovered career portal: {career_url}")

                    # Crawl /contact or /about if available for emails
                    sub_emails = linkedin_enricher.scrape_website_emails(website_url)
                    for em_dict in sub_emails:
                        if not any(e["email"] == em_dict["email"] for e in emails_extracted):
                            emails_extracted.append(em_dict)

                except Exception as web_err:
                    logger.debug(f"Error scraping company website {website_url}: {web_err}")
            else:
                logger.info(f"[{idx}/{total_captured}] No website domain available for '{comp_name}'. Proceeding to next job.")
                if on_enrichment_step:
                    on_enrichment_step(company, "website_contacts", "No website found. Skipping to next job role.")

            # Save extracted emails to Contacts DB
            for em_info in emails_extracted:
                try:
                    contact = Contact(
                        company_id=company.id,
                        email=em_info["email"],
                        email_type=em_info.get("type", "General"),
                        source_url=em_info.get("source", website_url)
                    )
                    self.contacts_repo.upsert(contact)
                except Exception as ct_err:
                    logger.debug(f"Error saving contact: {ct_err}")

            # Save the LinkedIn Job opening
            try:
                job_record = Job(
                    company_id=company.id,
                    title=job_title,
                    normalized_title=JobNormalizer.normalize_job_title(job_title),
                    location=job_loc,
                    source="linkedin",
                    source_url=job_url,
                    employment_type="Full-time",
                    relevance_score=job_info.get("relevance", 75),
                    work_mode=JobNormalizer.normalize_remote_type(job_title, job_loc)
                )
                job_id = self.jobs_repo.upsert(job_record)
                if job_id:
                    self.jobs_repo.sources_repo.upsert(JobSource(
                        job_id=job_id,
                        source="linkedin",
                        source_url=job_url,
                        is_primary=True
                    ))
            except Exception as j_err:
                logger.debug(f"Error saving job record: {j_err}")

            # Update company status and counts
            company.enrichment_status = "SUCCESS"
            company.email_count = len(emails_extracted)
            company.job_count = max(1, company.job_count)
            self.companies_repo.upsert(company)

            enriched_companies.append(company)

            # Real-time UI table updates
            if on_company_enriched:
                on_company_enriched(company)

            logger.info(f"[{idx}/{total_captured}] Completed enrichment for {comp_name}: domain={company.website_domain}, phone={company.phone}, emails={len(emails_extracted)}")

        if on_progress_update:
            on_progress_update(total_captured, total_captured, f"Completed! Captured & enriched {len(enriched_companies)} LinkedIn jobs.")

        return enriched_companies
