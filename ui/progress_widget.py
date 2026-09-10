"""
Real-time inline progress bar and status indicator for search workflows.
"""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QProgressBar, QFrame, QSizePolicy
)
from PyQt6.QtCore import Qt, pyqtSlot
from database.models import Company


class ProgressWidget(QWidget):
    """Compact inline progress bar and live telemetry for ongoing searches."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.companies_found = 0
        self.companies_enriched = 0
        self.jobs_found = 0
        self.emails_found = 0
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 2, 14, 4)
        layout.setSpacing(4)

        # Single compact row: Progress bar + Live status info
        row = QHBoxLayout()
        row.setSpacing(10)

        # Progress bar (slim, loading line)
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setFormat("%p%")
        self.progress_bar.setFixedHeight(16)
        row.addWidget(self.progress_bar, 2)

        # Live metric badges
        self.status_detail_label = QLabel("Ready")
        self.status_detail_label.setStyleSheet("color: #38BDF8; font-size: 11px; font-weight: 600;")
        row.addWidget(self.status_detail_label, 1)

        self.stats_badge = QLabel("Companies: 0 | Jobs: 0 | Emails: 0")
        self.stats_badge.setStyleSheet("color: #94A3B8; font-size: 11px; font-weight: 500;")
        row.addWidget(self.stats_badge)

        layout.addLayout(row)

    def reset_progress(self):
        self.progress_bar.setValue(0)
        self.companies_found = 0
        self.companies_enriched = 0
        self.jobs_found = 0
        self.emails_found = 0
        self._update_badges()
        self.status_detail_label.setText("Starting search...")

    def _update_badges(self):
        self.stats_badge.setText(f"Companies: {self.companies_found} | Jobs: {self.jobs_found} | Emails: {self.emails_found}")

    def update_progress(self, current: int, total: int, status_text: str):
        if total > 0:
            pct = int((current / total) * 100)
            self.progress_bar.setValue(min(100, pct))
        self.status_detail_label.setText(status_text)

    def on_company_found(self, comp: Company):
        self.companies_found += 1
        self._update_badges()
        self.status_detail_label.setText(f"Found: {comp.name}")

    def on_company_enriched(self, comp: Company):
        self.companies_enriched += 1
        self.jobs_found += comp.job_count
        self.emails_found += comp.email_count
        self._update_badges()
        self.status_detail_label.setText(f"Enriched: {comp.name}")

    def on_step_updated(self, comp: Company, step: str, details: str):
        self.status_detail_label.setText(f"{comp.name} → {step}")
