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
        is_stopped: Optional[Callable[[], bool]] = None
    ) -> Company:
        """
        Executes full enrichment pipeline for one company.
        step_callback receives: (company, step_name, details_msg)
        """
        logger.info(f"--- Starting Enrichment for Company #{company.id}: {company.name} ---")
        company.enrichment_status = "ENRICHING"
        self.companies_repo.update_enrichment_status(company.id, "ENRICHING")

        def emit_step(step: str, details: str):
            if step_callback:
                step_callback(company, step, details)

        try:
            # -------------------------------------------------------------
            # STEP 1: Website Verification & Liveness Check
            # -------------------------------------------------------------
            emit_step("Website Checking", f"Checking website: {company.website_url or 'None'}")
            
            if not company.website_url:
                logger.info(f"No website provided for {company.name}, marking OFFLINE/NO_WEBSITE.")
                company.website_status = "OFFLINE"
                company.enrichment_status = "OFFLINE"
                self.companies_repo.upsert(company)
                emit_step("Website Checking", "No website found")
                return company

            status, resolved_url, html = self.website_checker.check_liveness(company.website_url)
            company.website_status = status
            company.website_checked_at = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
            if resolved_url:
                company.website_url = resolved_url
                company.website_domain = extract_domain(resolved_url)

            if status != "LIVE" or not html:
                logger.info(f"Website for {company.name} is {status}. Saving and skipping further enrichment.")
                company.enrichment_status = status
                self.companies_repo.upsert(company)
                emit_step("Website Checking", f"Website status: {status}")
                return company

            # If browser manager is available, open the website in Chrome so the user sees it live
            if self.browser_manager and company.website_url:
                try:
                    browser_html = self.browser_manager.navigate(company.website_url, wait_seconds=1.5)
                    if browser_html and len(browser_html) > len(html):
                        html = browser_html
                except Exception as e:
                    logger.debug(f"Live browser navigation to {company.website_url}: {e}")

            emit_step("Website Checking", f"Website is LIVE ({len(html)} bytes)")

            if is_stopped and is_stopped():
                company.enrichment_status = "STOPPED"
                self.companies_repo.upsert(company)
                return company

            # -------------------------------------------------------------
            # STEP 2: Company Type Detection & Social Profiles
            # -------------------------------------------------------------
            emit_step("Company Information", "Detecting type and social profiles")
            meta = self.website_checker.detect_company_type_and_meta(html, company.company_type)
            if meta.get("detected_type") and not company.company_type:
                company.company_type = meta["detected_type"]
                company.company_type_source = meta.get("type_source")

            # Social Profiles
            socials = extract_social_links(html)
            company.linkedin_url = socials.get("linkedin")
            company.facebook_url = socials.get("facebook")
            company.instagram_url = socials.get("instagram")
            company.twitter_url = socials.get("twitter")
            company.youtube_url = socials.get("youtube")
            company.github_url = socials.get("github")

            if is_stopped and is_stopped():
                company.enrichment_status = "STOPPED"
                self.companies_repo.upsert(company)
                return company

            # -------------------------------------------------------------
            # STEP 3: Career Page Discovery
            # -------------------------------------------------------------
            emit_step("Career Search", "Discovering career & job openings page")
            career_url, career_source = self.careers_scraper.discover_career_url(
                base_url=company.website_url,
                company_name=company.name,
                homepage_html=html
            )
            company.career_url = career_url
            company.career_url_source = career_source
            company.career_status = "FOUND" if career_url else "NOT_FOUND"

            career_html = None
            if career_url:
                emit_step("Career Search", f"Found career page: {career_url}")
            else:
                emit_step("Career Search", "No career page located")

            if is_stopped and is_stopped():
                company.enrichment_status = "STOPPED"
                self.companies_repo.upsert(company)
                return company

            # -------------------------------------------------------------
            # STEP 4: Job Openings Extraction & Relevance Scoring
            # -------------------------------------------------------------
            if career_url:
                emit_step("Job Extraction", "Extracting open positions and scoring relevance")
                target_url = career_url
                extracted_jobs = self.careers_scraper.extract_jobs(
                    career_url=target_url,
                    company_id=company.id,
                    job_matcher=job_matcher
                )

                # Persist jobs to DB with multi-source tracking
                saved_jobs_count = 0
                for job in extracted_jobs:
                    job.source = "career_portal"
                    job.normalized_title = self.normalizer.normalize_job_title(job.title)
                    job.skills = self.normalizer.extract_skills(f"{job.title} {job.description or ''} {job.requirements or ''}")
                    source_obj = JobSource(
                        job_id=job.id or 0,
                        source="career_portal",
                        source_url=job.job_url or target_url,
                        is_primary=True
                    )
                    job.sources = [source_obj]
                    self.jobs_repo.upsert(job)
                    saved_jobs_count += 1
                
                company.job_count = saved_jobs_count
                emit_step("Job Extraction", f"Extracted {saved_jobs_count} matching job(s)")
            else:
                emit_step("Job Extraction", "Skipped (no career page)")

            if is_stopped and is_stopped():
                company.enrichment_status = "STOPPED"
                self.companies_repo.upsert(company)
                return company

            # -------------------------------------------------------------
            # STEP 5: Contact Page & Email Extraction
            # -------------------------------------------------------------
            emit_step("Contact Extraction", "Extracting business emails and contact details")
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

            # Persist contacts
            saved_contacts_count = 0
            for contact in extracted_contacts:
                self.contacts_repo.upsert(contact)
                saved_contacts_count += 1

            company.email_count = saved_contacts_count
            emit_step("Contact Extraction", f"Extracted {saved_contacts_count} email(s)")

            # -------------------------------------------------------------
            # STEP 6: Mark Completed & Save
            # -------------------------------------------------------------
            company.enrichment_status = "COMPLETED"
            self.companies_repo.upsert(company)
            emit_step("Completed", f"Enrichment completed (Jobs: {company.job_count}, Emails: {company.email_count})")
            logger.info(f"Successfully finished enrichment for company: {company.name}")

        except Exception as e:
            logger.error(f"Error enriching company {company.name}: {e}", exc_info=True)
            company.enrichment_status = "FAILED"
            self.companies_repo.upsert(company)
            emit_step("Failed", f"Error: {str(e)}")

        return company
