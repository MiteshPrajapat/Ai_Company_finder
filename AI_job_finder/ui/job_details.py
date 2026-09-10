"""
Job details modal dialog displaying full description, multi-source links, skills, requirements, and apply actions.
"""

import webbrowser
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QTextEdit,
    QPushButton, QFrame, QGridLayout, QScrollArea, QWidget
)
from PyQt6.QtCore import Qt
from database.models import Job, JobSource
from ui.styles import get_relevance_badge_style, get_source_badge_style
from utils.text_utils import clean_location_display, format_employment_type


class JobDetailsDialog(QDialog):
    """Modal displaying complete unified job posting with multi-source listings."""

    def __init__(self, job: Job, parent=None):
        super().__init__(parent)
        self.job = job
        self.setWindowTitle(f"Job Opening: {job.title}")
        self.resize(750, 580)
        self.setMinimumSize(600, 460)
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(12)

        # Header Frame
        header_frame = QFrame()
        header_frame.setObjectName("cardFrame")
        h_layout = QVBoxLayout(header_frame)
        h_layout.setContentsMargins(16, 12, 16, 12)
        h_layout.setSpacing(8)

        # Title & Relevance Score
        top_row = QHBoxLayout()
        title_lbl = QLabel(self.job.title)
        title_lbl.setObjectName("headerTitle")
        title_lbl.setWordWrap(True)

        score_lbl = QLabel(f"Relevance: {self.job.relevance_score}%")
        score_lbl.setStyleSheet(get_relevance_badge_style(self.job.relevance_score))
        score_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)

        top_row.addWidget(title_lbl, 4)
        top_row.addStretch()
        top_row.addWidget(score_lbl, 1)
        h_layout.addLayout(top_row)

        # Company name subtitle
        if self.job.company_name:
            comp_lbl = QLabel(f"🏢  {self.job.company_name}")
            comp_lbl.setStyleSheet("font-size: 13px; font-weight: 600; color: #38BDF8;")
            h_layout.addWidget(comp_lbl)

        # Metadata Grid
        grid = QGridLayout()
        grid.setSpacing(8)

        grid.addWidget(QLabel("<b>📍 Location:</b>"), 0, 0)
        clean_loc = clean_location_display(self.job.location)
        grid.addWidget(QLabel(clean_loc), 0, 1)

        grid.addWidget(QLabel("<b>⏱ Type:</b>"), 0, 2)
        clean_type = format_employment_type(self.job.employment_type)
        grid.addWidget(QLabel(clean_type), 0, 3)

        grid.addWidget(QLabel("<b>💼 Work Mode:</b>"), 1, 0)
        grid.addWidget(QLabel(self.job.work_mode or self.job.remote_type or "On-site / Unspecified"), 1, 1)

        grid.addWidget(QLabel("<b>💰 Salary:</b>"), 1, 2)
        grid.addWidget(QLabel(self.job.salary or "Not disclosed"), 1, 3)

        h_layout.addLayout(grid)

        # Extracted Skills Tag Row
        if self.job.skills:
            skills_row = QHBoxLayout()
            skills_row.setSpacing(6)
            skills_row.addWidget(QLabel("<b>🏷 Skills:</b>"))
            for sk in self.job.skills[:8]:
                badge = QLabel(sk)
                badge.setStyleSheet("background-color: #0F172A; color: #38BDF8; border: 1px solid #0284C7; padding: 2px 6px; border-radius: 4px; font-size: 10px; font-weight: 600;")
                skills_row.addWidget(badge)
            skills_row.addStretch()
            h_layout.addLayout(skills_row)

        layout.addWidget(header_frame)

        # Multi-Source Availability Section
        sources_frame = QFrame()
        sources_frame.setObjectName("compactCard")
        sf_layout = QVBoxLayout(sources_frame)
        sf_layout.setContentsMargins(14, 10, 14, 10)
        sf_layout.setSpacing(8)

        sf_title_row = QHBoxLayout()
        sf_title_row.addWidget(QLabel("<b>🌐 Available On Job Sources:</b>"))
        sf_title_row.addStretch()
        sf_layout.addLayout(sf_title_row)

        # List all sources with direct Apply buttons
        sources_list = self.job.sources if self.job.sources else []
        if not sources_list and self.job.job_url:
            sources_list = [JobSource(job_id=self.job.id or 0, source=self.job.source or "career_portal", source_url=self.job.job_url, is_primary=True)]

        src_grid = QGridLayout()
        src_grid.setSpacing(6)

        for idx, src in enumerate(sources_list):
            src_name = src.source.replace("_", " ").title()
            badge = QLabel(src_name)
            badge.setStyleSheet(get_source_badge_style(src.source))
            src_grid.addWidget(badge, idx, 0)

            # URL snippet
            url_snippet = src.source_url[:55] + "..." if len(src.source_url) > 55 else src.source_url
            url_lbl = QLabel(url_snippet)
            url_lbl.setStyleSheet("color: #94A3B8; font-size: 11px;")
            url_lbl.setToolTip(src.source_url)
            src_grid.addWidget(url_lbl, idx, 1)

            # Direct Apply / View button for each source
            btn_text = "⭐ View Primary" if src.is_primary else f"↗ Apply on {src_name}"
            btn = QPushButton(btn_text)
            btn.setObjectName("btnPrimary" if src.is_primary else "btnAction")
            btn.setFixedHeight(26)
            btn.clicked.connect(lambda checked=False, u=src.source_url: webbrowser.open(u))
            src_grid.addWidget(btn, idx, 2)

        sf_layout.addLayout(src_grid)
        layout.addWidget(sources_frame)

        # Description / Content Frame
        desc_frame = QFrame()
        desc_frame.setObjectName("cardFrame")
        desc_layout = QVBoxLayout(desc_frame)
        desc_layout.setContentsMargins(14, 10, 14, 10)
        desc_layout.setSpacing(6)

        desc_layout.addWidget(QLabel("<b>Job Description & Requirements:</b>"))
        self.desc_text = QTextEdit()
        self.desc_text.setReadOnly(True)
        content = self.job.description or self.job.requirements or "No detailed description available."
        self.desc_text.setText(content)
        desc_layout.addWidget(self.desc_text)
        layout.addWidget(desc_frame, 1)

        # Actions Row
        action_row = QHBoxLayout()
        action_row.addStretch()

        if self.job.job_url:
            open_btn = QPushButton("🌐  Open Primary Link in Browser")
            open_btn.setObjectName("btnPrimary")
            open_btn.clicked.connect(lambda: webbrowser.open(self.job.job_url))
            action_row.addWidget(open_btn)

        close_btn = QPushButton("Close")
        close_btn.setObjectName("btnAction")
        close_btn.setMinimumWidth(80)
        close_btn.clicked.connect(self.accept)
        action_row.addWidget(close_btn)
        layout.addLayout(action_row)
