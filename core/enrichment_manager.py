"""
Company enrichment manager orchestrating website verification, career discovery,
job extraction & scoring, contact extraction, and database persistence.
"""

from datetime import datetime
from typing import Optional, Callable, Dict, Any, List
from database.models import Company, Job, Contact, JobSource
from database.repositories import CompaniesRepository, JobsRepository, ContactsRepository
from scrapers.website import WebsiteChecker
from scrapers.careers import CareersScraper
from scrapers.contacts import ContactsScraper
from scrapers.social import extract_social_links
from scrapers.linkedin_company_enricher import linkedin_enricher
from core.job_matcher import JobMatcher
from core.normalizer import JobNormalizer
from utils.logger import get_logger
from utils.url_utils import clean_url, extract_domain

logger = get_logger("enrichment_manager")


class EnrichmentManager:
    """Orchestrates comprehensive enrichment for a single company."""

    def __init__(
        self,
        companies_repo: Optional[CompaniesRepository] = None,
        jobs_repo: Optional[JobsRepository] = None,
        contacts_repo: Optional[ContactsRepository] = None,
        browser_manager: Optional[Any] = None
    ):
        self.companies_repo = companies_repo or CompaniesRepository()
        self.jobs_repo = jobs_repo or JobsRepository()
        self.contacts_repo = contacts_repo or ContactsRepository()
        self.browser_manager = browser_manager
        self.normalizer = JobNormalizer()

        self.website_checker = WebsiteChecker()
        self.careers_scraper = CareersScraper(browser_manager=self.browser_manager)
        self.contacts_scraper = ContactsScraper()

    def enrich_company(
        self,
        company: Company,
        job_matcher: JobMatcher,
        step_callback: Optional[Callable[[Company, str, str], None]] = None,
        is_stopped: Optional[Callable[[], bool]] = None,
        enrich_career_portals: bool = True,
        enrich_linkedin_website: bool = True
    ) -> Company:
        """
        Executes granular enrichment pipeline for one company.
        Supports separate flags for Career Portal discovery and LinkedIn / Website contact enrichment.
        step_callback receives: (company, step_name, details_msg)
        """
        logger.info(f"--- Starting Enrichment for Company #{company.id}: {company.name} (Career: {enrich_career_portals}, LinkedIn/Web: {enrich_linkedin_website}) ---")
        company.enrichment_status = "ENRICHING"
        self.companies_repo.update_enrichment_status(company.id, "ENRICHING")

        def emit_step(step: str, details: str):
            if step_callback:
                step_callback(company, step, details)

        try:
            # -------------------------------------------------------------
            # STEP 1: LinkedIn Discovery & Website Fallback
            # -------------------------------------------------------------
            if enrich_linkedin_website:
                emit_step("LinkedIn & Website Enrich", f"Searching & Opening LinkedIn profile for '{company.name}'...")
                driver = self.browser_manager.get_driver() if (self.browser_manager and hasattr(self.browser_manager, "get_driver")) else None
                li_res = linkedin_enricher.full_enrichment_flow(
                    company_name=company.name,
                    company_linkedin_url=company.linkedin_url,
                    location=company.city or company.address,
                    driver=driver
                )
                if li_res.get("linkedin_url") and not company.linkedin_url:
                    company.linkedin_url = li_res["linkedin_url"]
                    emit_step("LinkedIn & Website Enrich", f"Linked profile: {company.linkedin_url}")
                if li_res.get("website") and not company.website_url:
                    company.website_url = li_res["website"]
                    company.website_domain = extract_domain(li_res["website"])
                    emit_step("LinkedIn & Website Enrich", f"Discovered official website: {company.website_url}")
                if li_res.get("phone") and not company.phone:
                    company.phone = li_res["phone"]
                    emit_step("LinkedIn & Website Enrich", f"Discovered phone: {company.phone}")
                if li_res.get("company_size") and not company.category:
                    company.category = li_res["company_size"]
                if li_res.get("industry") and not company.company_type:
                    company.company_type = li_res["industry"]

            # Website Liveness Check (if website exists)
            html = ""
            if company.website_url:
                emit_step("Website Checking", f"Verifying website: {company.website_url}")
                status, resolved_url, page_html = self.website_checker.check_liveness(company.website_url)
                company.website_status = status
                company.website_checked_at = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
                if resolved_url:
                    company.website_url = resolved_url
                    company.website_domain = extract_domain(resolved_url)
                html = page_html or ""

                if status == "LIVE" and html:
                    # Open in visible Chrome if browser manager exists
                    if self.browser_manager and company.website_url:
                        try:
                            browser_html = self.browser_manager.navigate(company.website_url, wait_seconds=1.5)
                            if browser_html and len(browser_html) > len(html):
                                html = browser_html
                        except Exception as e:
                            logger.debug(f"Live browser navigation to {company.website_url}: {e}")
                    emit_step("Website Checking", f"Website is LIVE ({len(html)} bytes)")
                else:
                    emit_step("Website Checking", f"Website status: {status}")
            else:
                emit_step("Website Checking", f"No website available for '{company.name}'")

            if is_stopped and is_stopped():
                company.enrichment_status = "STOPPED"
                self.companies_repo.upsert(company)
                return company

            # -------------------------------------------------------------
            # STEP 2: Company Type Detection & Social Profiles
            # -------------------------------------------------------------
            if html:
                meta = self.website_checker.detect_company_type_and_meta(html, company.company_type)
                if meta.get("detected_type") and not company.company_type:
                    company.company_type = meta["detected_type"]
                    company.company_type_source = meta.get("type_source")

                socials = extract_social_links(html)
                if socials.get("linkedin") and not company.linkedin_url:
                    company.linkedin_url = socials["linkedin"]
                if socials.get("facebook") and not company.facebook_url:
                    company.facebook_url = socials["facebook"]
                if socials.get("instagram") and not company.instagram_url:
                    company.instagram_url = socials["instagram"]
                if socials.get("twitter") and not company.twitter_url:
                    company.twitter_url = socials["twitter"]
                if socials.get("youtube") and not company.youtube_url:
                    company.youtube_url = socials["youtube"]
                if socials.get("github") and not company.github_url:
                    company.github_url = socials["github"]

            # LinkedIn Profile Enrichment (About Tab details)
            if enrich_linkedin_website and company.linkedin_url and (not company.phone or not company.category):
                emit_step("LinkedIn & Website Enrich", f"Checking LinkedIn About tab: {company.linkedin_url}")
                driver = self.browser_manager.get_driver() if (self.browser_manager and hasattr(self.browser_manager, "get_driver")) else None
                li_data = linkedin_enricher.enrich_from_linkedin_about(company.name, company.linkedin_url, driver=driver)
                if li_data.get("phone") and not company.phone:
                    company.phone = li_data["phone"]
                    emit_step("LinkedIn & Website Enrich", f"Found phone: {company.phone}")
                if li_data.get("company_size") and not company.category:
                    company.category = li_data["company_size"]
                if li_data.get("industry") and not company.company_type:
                    company.company_type = li_data["industry"]

            if is_stopped and is_stopped():
                company.enrichment_status = "STOPPED"
                self.companies_repo.upsert(company)
                return company

            # -------------------------------------------------------------
            # STEP 3 & 4: Career Portal Discovery & Job Openings (if enabled)
            # -------------------------------------------------------------
            career_html = None
            if enrich_career_portals:
                if company.website_url:
                    emit_step("Career Portal Enrich", f"Discovering ATS & Career Portal for '{company.name}'...")
                    career_url, career_source = self.careers_scraper.discover_career_url(
                        base_url=company.website_url,
                        company_name=company.name,
                        homepage_html=html
                    )
                    company.career_url = career_url
                    company.career_url_source = career_source
                    company.career_status = "FOUND" if career_url else "NOT_FOUND"

                    if career_url:
                        emit_step("Career Portal Enrich", f"Found Career Portal: {career_url} ({career_source})")
                        emit_step("Career Portal Enrich", "Extracting active job postings and calculating relevance scores...")
                        extracted_jobs = self.careers_scraper.extract_jobs(
                            career_url=career_url,
                            company_id=company.id,
                            job_matcher=job_matcher
                        )
                        saved_jobs_count = 0
                        for job in extracted_jobs:
                            job.source = "career_portal"
                            job.normalized_title = self.normalizer.normalize_job_title(job.title)
                            job.skills = self.normalizer.extract_skills(f"{job.title} {job.description or ''} {job.requirements or ''}")
                            source_obj = JobSource(
                                job_id=job.id or 0,
                                source="career_portal",
                                source_url=job.job_url or career_url,
                                is_primary=True
                            )
                            job.sources = [source_obj]
                            self.jobs_repo.upsert(job)
                            saved_jobs_count += 1
                        company.job_count = saved_jobs_count
                        emit_step("Career Portal Enrich", f"Extracted {saved_jobs_count} matching job opening(s)")
                    else:
                        emit_step("Career Portal Enrich", "No direct career portal located on website")
                else:
                    emit_step("Career Portal Enrich", "Skipped career search (no website available)")
            else:
                emit_step("Career Portal Enrich", "Career Portal Discovery skipped by user filter")

            if is_stopped and is_stopped():
                company.enrichment_status = "STOPPED"
                self.companies_repo.upsert(company)
                return company

            # -------------------------------------------------------------
            # STEP 5: Website Contacts & HR Hunter (if enabled)
            # -------------------------------------------------------------
            if enrich_linkedin_website:
                extracted_contacts = []
                if company.website_url:
                    emit_step("LinkedIn & Website Enrich", f"Crawling website /contact and /careers for corporate emails on {company.website_url}...")
                    contact_page_url = self.contacts_scraper.discover_contact_url(
                        base_url=company.website_url,
                        homepage_html=html
                    )
                    extracted_contacts = self.contacts_scraper.extract_contacts(
                        company_id=company.id,
                        base_url=company.website_url,
                        homepage_html=html,
                        contact_page_url=contact_page_url,
                        career_page_html=career_html
                    )
                    emit_step("LinkedIn & Website Enrich", f"Found {len(extracted_contacts)} email(s) from website crawl")

                # If no contacts or few contacts discovered, run Smart OSINT HR Hunter
                if len(extracted_contacts) < 2:
                    emit_step("LinkedIn & Website Enrich", f"Hunting recruiter & HR emails for '{company.name}' via OSINT dorks...")
                    try:
                        from core.hr_email_hunter import hr_hunter
                        hunt_res = hr_hunter.hunt_hr_contacts(company.name, company.website_domain or company.website_url)
                        for cand in hunt_res.get("email_candidates", [])[:3]:
                            em = cand.get("email")
                            if em and not any(c.email.lower() == em.lower() for c in extracted_contacts):
                                extracted_contacts.append(Contact(
                                    company_id=company.id,
                                    email=em,
                                    email_type="hr",
                                    source_url="OSINT Recruiter Dork"
                                ))
                                emit_step("LinkedIn & Website Enrich", f"🎯 Discovered HR email: {em}")
                    except Exception as e:
                        logger.debug(f"OSINT hunter fallback note for {company.name}: {e}")

                # Persist contacts
                saved_contacts_count = 0
                for contact in extracted_contacts:
                    self.contacts_repo.upsert(contact)
                    saved_contacts_count += 1
                company.email_count = saved_contacts_count
                emit_step("LinkedIn & Website Enrich", f"Successfully saved {saved_contacts_count} verified email contact(s)")
            else:
                emit_step("LinkedIn & Website Enrich", "LinkedIn & Website Contact extraction skipped by user filter")

            # -------------------------------------------------------------
            # STEP 6: Mark Completed & Save
            # -------------------------------------------------------------
            company.enrichment_status = "COMPLETED"
            self.companies_repo.upsert(company)
            emit_step("Completed", f"Enrichment completed (Jobs: {company.job_count}, Contacts: {company.email_count})")
            logger.info(f"Successfully completed enrichment for {company.name}")

        except Exception as e:
            logger.error(f"Error enriching company {company.name}: {e}", exc_info=True)
            company.enrichment_status = "FAILED"
            self.companies_repo.upsert(company)
            emit_step("Failed", f"Error: {str(e)}")

        return company
