"""
Detailed Company modal dialog featuring tabbed overview, extracted job openings, and business contacts.
"""

import webbrowser
from typing import Optional
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel,
    QPushButton, QFrame, QTabWidget, QTableWidget, QTableWidgetItem,
    QHeaderView, QWidget, QAbstractItemView
)
from PyQt6.QtCore import Qt
from database.models import Company, Job, Contact
from database.repositories import CompaniesRepository, JobsRepository, ContactsRepository
from ui.job_details import JobDetailsDialog
from ui.styles import get_status_badge_style, get_relevance_badge_style
from utils.text_utils import clean_location_display, format_employment_type, is_valid_contact_email


class CompanyDetailsDialog(QDialog):
    """Full detail view for a specific company with tabs for Overview, Jobs, and Contacts."""

    def __init__(self, company_id: int, parent=None):
        super().__init__(parent)
        self.company_id = company_id
        self.companies_repo = CompaniesRepository()
        self.jobs_repo = JobsRepository()
        self.contacts_repo = ContactsRepository()

        self.company = self.companies_repo.get_by_id(company_id)
        self.jobs = self.jobs_repo.get_by_company(company_id)
        raw_contacts = self.contacts_repo.get_by_company(company_id)
        self.contacts = [c for c in raw_contacts if is_valid_contact_email(c.email)]

        comp_name = self.company.name if self.company else "Unknown Company"
        self.setWindowTitle(f"Company Profile — {comp_name}")
        self.resize(860, 600)
        self.setMinimumSize(720, 500)
        self._init_ui()

    def _init_ui(self):
        if not self.company:
            layout = QVBoxLayout(self)
            layout.addWidget(QLabel("Company record not found in database."))
            return

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(18, 16, 18, 16)
        main_layout.setSpacing(12)

        # 1. Header Frame
        header = QFrame()
        header.setObjectName("cardFrame")
        h_layout = QVBoxLayout(header)
        h_layout.setContentsMargins(16, 12, 16, 12)
        h_layout.setSpacing(6)

        top_row = QHBoxLayout()
        name_lbl = QLabel(self.company.name)
        name_lbl.setObjectName("headerTitle")
        top_row.addWidget(name_lbl)
        top_row.addStretch()

        web_badge = QLabel(self.company.website_status)
        web_badge.setStyleSheet(get_status_badge_style(self.company.website_status))
        top_row.addWidget(web_badge)

        enrich_badge = QLabel(self.company.enrichment_status)
        enrich_badge.setStyleSheet(get_status_badge_style(self.company.enrichment_status))
        top_row.addWidget(enrich_badge)
        h_layout.addLayout(top_row)

        sub_info = f"🏷️ {self.company.company_type or 'General Company'}  |  📍 {self.company.address or self.company.city or 'Location Unspecified'}"
        if self.company.rating:
            sub_info += f"  |  ⭐ {self.company.rating:.1f} ({self.company.review_count or 0} reviews)"
        sub_lbl = QLabel(sub_info)
        sub_lbl.setStyleSheet("color: #94A3B8; font-weight: 500; font-size: 11px;")
        h_layout.addWidget(sub_lbl)

        main_layout.addWidget(header)

        # 2. Tabs
        tabs = QTabWidget()

        # Tab 1: Overview
        tab_overview = self._create_overview_tab()
        tabs.addTab(tab_overview, "📌 Overview & Web Links")

        # Tab 2: Jobs
        tab_jobs = self._create_jobs_tab()
        tabs.addTab(tab_jobs, f"💼 Job Openings ({len(self.jobs)})")

        # Tab 3: Contacts
        tab_contacts = self._create_contacts_tab()
        tabs.addTab(tab_contacts, f"✉️ Business Contacts ({len(self.contacts)})")

        main_layout.addWidget(tabs, 1)

        # Bottom Actions
        bottom_row = QHBoxLayout()
        bottom_row.addStretch()

        close_btn = QPushButton("Close")
        close_btn.setObjectName("btnAction")
        close_btn.setMinimumWidth(90)
        close_btn.clicked.connect(self.accept)
        bottom_row.addWidget(close_btn)
        main_layout.addLayout(bottom_row)

    def _create_overview_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(12)

        grid = QGridLayout()
        grid.setSpacing(10)

        # General info
        grid.addWidget(QLabel("<b>Phone:</b>"), 0, 0)
        grid.addWidget(QLabel(self.company.phone or "Not provided"), 0, 1)

        grid.addWidget(QLabel("<b>Official Website:</b>"), 1, 0)
        web_box = QHBoxLayout()
        web_text = self.company.website_url or "None"
        web_lbl = QLabel(web_text)
        web_lbl.setWordWrap(True)
        web_box.addWidget(web_lbl)
        if self.company.website_url:
            web_btn = QPushButton("Open 🌐")
            web_btn.setObjectName("btnAction")
            web_btn.setFixedWidth(70)
            web_btn.clicked.connect(lambda: webbrowser.open(self.company.website_url))
            web_box.addWidget(web_btn)
        grid.addLayout(web_box, 1, 1)

        grid.addWidget(QLabel("<b>Career Portal:</b>"), 2, 0)
        career_box = QHBoxLayout()
        career_text = self.company.career_url or "None"
        career_lbl = QLabel(career_text)
        career_lbl.setWordWrap(True)
        career_box.addWidget(career_lbl)
        if self.company.career_url:
            career_btn = QPushButton("Open 💼")
            career_btn.setObjectName("btnAction")
            career_btn.setFixedWidth(70)
            career_btn.clicked.connect(lambda: webbrowser.open(self.company.career_url))
            career_box.addWidget(career_btn)
        grid.addLayout(career_box, 2, 1)

        grid.addWidget(QLabel("<b>Google Maps:</b>"), 3, 0)
        maps_box = QHBoxLayout()
        if self.company.maps_url:
            maps_btn = QPushButton("View on Google Maps 🗺️")
            maps_btn.setObjectName("btnAction")
            maps_btn.clicked.connect(lambda: webbrowser.open(self.company.maps_url))
            maps_box.addWidget(maps_btn)
        else:
            maps_box.addWidget(QLabel("Maps link not available"))
        maps_box.addStretch()
        grid.addLayout(maps_box, 3, 1)

        layout.addLayout(grid)

        # Social Profiles Box
        layout.addWidget(QLabel("<b>Social Profiles:</b>"))
        social_box = QHBoxLayout()
        social_box.setSpacing(8)

        social_links = [
            ("LinkedIn", self.company.linkedin_url),
            ("Facebook", self.company.facebook_url),
            ("Instagram", self.company.instagram_url),
            ("Twitter / X", self.company.twitter_url),
            ("YouTube", self.company.youtube_url),
            ("GitHub", self.company.github_url)
        ]

        has_social = False
        for name, url in social_links:
            if url:
                has_social = True
                btn = QPushButton(f"🔗 {name}")
                btn.setObjectName("btnAction")
                btn.clicked.connect(lambda checked=False, target=url: webbrowser.open(target))
                social_box.addWidget(btn)

        if not has_social:
            lbl_no_soc = QLabel("No public social profiles detected on website.")
            lbl_no_soc.setStyleSheet("color: #94A3B8; font-style: italic;")
            social_box.addWidget(lbl_no_soc)

        social_box.addStretch()
        layout.addLayout(social_box)
        layout.addStretch()
        return widget

    def _create_jobs_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(12, 12, 12, 12)

        if not self.jobs:
            empty_lbl = QLabel("No relevant job openings found.")
            empty_lbl.setStyleSheet("color: #94A3B8; font-style: italic; font-size: 12px; padding: 20px;")
            empty_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(empty_lbl)
            return widget

        table = QTableWidget()
        table.setColumnCount(6)
        table.setHorizontalHeaderLabels(["Job Title", "Available Sources", "Location", "Work Mode", "Relevance", "Action"])
        table.setRowCount(len(self.jobs))
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setAlternatingRowColors(True)
        table.verticalHeader().setVisible(False)

        header = table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)

        table.setColumnWidth(1, 180)
        table.setColumnWidth(2, 140)
        table.setColumnWidth(3, 90)

        for row, job in enumerate(self.jobs):
            # Job Title
            table.setItem(row, 0, QTableWidgetItem(job.title))

            # Available Sources Badges
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
            table.setCellWidget(row, 1, src_container)

            # Location & Work Mode
            table.setItem(row, 2, QTableWidgetItem(clean_location_display(job.location)))
            table.setItem(row, 3, QTableWidgetItem(job.work_mode or job.remote_type or "-"))

            score_lbl = QLabel(f"{job.relevance_score}%")
            score_lbl.setStyleSheet(get_relevance_badge_style(job.relevance_score))
            score_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            table.setCellWidget(row, 4, score_lbl)

            btn = QPushButton("View")
            btn.setObjectName("btnAction")
            btn.clicked.connect(lambda checked=False, target_job=job: self._open_job_details(target_job))
            table.setCellWidget(row, 5, btn)

        layout.addWidget(table)
        return widget

    def _create_contacts_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(12, 12, 12, 12)

        if not self.contacts:
            empty_lbl = QLabel("No public business email found.")
            empty_lbl.setStyleSheet("color: #94A3B8; font-style: italic; font-size: 12px; padding: 20px;")
            empty_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(empty_lbl)
            return widget

        table = QTableWidget()
        table.setColumnCount(3)
        table.setHorizontalHeaderLabels(["Email Address", "Category", "Source URL"])
        table.setRowCount(len(self.contacts))
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setAlternatingRowColors(True)
        table.verticalHeader().setVisible(False)

        header = table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)

        table.setColumnWidth(0, 240)

        for row, contact in enumerate(self.contacts):
            table.setItem(row, 0, QTableWidgetItem(contact.email))

            cat_lbl = QLabel(contact.email_type)
            cat_lbl.setStyleSheet(get_status_badge_style(contact.email_type))
            cat_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            table.setCellWidget(row, 1, cat_lbl)

            table.setItem(row, 2, QTableWidgetItem(contact.source_url or "-"))

        layout.addWidget(table)
        return widget

    def _open_job_details(self, job: Job):
        job.company_name = self.company.name
        dialog = JobDetailsDialog(job, self)
        dialog.exec()
