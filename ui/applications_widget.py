"""
Applications Tracker dashboard widget displaying application pipeline, status badges, activity logs, and dispatch actions.
"""

import webbrowser
from typing import List, Optional
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QComboBox, QPushButton, QTableWidget, QTableWidgetItem,
    QHeaderView, QFrame, QAbstractItemView, QMessageBox,
    QMenu, QDialog, QTextEdit
)
from PyQt6.QtCore import Qt, pyqtSignal
from database.models import JobApplication
from database.repositories import ApplicationsRepository
from browser.email_automation import EmailAutomationService
from ui.styles import get_status_badge_style, get_relevance_badge_style
from utils.logger import get_logger

logger = get_logger("applications_widget")


class ActivityLogDialog(QDialog):
    """Modal displaying timeline log and notes for a job application."""

    def __init__(self, app: JobApplication, parent=None):
        super().__init__(parent)
        self.app = app
        self.setWindowTitle(f"Application Activity Log: {app.job_title or 'Job'}")
        self.resize(550, 400)
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(10)

        # Header Info
        header = QFrame()
        header.setObjectName("compactCard")
        h_layout = QVBoxLayout(header)
        h_layout.addWidget(QLabel(f"<b>Job:</b> {self.app.job_title}"))
        h_layout.addWidget(QLabel(f"<b>Company:</b> {self.app.company_name}"))
        h_layout.addWidget(QLabel(f"<b>HR Email:</b> {self.app.hr_email or 'Not specified'}"))
        layout.addWidget(header)

        layout.addWidget(QLabel("<b>Activity Timeline:</b>"))
        log_box = QTextEdit()
        log_box.setReadOnly(True)
        log_box.setText(self.app.activity_log or "No activity logs recorded.")
        layout.addWidget(log_box, 1)

        close_btn = QPushButton("Close")
        close_btn.setObjectName("btnAction")
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn, alignment=Qt.AlignmentFlag.AlignRight)


