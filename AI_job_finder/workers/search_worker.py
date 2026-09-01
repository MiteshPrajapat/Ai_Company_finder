"""
Background QThread worker for executing searches and enrichment flows without blocking the UI.
"""

from PyQt6.QtCore import QThread, pyqtSignal
from database.models import SearchSession, Company
from core.workflow_manager import WorkflowManager
from browser.browser_manager import BrowserManager
from config.settings import settings
from utils.logger import get_logger

logger = get_logger("search_worker")


class SearchWorkflowWorker(QThread):
    """
    Background worker thread running the complete Search + Enrichment lifecycle.
    Keeps the PyQt6 UI completely responsive.
    """
    company_found = pyqtSignal(Company)
    company_updated = pyqtSignal(Company)
    progress_updated = pyqtSignal(int, int, str)  # (current, total, status_text)
    step_updated = pyqtSignal(Company, str, str)  # (company, step_name, details)
    workflow_finished = pyqtSignal(list)
    error_occurred = pyqtSignal(str)

    def __init__(self, session: SearchSession, is_resume: bool = False, parent=None):
        super().__init__(parent)
        self.session = session
        self.is_resume = is_resume
        self._is_stopped = False
        # If Auto Browser is checked in the UI or headless is configured False, show the browser on screen
        is_headless = not session.auto_browser if session else settings.get_config().headless
        self.browser_manager = BrowserManager(headless=is_headless)
        self.workflow_manager = WorkflowManager(browser_manager=self.browser_manager)

    def stop(self):
        """Requests graceful thread cancellation."""
        logger.info("Cancellation requested for worker thread.")
        self._is_stopped = True
        # Close browser to unblock any pending navigation
        if self.browser_manager:
            self.browser_manager.close()

    def run(self):
        """Worker execution entry point."""
        try:
            if self.is_resume:
                results = self.workflow_manager.resume_enrichment(
                    profession=self.session.profession,
                    custom_profession=self.session.custom_profession,
                    search_id=self.session.id,
                    on_progress_update=lambda cur, tot, msg: self.progress_updated.emit(cur, tot, msg),
                    on_enrichment_step=lambda comp, step, desc: self.step_updated.emit(comp, step, desc),
                    on_company_enriched=lambda comp: self.company_updated.emit(comp),
                    is_stopped=lambda: self._is_stopped
                )
            else:
                results = self.workflow_manager.run_full_workflow(
                    session=self.session,
                    on_company_found=lambda comp: self.company_found.emit(comp),
                    on_progress_update=lambda cur, tot, msg: self.progress_updated.emit(cur, tot, msg),
                    on_enrichment_step=lambda comp, step, desc: self.step_updated.emit(comp, step, desc),
                    on_company_enriched=lambda comp: self.company_updated.emit(comp),
                    is_stopped=lambda: self._is_stopped
                )

            self.workflow_finished.emit(results)

        except Exception as e:
            logger.error(f"SearchWorkflowWorker crashed: {e}", exc_info=True)
            self.error_occurred.emit(str(e))
        finally:
            self.browser_manager.close()
