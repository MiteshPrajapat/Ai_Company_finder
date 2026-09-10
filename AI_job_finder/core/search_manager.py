"""
Search manager coordinating search parameters, Google Maps queries, and database persistence.
"""

from typing import List, Optional, Callable
from database.models import SearchSession, Company
from database.repositories import SearchesRepository, CompaniesRepository
from scrapers.google_maps import GoogleMapsScraper
from browser.browser_manager import BrowserManager
from utils.logger import get_logger

logger = get_logger("search_manager")


class SearchManager:
    """Manages the initial company discovery phase via Google Maps."""

    def __init__(
        self,
        searches_repo: Optional[SearchesRepository] = None,
        companies_repo: Optional[CompaniesRepository] = None,
        browser_manager: Optional[BrowserManager] = None
    ):
        self.searches_repo = searches_repo or SearchesRepository()
        self.companies_repo = companies_repo or CompaniesRepository()
        self.browser_manager = browser_manager or BrowserManager()
        self.maps_scraper = GoogleMapsScraper(browser_manager=self.browser_manager)

    def execute_search(
        self,
        session: SearchSession,
        progress_callback: Optional[Callable[[int, int, str], None]] = None,
        is_stopped: Optional[Callable[[], bool]] = None
    ) -> List[Company]:
        """
        Executes Google Maps company search, stores session, and persists discovered companies.
        """
        # 1. Create search session in DB
        session_id = self.searches_repo.create(session)
        logger.info(f"Initialized Search Session ID #{session_id}")

        # 2. Build search query
        company_type = session.custom_company_type if session.company_type == "Other" and session.custom_company_type else session.company_type
        query = self.maps_scraper.build_search_query(
            city=session.city,
            state=session.state,
            country=session.country,
            company_type=company_type
        )

        # 3. Perform Google Maps Scraping
        self.searches_repo.update_status(session_id, "RUNNING")
        companies = self.maps_scraper.search_companies(
            query=query,
            limit=session.result_limit,
            progress_callback=progress_callback,
            is_stopped=is_stopped
        )

        # 4. Save discovered companies to DB
        persisted_companies: List[Company] = []
        for comp in companies:
            comp.search_id = session_id
            comp.id = self.companies_repo.upsert(comp)
            persisted_companies.append(comp)

        status = "STOPPED" if (is_stopped and is_stopped()) else "COMPLETED"
        self.searches_repo.update_status(session_id, status)
        logger.info(f"Search session #{session_id} finished with status '{status}'. Total companies: {len(persisted_companies)}")
        return persisted_companies
