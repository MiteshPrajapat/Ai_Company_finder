"""
Dedicated LinkedIn & Website Contact Enricher and Career Portal Discovery Widget.
Provides granular, on-demand enrichment with real-time live terminal streaming of all scraping processes.
"""

import os
import webbrowser
from datetime import datetime
from typing import Optional, Dict, Any, List

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel,
    QLineEdit, QPushButton, QFrame, QPlainTextEdit, QTableWidget,
    QTableWidgetItem, QHeaderView, QSplitter, QMessageBox, QTabWidget,
    QProgressBar, QGroupBox
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QTextCursor

from database.models import Company, Job, Contact
from database.repositories import CompaniesRepository, JobsRepository, ContactsRepository
from core.enrichment_manager import EnrichmentManager
from core.job_matcher import JobMatcher
from scrapers.linkedin_company_enricher import linkedin_enricher
from utils.logger import get_logger

logger = get_logger("enrichment_widget")


class GranularEnrichmentWorker(QThread):
    """Background worker executing specific enrichment tasks with real-time telemetry."""
    log_emitted = pyqtSignal(str)
    step_emitted = pyqtSignal(str, str)  # (step_name, detail)
    finished_success = pyqtSignal(dict)
    finished_error = pyqtSignal(str)

    def __init__(
        self,
        company_name: str,
        linkedin_url: Optional[str] = None,
        website_url: Optional[str] = None,
        location: Optional[str] = None,
        mode: str = "linkedin_web",  # "linkedin_web", "career_portal", "full"
        parent=None
    ):
        super().__init__(parent)
        self.company_name = company_name.strip()
        self.linkedin_url = linkedin_url.strip() if linkedin_url else None
        self.website_url = website_url.strip() if website_url else None
        self.location = location.strip() if location else None
        self.mode = mode

    def run(self):
        try:
            self.log_emitted.emit(f"🚀 Initializing {self.mode.upper()} enrichment for '{self.company_name}'...")
            comp_repo = CompaniesRepository()
            jobs_repo = JobsRepository()
            contacts_repo = ContactsRepository()

            # Find or create Company record
            existing = comp_repo.get_by_name(self.company_name)
            if existing:
                company = existing
            else:
                from core.normalizer import JobNormalizer
                c_key = JobNormalizer.generate_company_key(self.company_name)
                company = Company(
                    company_key=c_key,
                    name=self.company_name,
                    normalized_name=JobNormalizer.normalize_company_name(self.company_name),
                    linkedin_url=self.linkedin_url,
                    website_url=self.website_url,
                    city=self.location
                )
                comp_id = comp_repo.upsert(company)
                company.id = comp_id

            if self.linkedin_url and not company.linkedin_url:
                company.linkedin_url = self.linkedin_url
            if self.website_url and not company.website_url:
                company.website_url = self.website_url

            enrichment_manager = EnrichmentManager(
                companies_repo=comp_repo,
                jobs_repo=jobs_repo,
                contacts_repo=contacts_repo
            )

            job_matcher = JobMatcher(profession="Software Engineer")

            do_career = self.mode in ("career_portal", "full")
            do_linkedin = self.mode in ("linkedin_web", "full")

            def step_cb(comp, step, details):
                icon = "🌐" if "LinkedIn" in step or "Website" in step else ("💼" if "Career" in step or "Job" in step else "⚡")
                self.log_emitted.emit(f"{icon} [{step}] {details}")
                self.step_emitted.emit(step, details)

            updated_comp = enrichment_manager.enrich_company(
                company=company,
                job_matcher=job_matcher,
                step_callback=step_cb,
                enrich_career_portals=do_career,
                enrich_linkedin_website=do_linkedin
            )

            # Retrieve refreshed contacts and jobs
            contacts = contacts_repo.get_by_company(updated_comp.id)
            jobs = jobs_repo.get_by_company(updated_comp.id)

            self.log_emitted.emit(f"✨ Enrichment completed! Found {len(contacts)} contact(s), {len(jobs)} job(s).")
            self.finished_success.emit({
                "company": updated_comp,
                "contacts": contacts,
                "jobs": jobs
            })

        except Exception as e:
            logger.error(f"Granular enrichment worker crashed: {e}", exc_info=True)
            self.log_emitted.emit(f"❌ Error occurred: {str(e)}")
            self.finished_error.emit(str(e))


