"""
Workflow manager coordinating end-to-end multi-source search, deduplication, enrichment, and resume flows.
Executes sources in strict priority: Career Portals -> Indeed -> Unstop -> LinkedIn -> Glassdoor.
"""

from typing import List, Optional, Callable
from database.models import SearchSession, Company, Job, NormalizedJob
from database.repositories import CompaniesRepository, SearchesRepository, JobsRepository
from core.search_manager import SearchManager
from core.enrichment_manager import EnrichmentManager
from core.deduplication_service import DeduplicationService
from core.job_matcher import JobMatcher
from browser.browser_manager import BrowserManager
from scrapers.adapters import IndeedAdapter, UnstopAdapter, LinkedInAdapter, GlassdoorAdapter
from config.settings import settings
from utils.logger import get_logger

logger = get_logger("workflow_manager")


class WorkflowManager:
    """Controls overarching search, multi-source aggregation, and deduplication life cycles."""

    def __init__(
        self,
        browser_manager: Optional[BrowserManager] = None,
        companies_repo: Optional[CompaniesRepository] = None,
        searches_repo: Optional[SearchesRepository] = None,
        jobs_repo: Optional[JobsRepository] = None
    ):
        self.browser_manager = browser_manager or BrowserManager()
        self.companies_repo = companies_repo or CompaniesRepository()
        self.searches_repo = searches_repo or SearchesRepository()
        self.jobs_repo = jobs_repo or JobsRepository()

        self.search_manager = SearchManager(
            searches_repo=self.searches_repo,
            companies_repo=self.companies_repo,
            browser_manager=self.browser_manager
        )
        self.enrichment_manager = EnrichmentManager(
            companies_repo=self.companies_repo,
            browser_manager=self.browser_manager
        )
        self.dedup_service = DeduplicationService(
            companies_repo=self.companies_repo,
            jobs_repo=self.jobs_repo
        )

        # Multi-source secondary adapters
        self.indeed_adapter = IndeedAdapter()
        self.unstop_adapter = UnstopAdapter()
        self.linkedin_adapter = LinkedInAdapter()
        self.glassdoor_adapter = GlassdoorAdapter()

    def run_full_workflow(
        self,
        session: SearchSession,
        on_company_found: Optional[Callable[[Company], None]] = None,
        on_progress_update: Optional[Callable[[int, int, str], None]] = None,
        on_enrichment_step: Optional[Callable[[Company, str, str], None]] = None,
        on_company_enriched: Optional[Callable[[Company], None]] = None,
        is_stopped: Optional[Callable[[], bool]] = None
    ) -> List[Company]:
        """
        Executes priority search across:
        1. Company Discovery + Career Portals
        2. Indeed
        3. Unstop
        4. LinkedIn
        5. Glassdoor
        Followed by multi-signal deduplication, relevance scoring, and database sync.
        """
        loc_str = f"{session.city}, {session.state}, {session.country}".strip(", ")
        logger.info(f"Starting Multi-Source workflow for {loc_str} (Profession: {session.profession})")

        job_matcher = JobMatcher(
            profession=session.profession,
            custom_profession=session.custom_profession,
            threshold=settings.get_config().relevance_threshold
        )

        # =========================================================================
        # Source 1: Company Discovery & Direct Career Portals (Primary Priority)
        # =========================================================================
        if on_progress_update:
            on_progress_update(1, 5, "Searching Source 1/5: Company Career Portals...")

        companies = self.search_manager.execute_search(
            session=session,
            progress_callback=lambda current, total, name: on_progress_update(1, 5, f"[Career Portals] Found: {name}") if on_progress_update else None,
            is_stopped=is_stopped
        )

        for comp in companies:
            if on_company_found:
                on_company_found(comp)

        if session.enrich_enabled and not (is_stopped and is_stopped()):
            total_to_enrich = len(companies)
            for idx, comp in enumerate(companies, start=1):
                if is_stopped and is_stopped():
                    break
                if on_progress_update:
                    on_progress_update(1, 5, f"Enriching Portal ({idx}/{total_to_enrich}): {comp.name}")

                enriched_comp = self.enrichment_manager.enrich_company(
                    company=comp,
                    job_matcher=job_matcher,
                    step_callback=on_enrichment_step,
                    is_stopped=is_stopped,
                    enrich_career_portals=getattr(session, "enrich_career_portals", True),
                    enrich_linkedin_website=getattr(session, "enrich_linkedin_website", True)
                )
                if on_company_enriched:
                    on_company_enriched(enriched_comp)

        if is_stopped and is_stopped():
            logger.info("Workflow stopped after Career Portals phase.")
            return self.companies_repo.get_companies(search_id=session.id)

        # =========================================================================
        # Source 2: Indeed Search
        # =========================================================================
        if not (is_stopped and is_stopped()):
            if on_progress_update:
                on_progress_update(2, 5, "Searching Source 2/5: Indeed...")
            logger.info("Querying Indeed Job Source Adapter...")
            try:
                indeed_jobs = self.indeed_adapter.search_jobs(
                    profession=session.profession if session.profession != "Other" else (session.custom_profession or ""),
                    location=session.city or loc_str,
                    limit=max(10, session.result_limit)
                )
                self._ingest_multi_source_jobs(indeed_jobs, session.id, job_matcher, on_company_found, on_company_enriched)
            except Exception as e:
                logger.warning(f"Indeed aggregation error: {e}")

        # =========================================================================
        # Source 3: Unstop Search
        # =========================================================================
        if not (is_stopped and is_stopped()):
            if on_progress_update:
                on_progress_update(3, 5, "Searching Source 3/5: Unstop...")
            logger.info("Querying Unstop Job Source Adapter...")
            try:
                unstop_jobs = self.unstop_adapter.search_jobs(
                    profession=session.profession if session.profession != "Other" else (session.custom_profession or ""),
                    location=session.city or loc_str,
                    limit=max(10, session.result_limit)
                )
                self._ingest_multi_source_jobs(unstop_jobs, session.id, job_matcher, on_company_found, on_company_enriched)
            except Exception as e:
                logger.warning(f"Unstop aggregation error: {e}")

        # =========================================================================
        # Source 4: LinkedIn Search
        # =========================================================================
        if not (is_stopped and is_stopped()):
            if on_progress_update:
                on_progress_update(4, 5, "Searching Source 4/5: LinkedIn...")
            logger.info("Querying LinkedIn Job Source Adapter...")
            try:
                linkedin_jobs = self.linkedin_adapter.search_jobs(
                    profession=session.profession if session.profession != "Other" else (session.custom_profession or ""),
                    location=session.city or loc_str,
                    limit=max(10, session.result_limit)
                )
                self._ingest_multi_source_jobs(linkedin_jobs, session.id, job_matcher, on_company_found, on_company_enriched)
            except Exception as e:
                logger.warning(f"LinkedIn aggregation error: {e}")

        # =========================================================================
        # Source 5: Glassdoor Search
        # =========================================================================
        if not (is_stopped and is_stopped()):
            if on_progress_update:
                on_progress_update(5, 5, "Searching Source 5/5: Glassdoor...")
            logger.info("Querying Glassdoor Job Source Adapter...")
            try:
                glassdoor_jobs = self.glassdoor_adapter.search_jobs(
                    profession=session.profession if session.profession != "Other" else (session.custom_profession or ""),
                    location=session.city or loc_str,
                    limit=max(10, session.result_limit)
                )
                self._ingest_multi_source_jobs(glassdoor_jobs, session.id, job_matcher, on_company_found, on_company_enriched)
            except Exception as e:
                logger.warning(f"Glassdoor aggregation error: {e}")

        if on_progress_update:
            on_progress_update(5, 5, "Multi-Source aggregation and deduplication complete.")

        final_companies = self.companies_repo.get_companies(search_id=session.id)
        logger.info(f"Multi-Source workflow finished. Total companies in session: {len(final_companies)}")
        return final_companies

    def _ingest_multi_source_jobs(
        self,
        jobs: List[NormalizedJob],
        search_id: Optional[int],
        job_matcher: JobMatcher,
        on_company_found: Optional[Callable[[Company], None]] = None,
        on_company_enriched: Optional[Callable[[Company], None]] = None
    ):
        """Passes external normalized jobs through DeduplicationService and calculates relevance."""
        for norm_job in jobs:
            try:
                job, is_new_job = self.dedup_service.process_normalized_job(norm_job, search_id=search_id)
                # Compute relevance score
                score = job_matcher.score_job(job.title, job.description, job.requirements)
                if score > job.relevance_score:
                    job.relevance_score = score
                    self.jobs_repo.upsert(job)

                comp = self.companies_repo.get_by_id(job.company_id)
                if comp:
                    # Auto-enrich LinkedIn companies: extract website, phone, and scrape emails
                    if not comp.website_url and norm_job.source == "linkedin":
                        try:
                            from scrapers.linkedin_company_enricher import linkedin_enricher
                            from database.models import Contact
                            raw = norm_job.raw_data or {}
                            li_url = raw.get("company_linkedin_url")
                            res = linkedin_enricher.full_enrichment_flow(
                                company_name=comp.name,
                                company_linkedin_url=li_url,
                                location=norm_job.location
                            )
                            if res.get("website"):
                                comp.website_url = res["website"]
                                comp.website = res["website"]
                            if res.get("phone"):
                                comp.phone = res["phone"]
                            if res.get("industry") and not comp.category:
                                comp.category = res["industry"]
                            self.companies_repo.upsert(comp)

                            # Save any scraped emails
                            for em_item in res.get("emails", []):
                                self.contacts_repo.upsert(Contact(
                                    company_id=comp.id,
                                    email=em_item["email"],
                                    email_type=em_item.get("type", "General"),
                                    source_url=em_item.get("source")
                                ))
                        except Exception as enrich_err:
                            logger.debug(f"LinkedIn auto-enrichment error for {comp.name}: {enrich_err}")

                    if on_company_found:
                        on_company_found(comp)
                    if on_company_enriched:
                        on_company_enriched(comp)
            except Exception as e:
                logger.debug(f"Error ingesting job '{norm_job.job_title}' from {norm_job.source}: {e}")

    def resume_enrichment(
        self,
        profession: str,
        custom_profession: Optional[str] = None,
        search_id: Optional[int] = None,
        on_progress_update: Optional[Callable[[int, int, str], None]] = None,
        on_enrichment_step: Optional[Callable[[Company, str, str], None]] = None,
        on_company_enriched: Optional[Callable[[Company], None]] = None,
        is_stopped: Optional[Callable[[], bool]] = None
    ) -> List[Company]:
        """Resumes enrichment for companies in PENDING / STOPPED / FAILED state."""
        pending_companies = self.companies_repo.get_pending_enrichment_companies(search_id=search_id)
        if not pending_companies:
            logger.info("No pending companies to enrich.")
            return []

        logger.info(f"Resuming enrichment for {len(pending_companies)} pending companies...")
        job_matcher = JobMatcher(
            profession=profession,
            custom_profession=custom_profession,
            threshold=settings.get_config().relevance_threshold
        )

        total = len(pending_companies)
        resumed_list = []

        for idx, comp in enumerate(pending_companies, start=1):
            if is_stopped and is_stopped():
                logger.info(f"Resume workflow stopped at company #{idx} ({comp.name})")
                comp.enrichment_status = "STOPPED"
                self.companies_repo.upsert(comp)
                if on_company_enriched:
                    on_company_enriched(comp)
                break

            if on_progress_update:
                on_progress_update(idx, total, f"Enriching: {comp.name}")

            enriched = self.enrichment_manager.enrich_company(
                company=comp,
                job_matcher=job_matcher,
                step_callback=on_enrichment_step,
                is_stopped=is_stopped
            )
            resumed_list.append(enriched)

            if on_company_enriched:
                on_company_enriched(enriched)

        return resumed_list

    def run_linkedin_enrichment(
        self,
        session: SearchSession,
        on_company_found: Optional[Callable[[Company], None]] = None,
        on_progress_update: Optional[Callable[[int, int, str], None]] = None,
        on_enrichment_step: Optional[Callable[[Company, str, str], None]] = None,
        on_company_enriched: Optional[Callable[[Company], None]] = None,
        is_stopped: Optional[Callable[[], bool]] = None
    ) -> List[Company]:
        """
        Executes live browser-driven LinkedIn Job hunting and sequential per-company enrichment:
        1. Opens LinkedIn Jobs search with exact role & location filters.
        2. Captures exactly up to session.result_limit matching jobs.
        3. Sequentially enriches company LinkedIn page -> website -> emails -> career portal.
        """
        from scrapers.linkedin_jobs_hunter import LinkedInJobsHunter
        hunter = LinkedInJobsHunter(
            browser_manager=self.browser_manager,
            companies_repo=self.companies_repo,
            jobs_repo=self.jobs_repo
        )
        return hunter.hunt_and_enrich(
            session=session,
            on_company_found=on_company_found,
            on_progress_update=on_progress_update,
            on_enrichment_step=on_enrichment_step,
            on_company_enriched=on_company_enriched,
            is_stopped=is_stopped
        )

    def run_unstop_enrichment(
        self,
        session: SearchSession,
        on_company_found: Optional[Callable[[Company], None]] = None,
        on_progress_update: Optional[Callable[[int, int, str], None]] = None,
        on_enrichment_step: Optional[Callable[[Company, str, str], None]] = None,
        on_company_enriched: Optional[Callable[[Company], None]] = None,
        is_stopped: Optional[Callable[[], bool]] = None
    ) -> List[Company]:
        """Queries Unstop for internships, hiring challenges, and tech opportunities."""
        loc_str = f"{session.city}, {session.state}, {session.country}".strip(", ")
        target_prof = session.profession if session.profession != "Other" else (session.custom_profession or "Software")
        job_matcher = JobMatcher(profession=target_prof, threshold=settings.get_config().relevance_threshold)

        if on_progress_update:
            on_progress_update(1, 2, f"Querying Unstop Opportunities for '{target_prof}' in {session.city or loc_str}...")

        try:
            unstop_jobs = self.unstop_adapter.search_jobs(
                profession=target_prof,
                location=session.city or loc_str,
                limit=max(5, session.result_limit)
            )
            if on_progress_update:
                on_progress_update(2, 2, f"Ingesting {len(unstop_jobs)} opportunities from Unstop...")
            self._ingest_multi_source_jobs(unstop_jobs, session.id, job_matcher, on_company_found, on_company_enriched)
        except Exception as e:
            logger.warning(f"Unstop enrichment error: {e}")

        return self.companies_repo.get_companies(search_id=session.id)

    def run_linkedin_unstop_enrichment(
        self,
        session: SearchSession,
        on_company_found: Optional[Callable[[Company], None]] = None,
        on_progress_update: Optional[Callable[[int, int, str], None]] = None,
        on_enrichment_step: Optional[Callable[[Company, str, str], None]] = None,
        on_company_enriched: Optional[Callable[[Company], None]] = None,
        is_stopped: Optional[Callable[[], bool]] = None
    ) -> List[Company]:
        """
        Runs live browser-driven LinkedIn Job search & sequential enrichment:
        Directly opens LinkedIn in Chrome, searches for the exact job role & location,
        and enriches each captured company step-by-step.
        """
        return self.run_linkedin_enrichment(
            session=session,
            on_company_found=on_company_found,
            on_progress_update=on_progress_update,
            on_enrichment_step=on_enrichment_step,
            on_company_enriched=on_company_enriched,
            is_stopped=is_stopped
        )


