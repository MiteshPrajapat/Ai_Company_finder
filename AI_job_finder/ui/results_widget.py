"""
Interactive results table widget with live sorting, filtering, status badges, empty states, and context menu.
"""

import webbrowser
from typing import List, Optional, Dict
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QComboBox, QCheckBox, QPushButton, QTableWidget,
    QTableWidgetItem, QHeaderView, QMenu, QFrame, QAbstractItemView,
    QSizePolicy
)
from PyQt6.QtCore import pyqtSignal, Qt
from database.models import Company
from ui.styles import get_status_badge_style


class ResultsWidget(QWidget):
    """Results table view with filters, badges, and company inspection."""

    company_selected = pyqtSignal(int)  # company_id
    export_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.companies: Dict[int, Company] = {}
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._init_ui()

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(14, 0, 14, 10)
        main_layout.setSpacing(6)

        # 1. Compact Filter Bar
        filter_frame = QFrame()
        filter_frame.setObjectName("compactCard")
        filter_layout = QHBoxLayout(filter_frame)
        filter_layout.setContentsMargins(10, 6, 10, 6)
        filter_layout.setSpacing(8)

        # Search box
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("🔎 Filter by company, address, domain...")
        self.search_input.setMinimumWidth(200)
        self.search_input.textChanged.connect(self._apply_filters)
        filter_layout.addWidget(self.search_input, 2)

        # Website Status combo
        lbl_web = QLabel("Website:")
        lbl_web.setStyleSheet("font-size: 11px; color: #94A3B8;")
        filter_layout.addWidget(lbl_web)
        self.web_filter = QComboBox()
        self.web_filter.addItems(["All", "LIVE", "OFFLINE", "TIMEOUT", "BLOCKED"])
        self.web_filter.currentTextChanged.connect(self._apply_filters)
        filter_layout.addWidget(self.web_filter)

        # Enrichment Status combo
        lbl_enr = QLabel("Enrichment:")
        lbl_enr.setStyleSheet("font-size: 11px; color: #94A3B8;")
        filter_layout.addWidget(lbl_enr)
        self.enrich_filter = QComboBox()
        self.enrich_filter.addItems(["All", "COMPLETED", "ENRICHING", "PENDING", "STOPPED", "FAILED", "OFFLINE"])
        self.enrich_filter.currentTextChanged.connect(self._apply_filters)
        filter_layout.addWidget(self.enrich_filter)

        # Checkboxes
        self.has_jobs_check = QCheckBox("With Jobs")
        self.has_jobs_check.stateChanged.connect(self._apply_filters)
        filter_layout.addWidget(self.has_jobs_check)

        self.has_emails_check = QCheckBox("With Emails")
        self.has_emails_check.stateChanged.connect(self._apply_filters)
        filter_layout.addWidget(self.has_emails_check)

        filter_layout.addStretch(1)

        # Export Button
        self.export_btn = QPushButton("📥 Export")
        self.export_btn.setObjectName("btnAction")
        self.export_btn.clicked.connect(self.export_requested.emit)
        filter_layout.addWidget(self.export_btn)

        main_layout.addWidget(filter_frame)

        # 2. Table Container / Widget
        self.table = QTableWidget()
        self.table.setColumnCount(11)
        self.table.setHorizontalHeaderLabels([
            "#", "Company", "Type", "Location", "Phone",
            "Website", "Rating", "Web Status", "Jobs", "Emails", "Enrichment"
        ])
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._show_context_menu)
        self.table.doubleClicked.connect(self._on_row_double_clicked)
        self.table.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.table.setSortingEnabled(True)

        # Column sizing (Adaptive + interactive)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(6, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(7, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(8, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(9, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(10, QHeaderView.ResizeMode.ResizeToContents)

        self.table.setColumnWidth(1, 200)
        self.table.setColumnWidth(2, 120)
        self.table.setColumnWidth(4, 110)
        self.table.setColumnWidth(5, 150)

        main_layout.addWidget(self.table, 1)

    def load_companies(self, companies: List[Company]):
        """Populates the table with an initial list of companies."""
        self.companies = {c.id: c for c in companies if c.id is not None}
        self._refresh_table()

    def add_or_update_company(self, company: Company):
        """Adds or updates a single company in the live view."""
        if not company.id:
            return
        self.companies[company.id] = company
        self._refresh_table()

    def _refresh_table(self):
        filter_text = self.search_input.text().lower().strip()
        web_filter = self.web_filter.currentText()
        enrich_filter = self.enrich_filter.currentText()
        has_jobs = self.has_jobs_check.isChecked()
        has_emails = self.has_emails_check.isChecked()

        filtered_list = []
        for c in self.companies.values():
            if filter_text:
                combined = f"{c.name} {c.address or ''} {c.website_domain or ''} {c.company_type or ''}".lower()
                if filter_text not in combined:
                    continue

            if web_filter != "All" and c.website_status != web_filter:
                continue

            if enrich_filter != "All" and c.enrichment_status != enrich_filter:
                continue

            if has_jobs and c.job_count <= 0:
                continue

            if has_emails and c.email_count <= 0:
                continue

            filtered_list.append(c)

        # Sort so newest appear predictably
        filtered_list.sort(key=lambda x: x.id or 0, reverse=True)

        self.table.setSortingEnabled(False)
        self.table.setRowCount(len(filtered_list))
        for row_idx, comp in enumerate(filtered_list):
            self._render_row(row_idx, comp)
        self.table.setSortingEnabled(True)

    def _render_row(self, row: int, comp: Company):
        # 0. Row #
        item_id = QTableWidgetItem()
        item_id.setData(Qt.ItemDataRole.DisplayRole, row + 1)
        item_id.setData(Qt.ItemDataRole.UserRole, comp.id)
        item_id.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        self.table.setItem(row, 0, item_id)

        # 1. Company Name
        item_name = QTableWidgetItem(comp.name)
        item_name.setToolTip(comp.name)
        self.table.setItem(row, 1, item_name)

        # 2. Company Type
        item_type = QTableWidgetItem(comp.company_type or "-")
        self.table.setItem(row, 2, item_type)

        # 3. Address
        item_addr = QTableWidgetItem(comp.address or comp.city or "-")
        item_addr.setToolTip(comp.address or comp.city or "")
        self.table.setItem(row, 3, item_addr)

        # 4. Phone
        item_phone = QTableWidgetItem(comp.phone or "-")
        self.table.setItem(row, 4, item_phone)

        # 5. Website Domain
        display_web = comp.website_domain or (comp.website_url or "-")
        if display_web.startswith("http://") or display_web.startswith("https://"):
            display_web = display_web.split("//")[-1].split("/")[0]
        item_web = QTableWidgetItem(display_web)
        item_web.setToolTip(comp.website_url or "No URL")
        self.table.setItem(row, 5, item_web)

        # 6. Rating
        rating_val = comp.rating or 0.0
        rating_str = f"⭐ {comp.rating:.1f}" if comp.rating else "-"
        item_rating = QTableWidgetItem()
        item_rating.setData(Qt.ItemDataRole.DisplayRole, rating_str)
        item_rating.setData(Qt.ItemDataRole.UserRole, rating_val)
        item_rating.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        self.table.setItem(row, 6, item_rating)

        # 7. Website Status Badge
        lbl_web_status = QLabel(comp.website_status)
        lbl_web_status.setStyleSheet(get_status_badge_style(comp.website_status))
        lbl_web_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.table.setCellWidget(row, 7, lbl_web_status)

        # 8. Jobs Count Badge
        lbl_jobs = QLabel(f"💼 {comp.job_count}")
        lbl_jobs.setStyleSheet("font-weight: 700; color: #38BDF8; padding: 2px 6px;")
        lbl_jobs.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.table.setCellWidget(row, 8, lbl_jobs)

        # 9. Emails Count Badge
        lbl_emails = QLabel(f"✉️ {comp.email_count}")
        lbl_emails.setStyleSheet("font-weight: 700; color: #34D399; padding: 2px 6px;")
        lbl_emails.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.table.setCellWidget(row, 9, lbl_emails)

        # 10. Enrichment Status Badge
        lbl_enrich = QLabel(comp.enrichment_status)
        lbl_enrich.setStyleSheet(get_status_badge_style(comp.enrichment_status))
        lbl_enrich.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.table.setCellWidget(row, 10, lbl_enrich)

    def _apply_filters(self):
        self._refresh_table()

    def _on_row_double_clicked(self, index):
        row = index.row()
        item = self.table.item(row, 0)
        if item:
            comp_id = item.data(Qt.ItemDataRole.UserRole)
            if comp_id:
                self.company_selected.emit(comp_id)

    def _show_context_menu(self, pos):
        item = self.table.itemAt(pos)
        if not item:
            return
        row = item.row()
        item_0 = self.table.item(row, 0)
        if not item_0:
            return
        comp_id = item_0.data(Qt.ItemDataRole.UserRole)
        comp = self.companies.get(comp_id)
        if not comp:
            return

        menu = QMenu(self)
        menu.setStyleSheet("background-color: #1E293B; color: #F8FAFC; border: 1px solid #334155; padding: 4px;")

        action_details = menu.addAction("🔍  View Full Company Details")
        action_details.triggered.connect(lambda: self.company_selected.emit(comp_id))

        if comp.website_url:
            action_web = menu.addAction("🌐  Open Website in Browser")
            action_web.triggered.connect(lambda: webbrowser.open(comp.website_url))

        if comp.career_url:
            action_career = menu.addAction("💼  Open Career Portal")
            action_career.triggered.connect(lambda: webbrowser.open(comp.career_url))

        if comp.maps_url:
            action_maps = menu.addAction("🗺️  Open Google Maps")
            action_maps.triggered.connect(lambda: webbrowser.open(comp.maps_url))

        menu.exec(self.table.viewport().mapToGlobal(pos))
