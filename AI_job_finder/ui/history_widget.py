"""
Search history browser widget with details preview card, reload and resume capabilities.
"""

from typing import Optional, Dict, Any
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QTableWidget,
    QTableWidgetItem, QPushButton, QHeaderView, QFrame,
    QAbstractItemView, QSplitter, QSizePolicy
)
from PyQt6.QtCore import pyqtSignal, Qt
from database.repositories import SearchesRepository, CompaniesRepository
from database.models import SearchSession
from ui.styles import get_status_badge_style


class HistoryWidget(QWidget):
    """View presenting past searches and detailed metrics preview."""

    load_search_requested = pyqtSignal(int)   # search_id
    resume_search_requested = pyqtSignal(int) # search_id

    def __init__(self, parent=None):
        super().__init__(parent)
        self.searches_repo = SearchesRepository()
        self.companies_repo = CompaniesRepository()
        self.records: Dict[int, Dict[str, Any]] = {}
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(10)

        # Header Frame
        header_frame = QFrame()
        header_frame.setObjectName("compactCard")
        h_layout = QHBoxLayout(header_frame)
        h_layout.setContentsMargins(14, 10, 14, 10)

        title = QLabel("Search History & Execution Sessions")
        title.setObjectName("sectionTitle")
        h_layout.addWidget(title)
        h_layout.addStretch()

        refresh_btn = QPushButton("🔄 Refresh History")
        refresh_btn.setObjectName("btnAction")
        refresh_btn.clicked.connect(self.reload_history)
        h_layout.addWidget(refresh_btn)

        layout.addWidget(header_frame)

        # Main splitter (Table + Details Side Card)
        splitter = QSplitter(Qt.Orientation.Vertical)
        splitter.setChildrenCollapsible(False)

        # Table
        self.table = QTableWidget()
        self.table.setColumnCount(8)
        self.table.setHorizontalHeaderLabels([
            "ID", "Date", "Location", "Profession", "Company Type",
            "Results", "Status", "Action"
        ])
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.itemSelectionChanged.connect(self._on_selection_changed)
        self.table.setSortingEnabled(True)

        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(6, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(7, QHeaderView.ResizeMode.ResizeToContents)

        self.table.setColumnWidth(1, 140)
        self.table.setColumnWidth(3, 160)
        self.table.setColumnWidth(4, 150)

        splitter.addWidget(self.table)

        # Details Panel
        self.details_card = QFrame()
        self.details_card.setObjectName("cardFrame")
        det_layout = QVBoxLayout(self.details_card)
        det_layout.setContentsMargins(14, 10, 14, 10)
        det_layout.setSpacing(6)

        det_header = QHBoxLayout()
        self.det_title = QLabel("Session Details: Select a row to inspect")
        self.det_title.setStyleSheet("font-weight: 700; color: #38BDF8; font-size: 12px;")
        det_header.addWidget(self.det_title)
        det_header.addStretch()

        self.det_view_btn = QPushButton("🔍 Load in Results View")
        self.det_view_btn.setObjectName("btnPrimary")
        self.det_view_btn.setEnabled(False)
        self.det_view_btn.clicked.connect(self._load_selected_session)
        det_header.addWidget(self.det_view_btn)

        self.det_resume_btn = QPushButton("▶ Resume Enrichment")
        self.det_resume_btn.setObjectName("btnSuccess")
        self.det_resume_btn.setEnabled(False)
        self.det_resume_btn.clicked.connect(self._resume_selected_session)
        det_header.addWidget(self.det_resume_btn)

        det_layout.addLayout(det_header)

        self.det_info_label = QLabel("Click on any past search session above to inspect full parameters, counts, and timestamps.")
        self.det_info_label.setStyleSheet("color: #94A3B8; font-size: 11px;")
        self.det_info_label.setWordWrap(True)
        det_layout.addWidget(self.det_info_label)

        splitter.addWidget(self.details_card)
        splitter.setStretchFactor(0, 4)
        splitter.setStretchFactor(1, 1)

        layout.addWidget(splitter, 1)
        self.reload_history()

    def reload_history(self):
        """Fetches history records from database."""
        raw_records = self.searches_repo.get_all(limit=100)
        self.records = {r["id"]: r for r in raw_records}
        self.table.setSortingEnabled(False)
        self.table.setRowCount(len(raw_records))

        for row, rec in enumerate(raw_records):
            search_id = rec["id"]

            item_id = QTableWidgetItem(f"#{search_id}")
            item_id.setData(Qt.ItemDataRole.UserRole, search_id)
            item_id.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(row, 0, item_id)

            self.table.setItem(row, 1, QTableWidgetItem(rec.get("created_at") or "-"))

            loc = f"{rec.get('city') or ''}, {rec.get('state') or ''}, {rec.get('country') or ''}".strip(", ")
            self.table.setItem(row, 2, QTableWidgetItem(loc or "-"))

            prof = rec.get("custom_profession") or rec.get("profession") or "-"
            self.table.setItem(row, 3, QTableWidgetItem(prof))

            comp_type = rec.get("custom_company_type") or rec.get("company_type") or "-"
            self.table.setItem(row, 4, QTableWidgetItem(comp_type))

            stats_str = f"🏢 {rec.get('company_count', 0)}  💼 {rec.get('job_count', 0)}  ✉️ {rec.get('email_count', 0)}"
            item_res = QTableWidgetItem(stats_str)
            item_res.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(row, 5, item_res)

            status_lbl = QLabel(rec.get("status") or "COMPLETED")
            status_lbl.setStyleSheet(get_status_badge_style(rec.get("status") or "COMPLETED"))
            status_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setCellWidget(row, 6, status_lbl)

            # Actions Button Group
            btn_frame = QWidget()
            btn_layout = QHBoxLayout(btn_frame)
            btn_layout.setContentsMargins(4, 2, 4, 2)
            btn_layout.setSpacing(6)

            load_btn = QPushButton("View")
            load_btn.setObjectName("btnAction")
            load_btn.clicked.connect(lambda checked=False, sid=search_id: self.load_search_requested.emit(sid))
            btn_layout.addWidget(load_btn)

            self.table.setCellWidget(row, 7, btn_frame)

        self.table.setSortingEnabled(True)

    def _on_selection_changed(self):
        selected_rows = self.table.selectionModel().selectedRows()
        if not selected_rows:
            self.det_view_btn.setEnabled(False)
            self.det_resume_btn.setEnabled(False)
            return

        row = selected_rows[0].row()
        item_0 = self.table.item(row, 0)
        if not item_0:
            return
        search_id = item_0.data(Qt.ItemDataRole.UserRole)
        rec = self.records.get(search_id)
        if not rec:
            return

        self.selected_search_id = search_id
        self.det_view_btn.setEnabled(True)
        self.det_resume_btn.setEnabled(True)

        self.det_title.setText(f"Session #{search_id} — {rec.get('city')}, {rec.get('profession')} ({rec.get('company_type')})")
        
        info_lines = [
            f"<b>Location:</b> {rec.get('city')}, {rec.get('state')}, {rec.get('country')}",
            f"<b>Profession:</b> {rec.get('custom_profession') or rec.get('profession')}",
            f"<b>Company Type:</b> {rec.get('custom_company_type') or rec.get('company_type')}",
            f"<b>Result Limit:</b> {rec.get('result_limit')}",
            f"<b>Enrichment Enabled:</b> {'Yes' if rec.get('enrich_enabled') else 'No'}",
            f"<b>Auto Browser:</b> {'Yes' if rec.get('auto_browser') else 'No'}",
            f"<b>Companies Found:</b> {rec.get('company_count', 0)} | <b>Jobs:</b> {rec.get('job_count', 0)} | <b>Emails:</b> {rec.get('email_count', 0)}",
            f"<b>Session Created:</b> {rec.get('created_at')} | <b>Status:</b> {rec.get('status')}"
        ]
        self.det_info_label.setText("  •  ".join(info_lines))

    def _load_selected_session(self):
        if hasattr(self, "selected_search_id") and self.selected_search_id:
            self.load_search_requested.emit(self.selected_search_id)

    def _resume_selected_session(self):
        if hasattr(self, "selected_search_id") and self.selected_search_id:
            self.resume_search_requested.emit(self.selected_search_id)