class ApplicationsWidget(QWidget):
    """Interactive table view for tracking submitted and draft job applications."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.apps_repo = ApplicationsRepository()
        self.applications_data: List[JobApplication] = []
        self._init_ui()

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(14, 12, 14, 10)
        main_layout.setSpacing(8)

        # 1. Header Card
        header = QFrame()
        header.setObjectName("compactCard")
        h_layout = QHBoxLayout(header)
        h_layout.setContentsMargins(12, 8, 12, 8)

        title = QLabel("AI Job Applications & Outreach Pipeline")
        title.setObjectName("sectionTitle")
        h_layout.addWidget(title)
        h_layout.addStretch(1)

        refresh_btn = QPushButton("🔄 Refresh")
        refresh_btn.setObjectName("btnAction")
        refresh_btn.clicked.connect(self.reload_applications)
        h_layout.addWidget(refresh_btn)
        main_layout.addWidget(header)

        # 2. Filter Bar
        filter_frame = QFrame()
        filter_frame.setObjectName("compactCard")
        f_layout = QHBoxLayout(filter_frame)
        f_layout.setContentsMargins(10, 6, 10, 6)
        f_layout.setSpacing(8)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("🔎 Filter by job title, company, or HR email...")
        self.search_input.textChanged.connect(self._filter_table)
        f_layout.addWidget(self.search_input, 2)

        f_layout.addWidget(QLabel("Status:"))
        self.status_filter = QComboBox()
        self.status_filter.addItems(["All", "DRAFT", "READY_TO_SEND", "BROWSER_OPENED", "SENT", "INTERVIEW", "REJECTED"])
        self.status_filter.currentTextChanged.connect(self._filter_table)
        f_layout.addWidget(self.status_filter)

        f_layout.addStretch(1)
        main_layout.addWidget(filter_frame)

        # 3. Table
        self.table = QTableWidget()
        self.table.setColumnCount(8)
        self.table.setHorizontalHeaderLabels([
            "Job Title", "Company", "HR Recipient", "Match Score", "Status", "Updated At", "Resume", "Actions"
        ])
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.setSortingEnabled(True)

        header_view = self.table.horizontalHeader()
        header_view.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header_view.setSectionResizeMode(1, QHeaderView.ResizeMode.Interactive)
        header_view.setSectionResizeMode(2, QHeaderView.ResizeMode.Interactive)
        header_view.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        header_view.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        header_view.setSectionResizeMode(5, QHeaderView.ResizeMode.Interactive)
        header_view.setSectionResizeMode(6, QHeaderView.ResizeMode.Interactive)
        header_view.setSectionResizeMode(7, QHeaderView.ResizeMode.ResizeToContents)

        self.table.setColumnWidth(1, 160)
        self.table.setColumnWidth(2, 180)
        self.table.setColumnWidth(5, 130)
        self.table.setColumnWidth(6, 140)

        main_layout.addWidget(self.table, 1)

    def reload_applications(self):
        """Fetches all applications from DB and repopulates the table."""
        self.applications_data = self.apps_repo.get_all_applications(limit=500)
        self._filter_table()

    def _filter_table(self):
        search_kw = self.search_input.text().lower().strip()
        status_sel = self.status_filter.currentText()

        filtered = []
        for app in self.applications_data:
            if search_kw:
                combined = f"{app.job_title or ''} {app.company_name or ''} {app.hr_email or ''}".lower()
                if search_kw not in combined:
                    continue

            if status_sel != "All" and (app.status or "").upper() != status_sel.upper():
                continue

            filtered.append(app)

        self.table.setSortingEnabled(False)
        self.table.setRowCount(len(filtered))

        for row, app in enumerate(filtered):
            # 0. Job Title
            item_title = QTableWidgetItem(app.job_title or "Position")
            item_title.setData(Qt.ItemDataRole.UserRole, app)
            self.table.setItem(row, 0, item_title)

            # 1. Company
            item_comp = QTableWidgetItem(app.company_name or "-")
            self.table.setItem(row, 1, item_comp)

            # 2. HR Email
            item_email = QTableWidgetItem(app.hr_email or "-")
            self.table.setItem(row, 2, item_email)

            # 3. Match Score
            score_lbl = QLabel(f"{app.match_score}%")
            score_lbl.setStyleSheet(get_relevance_badge_style(app.match_score))
            score_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setCellWidget(row, 3, score_lbl)

            # 4. Status Badge
            status_lbl = QLabel(app.status or "DRAFT")
            status_lbl.setStyleSheet(get_status_badge_style(app.status or "DRAFT"))
            status_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setCellWidget(row, 4, status_lbl)

            # 5. Updated At
            time_display = app.applied_at or app.updated_at or app.created_at
            item_time = QTableWidgetItem(time_display[:16] if time_display else "-")
            item_time.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(row, 5, item_time)

            # 6. Resume
            item_resume = QTableWidgetItem(app.resume_name or "Default")
            self.table.setItem(row, 6, item_resume)

            # 7. Action Buttons Container
            btn_container = QWidget()
            btn_layout = QHBoxLayout(btn_container)
            btn_layout.setContentsMargins(2, 2, 2, 2)
            btn_layout.setSpacing(4)

            # Re-open in Chrome
            open_btn = QPushButton("🚀 Send")
            open_btn.setObjectName("btnPrimary")
            open_btn.setFixedHeight(24)
            open_btn.clicked.connect(lambda checked=False, a=app: self._open_application_in_chrome(a))
            btn_layout.addWidget(open_btn)

            # Status Menu
            status_btn = QPushButton("⚙️ Status")
            status_btn.setObjectName("btnAction")
            status_btn.setFixedHeight(24)
            status_btn.clicked.connect(lambda checked=False, a=app, b=status_btn: self._show_status_menu(a, b))
            btn_layout.addWidget(status_btn)

            # Activity Log
            log_btn = QPushButton("📜 Log")
            log_btn.setObjectName("btnAction")
            log_btn.setFixedHeight(24)
            log_btn.clicked.connect(lambda checked=False, a=app: self._show_activity_log(a))
            btn_layout.addWidget(log_btn)

            self.table.setCellWidget(row, 7, btn_container)

        self.table.setSortingEnabled(True)

    def _open_application_in_chrome(self, app: JobApplication):
        """Re-opens webmail compose for this application."""
        if not app.hr_email:
            QMessageBox.warning(self, "Missing HR Email", "Please update the application with an HR email first.")
            return

        EmailAutomationService.open_in_chrome_webmail(
            to_email=app.hr_email,
            subject=app.subject or f"Application for {app.job_title}",
            body=app.email_body or "",
            provider="gmail"
        )
        self.apps_repo.update_status(app.id, "BROWSER_OPENED", "Re-opened application in Chrome")
        self.reload_applications()

    def _show_status_menu(self, app: JobApplication, button: QPushButton):
        """Displays popup menu to quickly update application status."""
        menu = QMenu(self)
        statuses = ["DRAFT", "READY_TO_SEND", "BROWSER_OPENED", "SENT", "INTERVIEW", "REJECTED"]
        for st in statuses:
            action = menu.addAction(f"Mark as {st}")
            action.triggered.connect(lambda checked=False, s=st: self._update_app_status(app, s))

        menu.addSeparator()
        delete_action = menu.addAction("🗑️ Delete Application")
        delete_action.triggered.connect(lambda: self._delete_app(app))

        menu.exec(button.mapToGlobal(button.rect().bottomLeft()))

    def _update_app_status(self, app: JobApplication, new_status: str):
        self.apps_repo.update_status(app.id, new_status, f"Status changed to {new_status}")
        self.reload_applications()

    def _delete_app(self, app: JobApplication):
        reply = QMessageBox.question(
            self,
            "Confirm Delete",
            f"Are you sure you want to delete the application for '{app.job_title}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.apps_repo.delete_application(app.id)
            self.reload_applications()

    def _show_activity_log(self, app: JobApplication):
        dialog = ActivityLogDialog(app, self)
        dialog.exec()