class EnrichmentWidget(QWidget):
    """Standalone page for granular LinkedIn + Website and Career Portal enrichment."""

    contact_hr_requested = pyqtSignal(dict)  # (company, job, email)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.current_worker: Optional[GranularEnrichmentWorker] = None
        self._init_ui()

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(14, 12, 14, 10)
        main_layout.setSpacing(10)

        # Header Card
        header = QFrame()
        header.setObjectName("compactCard")
        h_layout = QHBoxLayout(header)
        h_layout.setContentsMargins(12, 10, 12, 10)
        
        v_title = QVBoxLayout()
        v_title.setSpacing(2)
        title = QLabel("🌐 LinkedIn & Web Contacts Enricher | 💼 Career Portal Hunter")
        title.setObjectName("sectionTitle")
        title.setStyleSheet("font-size: 15px; font-weight: 800; color: #38BDF8;")
        v_title.addWidget(title)
        
        subtitle = QLabel("Deep enrichment of company profiles, LinkedIn About data, HR emails, social profiles, and direct ATS career openings with live process streaming.")
        subtitle.setStyleSheet("color: #94A3B8; font-size: 11px;")
        v_title.addWidget(subtitle)
        h_layout.addLayout(v_title)
        h_layout.addStretch()

        self.btn_li_login = QPushButton("🔑  Login to LinkedIn")
        self.btn_li_login.setObjectName("btnAction")
        self.btn_li_login.setToolTip("Open persistent Chrome window to log in to LinkedIn once. Keeps your session saved.")
        self.btn_li_login.clicked.connect(self._open_linkedin_login)
        h_layout.addWidget(self.btn_li_login)

        main_layout.addWidget(header)

        # Input Parameters Frame
        input_frame = QFrame()
        input_frame.setObjectName("compactCard")
        grid = QGridLayout(input_frame)
        grid.setContentsMargins(14, 12, 14, 12)
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(8)

        grid.addWidget(QLabel("🏢 Company Name *:"), 0, 0)
        self.company_input = QLineEdit()
        self.company_input.setPlaceholderText("e.g. Zomato, Razorpay, Infosys, Swiggy...")
        grid.addWidget(self.company_input, 0, 1)

        grid.addWidget(QLabel("📍 Location:"), 0, 2)
        self.location_input = QLineEdit()
        self.location_input.setPlaceholderText("e.g. Bengaluru, Gurugram, India")
        grid.addWidget(self.location_input, 0, 3)

        grid.addWidget(QLabel("🔗 LinkedIn URL:"), 1, 0)
        self.linkedin_input = QLineEdit()
        self.linkedin_input.setPlaceholderText("https://www.linkedin.com/company/zomato/ (optional)")
        grid.addWidget(self.linkedin_input, 1, 1)

        grid.addWidget(QLabel("🌐 Official Website:"), 1, 2)
        self.website_input = QLineEdit()
        self.website_input.setPlaceholderText("https://www.zomato.com (optional - discovered automatically if blank)")
        grid.addWidget(self.website_input, 1, 3)

        # Action Buttons Row
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)

        self.btn_enrich_linkedin = QPushButton("🌐  Enrich LinkedIn + Website Contacts")
        self.btn_enrich_linkedin.setObjectName("btnPrimary")
        self.btn_enrich_linkedin.setMinimumHeight(36)
        self.btn_enrich_linkedin.setToolTip("Scrapes LinkedIn About, phone, industry, company size, and crawls website for HR/recruiter emails.")
        self.btn_enrich_linkedin.clicked.connect(lambda: self._start_enrichment("linkedin_web"))
        btn_layout.addWidget(self.btn_enrich_linkedin, 2)

        self.btn_enrich_career = QPushButton("💼  Discover Career Portal & Jobs")
        self.btn_enrich_career.setObjectName("btnSuccess")
        self.btn_enrich_career.setMinimumHeight(36)
        self.btn_enrich_career.setToolTip("Finds ATS endpoints (/careers, Greenhouse, Lever, Workday) and extracts active jobs.")
        self.btn_enrich_career.clicked.connect(lambda: self._start_enrichment("career_portal"))
        btn_layout.addWidget(self.btn_enrich_career, 2)

        self.btn_enrich_full = QPushButton("⚡  Full Combined Enrich")
        self.btn_enrich_full.setObjectName("btnAction")
        self.btn_enrich_full.setMinimumHeight(36)
        self.btn_enrich_full.setToolTip("Runs complete pipeline: LinkedIn About + Website Contacts + Career Portals + Jobs.")
        self.btn_enrich_full.clicked.connect(lambda: self._start_enrichment("full"))
        btn_layout.addWidget(self.btn_enrich_full, 1)

        grid.addLayout(btn_layout, 2, 0, 1, 4)
        main_layout.addWidget(input_frame)

        # Splitter: Live Terminal (Left/Top) + Output Tables (Right/Bottom)
        splitter = QSplitter(Qt.Orientation.Vertical)

        # 1. Live Terminal Panel
        term_frame = QFrame()
        term_frame.setObjectName("compactCard")
        term_layout = QVBoxLayout(term_frame)
        term_layout.setContentsMargins(10, 8, 10, 8)
        term_layout.setSpacing(4)

        term_hdr = QHBoxLayout()
        term_title = QLabel("⚡ Live Scraping & Enrichment Process Terminal")
        term_title.setStyleSheet("font-size: 11px; font-weight: 700; color: #38BDF8; text-transform: uppercase;")
        term_hdr.addWidget(term_title)
        term_hdr.addStretch()

        self.status_spinner_lbl = QLabel("● Ready")
        self.status_spinner_lbl.setStyleSheet("color: #34D399; font-size: 11px; font-weight: 600;")
        term_hdr.addWidget(self.status_spinner_lbl)

        clear_btn = QPushButton("Clear Console")
        clear_btn.setObjectName("btnAction")
        clear_btn.setFixedHeight(20)
        clear_btn.setStyleSheet("font-size: 10px; padding: 2px 8px;")
        clear_btn.clicked.connect(lambda: self.terminal.clear())
        term_hdr.addWidget(clear_btn)
        term_layout.addLayout(term_hdr)

        self.terminal = QPlainTextEdit()
        self.terminal.setReadOnly(True)
        self.terminal.setMinimumHeight(130)
        self.terminal.setStyleSheet("""
            QPlainTextEdit {
                background-color: #060913;
                color: #E2E8F0;
                font-family: 'Consolas', 'Courier New', monospace;
                font-size: 12px;
                line-height: 1.4;
                border: 1px solid #1E293B;
                border-radius: 6px;
                padding: 8px;
            }
        """)
        self.terminal.setPlaceholderText("Select an enrichment mode above. Live execution logs, HTTP requests, Selenium browser telemetry, and discovered details will appear here...")
        term_layout.addWidget(self.terminal)
        splitter.addWidget(term_frame)

        # 2. Results Tabs (Details, Contacts, Jobs)
        self.results_tabs = QTabWidget()
        self.results_tabs.setStyleSheet("""
            QTabWidget::pane { border: 1px solid #1E293B; background: #0F172A; border-radius: 6px; }
            QTabBar::tab { background: #1E293B; color: #94A3B8; padding: 6px 16px; font-weight: 600; font-size: 12px; }
            QTabBar::tab:selected { background: #0F172A; color: #38BDF8; border-bottom: 2px solid #38BDF8; }
        """)

        # Tab 1: Company Overview
        self.tab_overview = QWidget()
        to_layout = QVBoxLayout(self.tab_overview)
        to_layout.setContentsMargins(12, 10, 12, 10)
        self.overview_label = QLabel("Run an enrichment task above to view extracted company metadata.")
        self.overview_label.setStyleSheet("color: #CBD5E1; font-size: 12px; line-height: 1.6;")
        self.overview_label.setWordWrap(True)
        to_layout.addWidget(self.overview_label)
        to_layout.addStretch()
        self.results_tabs.addTab(self.tab_overview, "🏢 Company Profile")

        # Tab 2: Contacts
        self.contacts_table = QTableWidget()
        self.contacts_table.setColumnCount(4)
        self.contacts_table.setHorizontalHeaderLabels(["Email Address", "Contact Type", "Source / Location", "Action"])
        self.contacts_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.contacts_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.contacts_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.contacts_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.contacts_table.setAlternatingRowColors(True)
        self.contacts_table.setStyleSheet("border: none; background: #0F172A;")
        self.results_tabs.addTab(self.contacts_table, "✉️ Discovered Contacts (0)")

        # Tab 3: Jobs
        self.jobs_table = QTableWidget()
        self.jobs_table.setColumnCount(4)
        self.jobs_table.setHorizontalHeaderLabels(["Job Title", "Location", "Source", "Action"])
        self.jobs_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.jobs_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.jobs_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.jobs_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.jobs_table.setAlternatingRowColors(True)
        self.jobs_table.setStyleSheet("border: none; background: #0F172A;")
        self.results_tabs.addTab(self.jobs_table, "💼 Career Openings (0)")

        splitter.addWidget(self.results_tabs)
        splitter.setSizes([200, 300])

        main_layout.addWidget(splitter, 1)

    def _start_enrichment(self, mode: str):
        company_name = self.company_input.text().strip()
        if not company_name:
            QMessageBox.warning(self, "Missing Company Name", "Please enter a Company Name to start enrichment.")
            return

        self.btn_enrich_linkedin.setEnabled(False)
        self.btn_enrich_career.setEnabled(False)
        self.btn_enrich_full.setEnabled(False)
        self.status_spinner_lbl.setText("● Processing...")
        self.status_spinner_lbl.setStyleSheet("color: #F59E0B; font-weight: 700; font-size: 11px;")

        self._append_terminal(f"=== Starting {mode.upper()} Pipeline for '{company_name}' ===")

        self.current_worker = GranularEnrichmentWorker(
            company_name=company_name,
            linkedin_url=self.linkedin_input.text().strip(),
            website_url=self.website_input.text().strip(),
            location=self.location_input.text().strip(),
            mode=mode
        )
        self.current_worker.log_emitted.connect(self._append_terminal)
        self.current_worker.finished_success.connect(self._on_enrichment_finished)
        self.current_worker.finished_error.connect(self._on_enrichment_error)
        self.current_worker.start()

    def _append_terminal(self, msg: str):
        ts = datetime.now().strftime("%H:%M:%S")
        self.terminal.appendPlainText(f"[{ts}] {msg}")
        cursor = self.terminal.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        self.terminal.setTextCursor(cursor)

    def _on_enrichment_finished(self, data: dict):
        self.btn_enrich_linkedin.setEnabled(True)
        self.btn_enrich_career.setEnabled(True)
        self.btn_enrich_full.setEnabled(True)
        self.status_spinner_lbl.setText("● Completed")
        self.status_spinner_lbl.setStyleSheet("color: #34D399; font-weight: 700; font-size: 11px;")

        comp: Company = data.get("company")
        contacts: List[Contact] = data.get("contacts", [])
        jobs: List[Job] = data.get("jobs", [])

        # 1. Update Profile Overview
        web_link = f"<a href='{comp.website_url}' style='color: #38BDF8;'>{comp.website_url}</a>" if comp.website_url else "None"
        li_link = f"<a href='{comp.linkedin_url}' style='color: #38BDF8;'>{comp.linkedin_url}</a>" if comp.linkedin_url else "None"
        car_link = f"<a href='{comp.career_url}' style='color: #38BDF8;'>{comp.career_url}</a>" if comp.career_url else "None"

        overview_html = f"""
        <table cellpadding='4' style='font-size: 12px; color: #CBD5E1;'>
            <tr><td><b>Company Name:</b></td><td><span style='color: #F8FAFC; font-weight: 700;'>{comp.name}</span></td></tr>
            <tr><td><b>Official Website:</b></td><td>{web_link} (Status: <b style='color: #34D399;'>{comp.website_status}</b>)</td></tr>
            <tr><td><b>Phone:</b></td><td>{comp.phone or 'Not found'}</td></tr>
            <tr><td><b>Industry / Category:</b></td><td>{comp.company_type or comp.category or 'N/A'}</td></tr>
            <tr><td><b>LinkedIn Profile:</b></td><td>{li_link}</td></tr>
            <tr><td><b>Career Portal:</b></td><td>{car_link} (Status: <b style='color: #38BDF8;'>{comp.career_status}</b>)</td></tr>
        </table>
        """
        self.overview_label.setText(overview_html)

        # 2. Update Contacts Table
        self.results_tabs.setTabText(1, f"✉️ Discovered Contacts ({len(contacts)})")
        self.contacts_table.setRowCount(len(contacts))
        for row, ct in enumerate(contacts):
            self.contacts_table.setItem(row, 0, QTableWidgetItem(ct.email))
            self.contacts_table.setItem(row, 1, QTableWidgetItem(ct.email_type.upper() if ct.email_type else "GENERAL"))
            self.contacts_table.setItem(row, 2, QTableWidgetItem(ct.source_url or "Website Scraper"))

            send_btn = QPushButton("Draft Cold Email ✉️")
            send_btn.setObjectName("btnPrimary")
            send_btn.setStyleSheet("font-size: 11px; padding: 2px 8px;")
            send_btn.clicked.connect(lambda _, c=comp, em=ct.email: self.contact_hr_requested.emit({
                "company": c,
                "email": em
            }))
            self.contacts_table.setCellWidget(row, 3, send_btn)

        # 3. Update Jobs Table
        self.results_tabs.setTabText(2, f"💼 Career Openings ({len(jobs)})")
        self.jobs_table.setRowCount(len(jobs))
        for row, jb in enumerate(jobs):
            self.jobs_table.setItem(row, 0, QTableWidgetItem(jb.title))
            self.jobs_table.setItem(row, 1, QTableWidgetItem(jb.location or "Not specified"))
            self.jobs_table.setItem(row, 2, QTableWidgetItem(jb.source or "career_portal"))

            open_btn = QPushButton("Open Link 🔗" if jb.job_url else "View")
            open_btn.setObjectName("btnAction")
            open_btn.setStyleSheet("font-size: 11px; padding: 2px 8px;")
            if jb.job_url:
                open_btn.clicked.connect(lambda _, u=jb.job_url: webbrowser.open(u))
            self.jobs_table.setCellWidget(row, 3, open_btn)

    def _on_enrichment_error(self, err_msg: str):
        self.btn_enrich_linkedin.setEnabled(True)
        self.btn_enrich_career.setEnabled(True)
        self.btn_enrich_full.setEnabled(True)
        self.status_spinner_lbl.setText("● Error")
        self.status_spinner_lbl.setStyleSheet("color: #EF4444; font-weight: 700; font-size: 11px;")
        QMessageBox.critical(self, "Enrichment Error", f"Enrichment process encountered an error:\n{err_msg}")

    def _open_linkedin_login(self):
        from browser.browser_manager import launch_login_browser
        launch_login_browser("https://www.linkedin.com/login")
        QMessageBox.information(
            self,
            "LinkedIn Login Session",
            "A Chrome browser window has been opened using your persistent profile.\n\n"
            "Please log in to your LinkedIn account in that browser. Once logged in, your session "
            "cookies and credentials will stay saved permanently for all future searches and enrichments."
        )

