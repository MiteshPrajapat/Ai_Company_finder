"""
Main Window interface uniting sidebar navigation, search workflows, results exploration, and background workers.
"""

import webbrowser
from typing import Optional, List, Dict, Any
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QListWidget, QListWidgetItem, QStackedWidget, QStatusBar,
    QMessageBox, QSplitter, QTableWidget, QTableWidgetItem,
    QHeaderView, QAbstractItemView, QPushButton, QFrame,
    QLineEdit, QComboBox, QSizePolicy
)
from PyQt6.QtCore import Qt, pyqtSlot
from PyQt6.QtGui import QIcon, QFont

from database.models import SearchSession, Company, Job
from database.repositories import CompaniesRepository, JobsRepository, ContactsRepository, SearchesRepository
from workers.search_worker import SearchWorkflowWorker
from ui.search_widget import SearchWidget
from ui.progress_widget import ProgressWidget
from ui.results_widget import ResultsWidget
from ui.company_details import CompanyDetailsDialog
from ui.job_details import JobDetailsDialog
from ui.history_widget import HistoryWidget
from ui.export_dialog import ExportDialog
from ui.settings_widget import SettingsWidget
from ui.styles import DARK_THEME_QSS, get_relevance_badge_style, get_status_badge_style
from utils.text_utils import clean_location_display, format_employment_type, is_valid_contact_email
from utils.logger import get_logger

logger = get_logger("main_window")


class MainWindow(QMainWindow):
    """Primary application window for Job Finder AI."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Job Finder AI — Intelligent Company & Job Intelligence")
        self.resize(1366, 768)
        self.setMinimumSize(1100, 680)

        # Repositories
        self.companies_repo = CompaniesRepository()
        self.jobs_repo = JobsRepository()
        self.contacts_repo = ContactsRepository()
        self.searches_repo = SearchesRepository()

        # State
        self.current_worker: Optional[SearchWorkflowWorker] = None
        self.active_search_session: Optional[SearchSession] = None
        self.all_jobs_data: List[Job] = []
        self.all_contacts_data: List[Dict[str, Any]] = []

        self._init_ui()
        self._load_initial_data()

    def _init_ui(self):
        self.setStyleSheet(DARK_THEME_QSS)

        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        root_layout = QVBoxLayout(central_widget)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        # 1. Main Content Splitter (Sidebar + Pages)
        main_content = QHBoxLayout()
        main_content.setContentsMargins(0, 0, 0, 0)
        main_content.setSpacing(0)

        # Left Sidebar Container with Brand Title
        sidebar_container = QWidget()
        sidebar_container.setFixedWidth(220)
        sidebar_container.setStyleSheet("background-color: #0B0F19; border-right: 1px solid #1E293B;")
        sc_layout = QVBoxLayout(sidebar_container)
        sc_layout.setContentsMargins(0, 10, 0, 10)
        sc_layout.setSpacing(8)

        # App Brand Header in Sidebar
        brand_frame = QFrame()
        brand_frame.setStyleSheet("background: transparent; padding: 4px 14px;")
        b_layout = QVBoxLayout(brand_frame)
        b_layout.setContentsMargins(0, 0, 0, 0)
        b_layout.setSpacing(2)
        title = QLabel("🚀 JOB FINDER AI")
        title.setObjectName("headerTitle")
        title.setStyleSheet("font-size: 15px; font-weight: 800; color: #38BDF8;")
        b_layout.addWidget(title)
        sc_layout.addWidget(brand_frame)

        # Sidebar
        self.sidebar = QListWidget()
        self.sidebar.setObjectName("navSidebar")
        self.sidebar.setStyleSheet("border: none; background-color: transparent;")
        self._setup_sidebar_items()
        self.sidebar.currentRowChanged.connect(self._on_nav_changed)
        sc_layout.addWidget(self.sidebar, 1)

        # Status badge inside sidebar bottom
        status_box = QFrame()
        status_box.setStyleSheet("background: transparent; padding: 8px 12px;")
        sb_layout = QVBoxLayout(status_box)
        sb_layout.setContentsMargins(0, 0, 0, 0)
        self.session_badge = QLabel("●  READY")
        self.session_badge.setStyleSheet("background-color: #064E3B; color: #34D399; font-weight: 700; font-size: 11px; padding: 6px 12px; border-radius: 6px; border: 1px solid #059669; text-align: center;")
        self.session_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sb_layout.addWidget(self.session_badge)
        sc_layout.addWidget(status_box)

        main_content.addWidget(sidebar_container)

        # Stacked Pages
        self.pages = QStackedWidget()

        # Page 0: Search & Discover (Primary workflow)
        self.page_search = self._create_search_page()
        self.pages.addWidget(self.page_search)

        # Page 1: All Companies
        self.page_all_companies = self._create_all_companies_page()
        self.pages.addWidget(self.page_all_companies)

        # Page 2: Job Openings
        self.page_all_jobs = self._create_all_jobs_page()
        self.pages.addWidget(self.page_all_jobs)

        # Page 3: Business Contacts
        self.page_all_contacts = self._create_all_contacts_page()
        self.pages.addWidget(self.page_all_contacts)

        # Page 4: History
        self.page_history = HistoryWidget()
        self.page_history.load_search_requested.connect(self._load_search_from_history)
        self.page_history.resume_search_requested.connect(self._resume_search_from_history)
        self.pages.addWidget(self.page_history)

        # Page 5: Settings
        self.page_settings = SettingsWidget()
        self.pages.addWidget(self.page_settings)

        main_content.addWidget(self.pages, 1)
        root_layout.addLayout(main_content, 1)

        # 3. Status Bar
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("Ready. Enter search parameters to discover companies.")

        self.sidebar.setCurrentRow(0)

    def _setup_sidebar_items(self):
        items = [
            ("🔎  Search & Discover", 0),
            ("🏢  All Companies", 1),
            ("💼  Job Openings", 2),
            ("✉️  Business Contacts", 3),
            ("📜  Search History", 4),
            ("⚙️  Settings", 5)
        ]
        for label, idx in items:
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, idx)
            self.sidebar.addItem(item)

    # -------------------------------------------------------------
    # Page 1: Search & Discover
    # -------------------------------------------------------------
    def _create_search_page(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Form (Compact, stretch=0)
        self.search_widget = SearchWidget()
        self.search_widget.search_requested.connect(self._start_search)
        self.search_widget.stop_requested.connect(self._stop_search)
        self.search_widget.resume_requested.connect(self._resume_enrichment)
        layout.addWidget(self.search_widget, 0)

        # Progress (Compact, stretch=0)
        self.progress_widget = ProgressWidget()
        layout.addWidget(self.progress_widget, 0)

        # Results (Stretch=1 so table receives all remaining space)
        self.results_widget = ResultsWidget()
        self.results_widget.company_selected.connect(self._open_company_details)
        self.results_widget.export_requested.connect(self._open_export_dialog)
        layout.addWidget(self.results_widget, 1)

        return widget

    # -------------------------------------------------------------
    # Page 2: All Saved Companies
    # -------------------------------------------------------------
    def _create_all_companies_page(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(14, 12, 14, 10)
        layout.setSpacing(8)

        header = QFrame()
        header.setObjectName("compactCard")
        h_layout = QHBoxLayout(header)
        h_layout.setContentsMargins(12, 8, 12, 8)

        title = QLabel("All Saved Companies Database")
        title.setObjectName("sectionTitle")
        h_layout.addWidget(title)
        h_layout.addStretch()

        refresh_btn = QPushButton("🔄 Refresh")
        refresh_btn.setObjectName("btnAction")
        refresh_btn.clicked.connect(self._refresh_all_companies_page)
        h_layout.addWidget(refresh_btn)
        layout.addWidget(header)

        self.all_companies_results = ResultsWidget()
        self.all_companies_results.company_selected.connect(self._open_company_details)
        self.all_companies_results.export_requested.connect(self._open_export_dialog)
        layout.addWidget(self.all_companies_results, 1)
        return widget

    # -------------------------------------------------------------
    # Page 3: Job Openings
    # -------------------------------------------------------------
    def _create_all_jobs_page(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(14, 12, 14, 10)
        layout.setSpacing(8)

        # Header
        header = QFrame()
        header.setObjectName("compactCard")
        h_layout = QHBoxLayout(header)
        h_layout.setContentsMargins(12, 8, 12, 8)

        title = QLabel("Extracted Job Openings & Career Opportunities")
        title.setObjectName("sectionTitle")
        h_layout.addWidget(title)
        h_layout.addStretch()

        refresh_btn = QPushButton("🔄 Refresh Jobs")
        refresh_btn.setObjectName("btnAction")
        refresh_btn.clicked.connect(self._refresh_all_jobs_page)
        h_layout.addWidget(refresh_btn)
        layout.addWidget(header)

        # Filter Bar for Jobs
        jobs_filter_frame = QFrame()
        jobs_filter_frame.setObjectName("compactCard")
        jf_layout = QHBoxLayout(jobs_filter_frame)
        jf_layout.setContentsMargins(10, 6, 10, 6)
        jf_layout.setSpacing(8)

        self.jobs_search_input = QLineEdit()
        self.jobs_search_input.setPlaceholderText("🔎 Filter by job title, company, or keyword...")
        self.jobs_search_input.textChanged.connect(self._filter_jobs_table)
        jf_layout.addWidget(self.jobs_search_input, 2)

        jf_layout.addWidget(QLabel("Source:"))
        self.jobs_source_filter = QComboBox()
        self.jobs_source_filter.addItems(["All", "Career Portal", "Indeed", "Unstop", "LinkedIn", "Glassdoor"])
        self.jobs_source_filter.currentTextChanged.connect(self._filter_jobs_table)
        jf_layout.addWidget(self.jobs_source_filter)

        jf_layout.addWidget(QLabel("Work Mode:"))
        self.jobs_workmode_filter = QComboBox()
        self.jobs_workmode_filter.addItems(["All", "Remote", "Hybrid", "On-site"])
        self.jobs_workmode_filter.currentTextChanged.connect(self._filter_jobs_table)
        jf_layout.addWidget(self.jobs_workmode_filter)

        jf_layout.addWidget(QLabel("Min Relevance:"))
        self.jobs_score_filter = QComboBox()
        self.jobs_score_filter.addItems(["All", "80%+ (High)", "60%+ (Good)", "40%+ (Moderate)"])
        self.jobs_score_filter.currentTextChanged.connect(self._filter_jobs_table)
        jf_layout.addWidget(self.jobs_score_filter)

        jf_layout.addStretch(1)
        layout.addWidget(jobs_filter_frame)

        # Jobs Table
        self.jobs_table = QTableWidget()
        self.jobs_table.setColumnCount(8)
        self.jobs_table.setHorizontalHeaderLabels([
            "Job Title", "Company", "Available Sources", "Location", "Work Mode", "Type", "Relevance", "Action"
        ])
        self.jobs_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.jobs_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.jobs_table.setAlternatingRowColors(True)
        self.jobs_table.verticalHeader().setVisible(False)
        self.jobs_table.doubleClicked.connect(self._on_job_row_double_clicked)
        self.jobs_table.setSortingEnabled(True)

        j_header = self.jobs_table.horizontalHeader()
        j_header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        j_header.setSectionResizeMode(1, QHeaderView.ResizeMode.Interactive)
        j_header.setSectionResizeMode(2, QHeaderView.ResizeMode.Interactive)
        j_header.setSectionResizeMode(3, QHeaderView.ResizeMode.Interactive)
        j_header.setSectionResizeMode(4, QHeaderView.ResizeMode.Interactive)
        j_header.setSectionResizeMode(5, QHeaderView.ResizeMode.Interactive)
        j_header.setSectionResizeMode(6, QHeaderView.ResizeMode.ResizeToContents)
        j_header.setSectionResizeMode(7, QHeaderView.ResizeMode.ResizeToContents)

        self.jobs_table.setColumnWidth(1, 180)
        self.jobs_table.setColumnWidth(2, 170)
        self.jobs_table.setColumnWidth(3, 140)
        self.jobs_table.setColumnWidth(4, 90)
        self.jobs_table.setColumnWidth(5, 90)

        layout.addWidget(self.jobs_table, 1)
        return widget

    # -------------------------------------------------------------
    # Page 4: Business Contacts
    # -------------------------------------------------------------
    def _create_all_contacts_page(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(14, 12, 14, 10)
        layout.setSpacing(8)

        # Header
        header = QFrame()
        header.setObjectName("compactCard")
        h_layout = QHBoxLayout(header)
        h_layout.setContentsMargins(12, 8, 12, 8)

        title = QLabel("Extracted Business Contacts & Verified Emails")
        title.setObjectName("sectionTitle")
        h_layout.addWidget(title)
        h_layout.addStretch()

        refresh_btn = QPushButton("🔄 Refresh Contacts")
        refresh_btn.setObjectName("btnAction")
        refresh_btn.clicked.connect(self._refresh_all_contacts_page)
        h_layout.addWidget(refresh_btn)
        layout.addWidget(header)

        # Filter Bar for Contacts
        contacts_filter_frame = QFrame()
        contacts_filter_frame.setObjectName("compactCard")
        cf_layout = QHBoxLayout(contacts_filter_frame)
        cf_layout.setContentsMargins(10, 6, 10, 6)
        cf_layout.setSpacing(8)

        self.contacts_search_input = QLineEdit()
        self.contacts_search_input.setPlaceholderText("🔎 Filter by email address, company, or domain...")
        self.contacts_search_input.textChanged.connect(self._filter_contacts_table)
        cf_layout.addWidget(self.contacts_search_input, 2)

        cf_layout.addWidget(QLabel("Category:"))
        self.contacts_cat_filter = QComboBox()
        self.contacts_cat_filter.addItems(["All", "General", "HR", "Careers", "Jobs", "Sales", "Support"])
        self.contacts_cat_filter.currentTextChanged.connect(self._filter_contacts_table)
        cf_layout.addWidget(self.contacts_cat_filter)

        cf_layout.addStretch(1)
        layout.addWidget(contacts_filter_frame)

        # Contacts Table
        self.contacts_table = QTableWidget()
        self.contacts_table.setColumnCount(5)
        self.contacts_table.setHorizontalHeaderLabels([
            "Email Address", "Category", "Company", "Location", "Website"
        ])
        self.contacts_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.contacts_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.contacts_table.setAlternatingRowColors(True)
        self.contacts_table.verticalHeader().setVisible(False)
        self.contacts_table.setSortingEnabled(True)

        c_header = self.contacts_table.horizontalHeader()
        c_header.setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
        c_header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        c_header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        c_header.setSectionResizeMode(3, QHeaderView.ResizeMode.Interactive)
        c_header.setSectionResizeMode(4, QHeaderView.ResizeMode.Interactive)

        self.contacts_table.setColumnWidth(0, 270)
        self.contacts_table.setColumnWidth(3, 160)
        self.contacts_table.setColumnWidth(4, 180)

        layout.addWidget(self.contacts_table, 1)
        return widget

    def _on_nav_changed(self, row: int):
        self.pages.setCurrentIndex(row)
        if row == 1:
            self._refresh_all_companies_page()
        elif row == 2:
            self._refresh_all_jobs_page()
        elif row == 3:
            self._refresh_all_contacts_page()
        elif row == 4:
            self.page_history.reload_history()

    def _load_initial_data(self):
        companies = self.companies_repo.get_companies(limit=50)
        self.results_widget.load_companies(companies)
        self.all_companies_results.load_companies(companies)

    def _refresh_all_companies_page(self):
        companies = self.companies_repo.get_companies(limit=500)
        self.all_companies_results.load_companies(companies)

    # -------------------------------------------------------------
    # Jobs Management (Page 3)
    # -------------------------------------------------------------
    def _refresh_all_jobs_page(self):
        self.all_jobs_data = self.jobs_repo.get_all_jobs(limit=500)
        self._filter_jobs_table()

    def _filter_jobs_table(self):
        search_kw = self.jobs_search_input.text().lower().strip()
        source_filter = self.jobs_source_filter.currentText()
        workmode = self.jobs_workmode_filter.currentText()
        score_sel = self.jobs_score_filter.currentText()

        min_score = 0
        if "80%" in score_sel:
            min_score = 80
        elif "60%" in score_sel:
            min_score = 60
        elif "40%" in score_sel:
            min_score = 40

        filtered = []
        for job in self.all_jobs_data:
            if search_kw:
                combined = f"{job.title} {job.company_name or ''} {job.location or ''} {job.description or ''}".lower()
                if search_kw not in combined:
                    continue

            if source_filter != "All":
                target_src = source_filter.lower().replace(" ", "_")
                job_sources = [s.source.lower() for s in (job.sources or [])]
                if target_src not in job_sources and (job.source or "").lower() != target_src:
                    continue

            if workmode != "All" and (job.work_mode or "").lower() != workmode.lower():
                continue

            if job.relevance_score < min_score:
                continue

            filtered.append(job)

        self.jobs_table.setSortingEnabled(False)
        self.jobs_table.setRowCount(len(filtered))

        for row, job in enumerate(filtered):
            # 0. Job Title
            item_title = QTableWidgetItem(job.title)
            item_title.setData(Qt.ItemDataRole.UserRole, job)
            item_title.setToolTip(job.title)
            self.jobs_table.setItem(row, 0, item_title)

            # 1. Company
            item_comp = QTableWidgetItem(job.company_name or "-")
            self.jobs_table.setItem(row, 1, item_comp)

            # 2. Available Sources Badges
            src_container = QWidget()
            src_layout = QHBoxLayout(src_container)
            src_layout.setContentsMargins(4, 2, 4, 2)
            src_layout.setSpacing(4)

            sources = job.sources if job.sources else []
            src_names = set(s.source for s in sources) if sources else {job.source or "career_portal"}

            for sname in sorted(list(src_names)):
                lbl = QLabel(sname.replace("_", " ").title())
                lbl.setStyleSheet("background-color: #0F172A; color: #38BDF8; border: 1px solid #0284C7; font-size: 9px; font-weight: 700; padding: 1px 4px; border-radius: 3px;")
                src_layout.addWidget(lbl)
            src_layout.addStretch()
            self.jobs_table.setCellWidget(row, 2, src_container)

            # 3. Location (Cleaned)
            clean_loc = clean_location_display(job.location)
            item_loc = QTableWidgetItem(clean_loc)
            item_loc.setToolTip(clean_loc)
            self.jobs_table.setItem(row, 3, item_loc)

            # 4. Work Mode
            item_mode = QTableWidgetItem(job.work_mode or job.remote_type or "-")
            item_mode.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.jobs_table.setItem(row, 4, item_mode)

            # 5. Type (Cleaned)
            clean_type = format_employment_type(job.employment_type)
            item_type = QTableWidgetItem(clean_type)
            item_type.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.jobs_table.setItem(row, 5, item_type)

            # 6. Score
            score_lbl = QLabel(f"{job.relevance_score}%")
            score_lbl.setStyleSheet(get_relevance_badge_style(job.relevance_score))
            score_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.jobs_table.setCellWidget(row, 6, score_lbl)

            # 7. Action Button
            btn = QPushButton("VIEW")
            btn.setObjectName("btnAction")
            btn.clicked.connect(lambda checked=False, j=job: self._open_job_modal(j))
            self.jobs_table.setCellWidget(row, 7, btn)

        self.jobs_table.setSortingEnabled(True)

    def _on_job_row_double_clicked(self, index):
        row = index.row()
        item = self.jobs_table.item(row, 0)
        if item:
            job = item.data(Qt.ItemDataRole.UserRole)
            if job:
                self._open_job_modal(job)

    # -------------------------------------------------------------
    # Contacts Management (Page 4)
    # -------------------------------------------------------------
    def _refresh_all_contacts_page(self):
        raw_contacts = self.contacts_repo.get_all_contacts(limit=500)
        # Filter out malformed strings / artifacts
        self.all_contacts_data = [ct for ct in raw_contacts if is_valid_contact_email(ct.get("email"))]
        self._filter_contacts_table()

    def _filter_contacts_table(self):
        search_kw = self.contacts_search_input.text().lower().strip()
        cat_filter = self.contacts_cat_filter.currentText()

        filtered = []
        for ct in self.all_contacts_data:
            email = ct.get("email") or ""
            company = ct.get("company_name") or ""
            city = ct.get("city") or ""
            web = ct.get("website_url") or ""

            if search_kw:
                combined = f"{email} {company} {city} {web}".lower()
                if search_kw not in combined:
                    continue

            if cat_filter != "All" and (ct.get("email_type") or "General").lower() != cat_filter.lower():
                continue

            filtered.append(ct)

        self.contacts_table.setSortingEnabled(False)
        self.contacts_table.setRowCount(len(filtered))

        for row, ct in enumerate(filtered):
            # Email Address
            item_email = QTableWidgetItem(ct.get("email") or "-")
            item_email.setToolTip(ct.get("email") or "")
            self.contacts_table.setItem(row, 0, item_email)

            # Category (Full clean word badge)
            cat_name = ct.get("email_type") or "General"
            if len(cat_name) <= 4 and cat_name.lower() in ["ener", "gen"]:
                cat_name = "General"
            type_lbl = QLabel(cat_name)
            type_lbl.setStyleSheet(get_status_badge_style(cat_name))
            type_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.contacts_table.setCellWidget(row, 1, type_lbl)

            # Company Name
            item_comp = QTableWidgetItem(ct.get("company_name") or "-")
            item_comp.setData(Qt.ItemDataRole.UserRole, ct.get("company_id"))
            item_comp.setToolTip(ct.get("company_name") or "")
            self.contacts_table.setItem(row, 2, item_comp)

            # Location
            loc = f"{ct.get('city') or ''}, {ct.get('state') or ''}".strip(", ")
            item_loc = QTableWidgetItem(loc or "-")
            self.contacts_table.setItem(row, 3, item_loc)

            # Website
            raw_web = ct.get("website_url") or "-"
            disp_web = raw_web.replace("https://", "").replace("http://", "").split("/")[0] if raw_web != "-" else "-"
            item_web = QTableWidgetItem(disp_web)
            item_web.setToolTip(raw_web)
            self.contacts_table.setItem(row, 4, item_web)

        self.contacts_table.setSortingEnabled(True)

    # -------------------------------------------------------------
    # Search Workflow Execution (Page 1)
    # -------------------------------------------------------------
    def _start_search(self, session: SearchSession):
        logger.info(f"Main window starting search session: {session.city}, {session.profession}")
        self.active_search_session = session
        self.session_badge.setText("●  SEARCHING")
        self.session_badge.setStyleSheet("background-color: #0C4A6E; color: #7DD3FC; font-weight: 700; font-size: 11px; padding: 5px 14px; border-radius: 6px; border: 1px solid #0284C7;")
        self.progress_widget.reset_progress()
        self.results_widget.companies.clear()
        self.results_widget._refresh_table()

        self.current_worker = SearchWorkflowWorker(session=session, is_resume=False)
        self._wire_worker(self.current_worker)
        self.current_worker.start()

    def _resume_enrichment(self, session: SearchSession):
        logger.info("Main window resuming enrichment workflow.")
        self.session_badge.setText("●  ENRICHING")
        self.session_badge.setStyleSheet("background-color: #0C4A6E; color: #7DD3FC; font-weight: 700; font-size: 11px; padding: 5px 14px; border-radius: 6px; border: 1px solid #0284C7;")
        self.progress_widget.reset_progress()

        self.current_worker = SearchWorkflowWorker(session=session, is_resume=True)
        self._wire_worker(self.current_worker)
        self.current_worker.start()

    def _stop_search(self):
        if self.current_worker and self.current_worker.isRunning():
            self.session_badge.setText("●  STOPPING...")
            self.session_badge.setStyleSheet("background-color: #78350F; color: #FDE68A; font-weight: 700; font-size: 11px; padding: 5px 14px; border-radius: 6px; border: 1px solid #D97706;")
            self.status_bar.showMessage("Stopping active search and cleaning up...")
            self.current_worker.stop()

    def _wire_worker(self, worker: SearchWorkflowWorker):
        worker.company_found.connect(self._on_company_found)
        worker.company_updated.connect(self._on_company_updated)
        worker.progress_updated.connect(self.progress_widget.update_progress)
        worker.step_updated.connect(self.progress_widget.on_step_updated)
        worker.workflow_finished.connect(self._on_workflow_finished)
        worker.error_occurred.connect(self._on_worker_error)

    @pyqtSlot(Company)
    def _on_company_found(self, comp: Company):
        self.progress_widget.on_company_found(comp)
        self.results_widget.add_or_update_company(comp)

    @pyqtSlot(Company)
    def _on_company_updated(self, comp: Company):
        self.progress_widget.on_company_enriched(comp)
        self.results_widget.add_or_update_company(comp)

    @pyqtSlot(list)
    def _on_workflow_finished(self, results: list):
        self.search_widget.set_running_state(False)
        self.session_badge.setText("●  COMPLETED")
        self.session_badge.setStyleSheet("background-color: #064E3B; color: #34D399; font-weight: 700; font-size: 11px; padding: 5px 14px; border-radius: 6px; border: 1px solid #059669;")
        self.status_bar.showMessage(f"Workflow complete. Processed {len(results)} companies.")
        self.progress_widget.update_progress(100, 100, "Workflow Completed")
        self.page_history.reload_history()

    @pyqtSlot(str)
    def _on_worker_error(self, err_msg: str):
        self.search_widget.set_running_state(False)
        self.session_badge.setText("●  ERROR")
        self.session_badge.setStyleSheet("background-color: #7F1D1D; color: #FCA5A5; font-weight: 700; font-size: 11px; padding: 5px 14px; border-radius: 6px; border: 1px solid #DC2626;")
        self.status_bar.showMessage(f"Error during workflow: {err_msg}")
        QMessageBox.warning(self, "Workflow Notice", f"Notice: {err_msg}")

    # -------------------------------------------------------------
    # History Integration
    # -------------------------------------------------------------
    def _load_search_from_history(self, search_id: int):
        companies = self.companies_repo.get_companies(search_id=search_id)
        self.results_widget.load_companies(companies)
        self.sidebar.setCurrentRow(0)
        self.status_bar.showMessage(f"Loaded {len(companies)} companies from Search #{search_id}.")

    def _resume_search_from_history(self, search_id: int):
        session = self.searches_repo.get_by_id(search_id)
        if not session:
            QMessageBox.warning(self, "Error", "Search session not found.")
            return

        self.sidebar.setCurrentRow(0)
        self.search_widget.set_running_state(True)
        self._resume_enrichment(session)

    # -------------------------------------------------------------
    # Dialogs & Detail Modals
    # -------------------------------------------------------------
    def _open_company_details(self, company_id: int):
        dialog = CompanyDetailsDialog(company_id=company_id, parent=self)
        dialog.exec()

    def _open_job_modal(self, job: Job):
        dialog = JobDetailsDialog(job=job, parent=self)
        dialog.exec()

    def _open_export_dialog(self):
        active_id = self.active_search_session.id if self.active_search_session else None
        dialog = ExportDialog(search_id=active_id, parent=self)
        dialog.exec()
