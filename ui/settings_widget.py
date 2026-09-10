"""
Settings & Configuration view for OpenRouter AI, Resume Management, Candidate Profile, and Scraper parameters.
"""

import os
import shutil
from pathlib import Path
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel,
    QComboBox, QCheckBox, QSpinBox, QDoubleSpinBox, QPushButton,
    QFrame, QMessageBox, QTabWidget, QLineEdit, QFileDialog,
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView,
    QDialog, QTextEdit
)
from PyQt6.QtCore import Qt
from config.settings import settings, RESUMES_DIR
from database.models import Resume
from database.repositories import ResumesRepository
from core.ai.openrouter_client import OpenRouterClient, POPULAR_MODELS
from core.ai.resume_extractor import ResumeExtractor
from ui.styles import get_status_badge_style
from utils.logger import get_logger

logger = get_logger("settings_widget")


class ResumePreviewDialog(QDialog):
    """Modal to view parsed resume plain text."""

    def __init__(self, resume: Resume, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Resume Text Preview: {resume.name}")
        self.resize(650, 500)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(10)

        header = QLabel(f"📄 <b>{resume.name}</b> (Uploaded: {resume.created_at})")
        header.setStyleSheet("color: #38BDF8; font-size: 13px;")
        layout.addWidget(header)

        text_edit = QTextEdit()
        text_edit.setReadOnly(True)
        text_edit.setText(resume.extracted_text or "No extracted text found.")
        layout.addWidget(text_edit, 1)

        close_btn = QPushButton("Close")
        close_btn.setObjectName("btnAction")
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn, alignment=Qt.AlignmentFlag.AlignRight)


class SettingsWidget(QWidget):
    """Unified application settings panel with tabs for AI, Resumes, Candidate Profile, and Scraper."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.resumes_repo = ResumesRepository()
        self._init_ui()

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(16, 14, 16, 14)
        main_layout.setSpacing(12)

        title = QLabel("System Settings & Configuration")
        title.setObjectName("sectionTitle")
        main_layout.addWidget(title)

        # Tab Widget
        self.tabs = QTabWidget()
        self.tabs.addTab(self._create_ai_tab(), "🤖 AI & OpenRouter")
        self.tabs.addTab(self._create_resumes_tab(), "📄 Resume Management")
        self.tabs.addTab(self._create_profile_tab(), "👤 Candidate Profile")
        self.tabs.addTab(self._create_scraper_tab(), "⚙️ Scraper & Browser")
        main_layout.addWidget(self.tabs, 1)

        # Bottom Global Save Button Row
        bottom_bar = QHBoxLayout()
        bottom_bar.addStretch(1)

        save_all_btn = QPushButton("💾  Save All Settings")
        save_all_btn.setObjectName("btnPrimary")
        save_all_btn.setFixedHeight(32)
        save_all_btn.clicked.connect(self._save_all_settings)
        bottom_bar.addWidget(save_all_btn)

        main_layout.addLayout(bottom_bar)

    # -------------------------------------------------------------
    # Tab 1: AI & OpenRouter Settings
    # -------------------------------------------------------------
    def _create_ai_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(12)

        card = QFrame()
        card.setObjectName("cardFrame")
        c_layout = QVBoxLayout(card)
        c_layout.setContentsMargins(16, 14, 16, 14)
        c_layout.setSpacing(12)

        desc = QLabel("Configure your OpenRouter API key and preferred AI model for job analysis & email generation.")
        desc.setStyleSheet("color: #94A3B8; font-size: 11px;")
        c_layout.addWidget(desc)

        grid = QGridLayout()
        grid.setHorizontalSpacing(14)
        grid.setVerticalSpacing(10)

        cfg = settings.get_config()

        # OpenRouter API Key
        grid.addWidget(QLabel("<b>OpenRouter API Key:</b>"), 0, 0)
        key_layout = QHBoxLayout()
        self.api_key_input = QLineEdit()
        self.api_key_input.setPlaceholderText("sk-or-v1-xxxxxxxxxxxxxxxxxxxx")
        self.api_key_input.setText(cfg.openrouter_api_key)
        self.api_key_input.setEchoMode(QLineEdit.EchoMode.Password)
        key_layout.addWidget(self.api_key_input, 1)

        self.show_key_btn = QPushButton("👁️")
        self.show_key_btn.setFixedWidth(36)
        self.show_key_btn.setObjectName("btnAction")
        self.show_key_btn.clicked.connect(self._toggle_api_key_visibility)
        key_layout.addWidget(self.show_key_btn)

        self.test_key_btn = QPushButton("🔌 Test Connection")
        self.test_key_btn.setObjectName("btnAction")
        self.test_key_btn.clicked.connect(self._test_openrouter_connection)
        key_layout.addWidget(self.test_key_btn)

        grid.addLayout(key_layout, 0, 1)

        # AI Model Dropdown
        grid.addWidget(QLabel("<b>AI Model:</b>"), 1, 0)
        self.model_combo = QComboBox()
        self.model_combo.setEditable(True)
        for model_id, model_name in POPULAR_MODELS:
            self.model_combo.addItem(f"{model_name} ({model_id})", model_id)
        
        # Select current model
        matched_idx = -1
        for i in range(self.model_combo.count()):
            if self.model_combo.itemData(i) == cfg.openrouter_model:
                matched_idx = i
                break
        if matched_idx >= 0:
            self.model_combo.setCurrentIndex(matched_idx)
        else:
            self.model_combo.setEditText(cfg.openrouter_model)
        grid.addWidget(self.model_combo, 1, 1)

        # Default Email Tone
        grid.addWidget(QLabel("<b>Default Email Tone:</b>"), 2, 0)
        self.tone_combo = QComboBox()
        self.tone_combo.addItems([
            "Professional & Concise",
            "Confident & High-Impact",
            "Enthusiastic & Friendly",
            "Formal & Executive",
            "Direct & Technical"
        ])
        self.tone_combo.setCurrentText(cfg.email_tone)
        grid.addWidget(self.tone_combo, 2, 1)

        # Auto-detect HR Email
        grid.addWidget(QLabel("<b>HR Email Preference:</b>"), 3, 0)
        self.auto_hr_check = QCheckBox("Automatically detect and pre-fill HR / Recruiter emails")
        self.auto_hr_check.setChecked(cfg.auto_detect_hr_email)
        grid.addWidget(self.auto_hr_check, 3, 1)

        c_layout.addLayout(grid)

        # Status feedback label
        self.ai_status_lbl = QLabel("")
        self.ai_status_lbl.setStyleSheet("font-weight: 600; font-size: 11px;")
        c_layout.addWidget(self.ai_status_lbl)

        layout.addWidget(card)
        layout.addStretch(1)
        return widget

    def _toggle_api_key_visibility(self):
        if self.api_key_input.echoMode() == QLineEdit.EchoMode.Password:
            self.api_key_input.setEchoMode(QLineEdit.EchoMode.Normal)
            self.show_key_btn.setText("🔒")
        else:
            self.api_key_input.setEchoMode(QLineEdit.EchoMode.Password)
            self.show_key_btn.setText("👁️")

    def _test_openrouter_connection(self):
        key = self.api_key_input.text().strip()
        if not key:
            QMessageBox.warning(self, "API Key Missing", "Please enter your OpenRouter API key first.")
            return

        self.ai_status_lbl.setText("⏳ Testing OpenRouter connection...")
        self.ai_status_lbl.setStyleSheet("color: #38BDF8;")
        client = OpenRouterClient(api_key=key)
        res = client.test_connection()
        if res.get("success"):
            self.ai_status_lbl.setText("✅ " + res.get("message", "Connected successfully!"))
            self.ai_status_lbl.setStyleSheet("color: #34D399;")
            QMessageBox.information(self, "Connection Successful", "OpenRouter API Key is valid and active!")
        else:
            err = res.get("error", "Failed to connect.")
            self.ai_status_lbl.setText("❌ " + err)
            self.ai_status_lbl.setStyleSheet("color: #F87171;")
            QMessageBox.critical(self, "Connection Failed", f"OpenRouter Connection Error:\n{err}")

    # -------------------------------------------------------------
    # Tab 2: Resume Management
    # -------------------------------------------------------------
    def _create_resumes_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(10)

        # Top Action Bar
        top_row = QHBoxLayout()
        desc = QLabel("Manage your resumes (.pdf, .docx, .txt). The default resume will be used for AI job matching.")
        desc.setStyleSheet("color: #94A3B8; font-size: 11px;")
        top_row.addWidget(desc, 1)

        upload_btn = QPushButton("➕ Upload Resume")
        upload_btn.setObjectName("btnPrimary")
        upload_btn.clicked.connect(self._upload_resume)
        top_row.addWidget(upload_btn)
        layout.addLayout(top_row)

        # Resumes Table
        self.resumes_table = QTableWidget()
        self.resumes_table.setColumnCount(5)
        self.resumes_table.setHorizontalHeaderLabels([
            "Resume Name", "Status", "Uploaded Date", "File Path", "Actions"
        ])
        self.resumes_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.resumes_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.resumes_table.setAlternatingRowColors(True)
        self.resumes_table.verticalHeader().setVisible(False)

        r_header = self.resumes_table.horizontalHeader()
        r_header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        r_header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        r_header.setSectionResizeMode(2, QHeaderView.ResizeMode.Interactive)
        r_header.setSectionResizeMode(3, QHeaderView.ResizeMode.Interactive)
        r_header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)

        self.resumes_table.setColumnWidth(2, 140)
        self.resumes_table.setColumnWidth(3, 200)

        layout.addWidget(self.resumes_table, 1)
        self._load_resumes_table()
        return widget

    def _load_resumes_table(self):
        resumes = self.resumes_repo.get_all_resumes()
        self.resumes_table.setRowCount(len(resumes))

        for row, r in enumerate(resumes):
            # 0. Name
            item_name = QTableWidgetItem(f"📄 {r.name}")
            item_name.setData(Qt.ItemDataRole.UserRole, r)
            self.resumes_table.setItem(row, 0, item_name)

            # 1. Status (Default Badge)
            if r.is_default:
                status_lbl = QLabel("⭐ Default")
                status_lbl.setStyleSheet("background-color: #064E3B; color: #34D399; font-weight: 700; padding: 2px 6px; border-radius: 4px; border: 1px solid #059669;")
            else:
                status_lbl = QLabel("Alternative")
                status_lbl.setStyleSheet("color: #94A3B8; font-size: 11px;")
            status_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.resumes_table.setCellWidget(row, 1, status_lbl)

            # 2. Date
            item_date = QTableWidgetItem(r.created_at[:10] if r.created_at else "-")
            item_date.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.resumes_table.setItem(row, 2, item_date)

            # 3. Path
            item_path = QTableWidgetItem(r.file_path)
            item_path.setToolTip(r.file_path)
            self.resumes_table.setItem(row, 3, item_path)

            # 4. Actions
            btn_box = QWidget()
            btn_layout = QHBoxLayout(btn_box)
            btn_layout.setContentsMargins(2, 2, 2, 2)
            btn_layout.setSpacing(4)

            # Set Default
            if not r.is_default:
                def_btn = QPushButton("⭐ Set Default")
                def_btn.setObjectName("btnAction")
                def_btn.setFixedHeight(24)
                def_btn.clicked.connect(lambda checked=False, rid=r.id: self._set_default_resume(rid))
                btn_layout.addWidget(def_btn)

            # Preview Text
            view_btn = QPushButton("👁️ View")
            view_btn.setObjectName("btnAction")
            view_btn.setFixedHeight(24)
            view_btn.clicked.connect(lambda checked=False, res=r: self._preview_resume(res))
            btn_layout.addWidget(view_btn)

            # Delete
            del_btn = QPushButton("🗑️")
            del_btn.setObjectName("btnAction")
            del_btn.setFixedHeight(24)
            del_btn.clicked.connect(lambda checked=False, rid=r.id: self._delete_resume(rid))
            btn_layout.addWidget(del_btn)

            self.resumes_table.setCellWidget(row, 4, btn_box)

    def _upload_resume(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Resume File",
            "",
            "Resume Files (*.pdf *.docx *.txt *.md);;PDF Files (*.pdf);;Word Files (*.docx);;Text Files (*.txt *.md)"
        )
        if not file_path:
            return

        try:
            src_path = Path(file_path)
            # Copy file to data/resumes directory
            dest_path = RESUMES_DIR / src_path.name
            # If name exists, append counter
            counter = 1
            while dest_path.exists():
                dest_path = RESUMES_DIR / f"{src_path.stem}_{counter}{src_path.suffix}"
                counter += 1

            shutil.copy2(src_path, dest_path)

            # Extract text
            extracted_text = ResumeExtractor.extract_text(str(dest_path))

            # Check if this is the first resume
            all_resumes = self.resumes_repo.get_all_resumes()
            is_first = len(all_resumes) == 0

            resume = Resume(
                name=src_path.name,
                file_path=str(dest_path),
                extracted_text=extracted_text,
                is_default=is_first
            )
            self.resumes_repo.add_resume(resume)
            self._load_resumes_table()
            QMessageBox.information(self, "Resume Uploaded", f"Successfully uploaded and parsed '{src_path.name}'.")

        except Exception as e:
            logger.error(f"Failed to upload resume: {e}", exc_info=True)
            QMessageBox.critical(self, "Upload Failed", f"Could not parse resume: {e}")

    def _set_default_resume(self, resume_id: int):
        self.resumes_repo.set_default_resume(resume_id)
        settings.save_settings(default_resume_id=resume_id)
        self._load_resumes_table()

    def _preview_resume(self, resume: Resume):
        dlg = ResumePreviewDialog(resume, self)
        dlg.exec()

    def _delete_resume(self, resume_id: int):
        reply = QMessageBox.question(
            self,
            "Confirm Delete",
            "Are you sure you want to delete this resume?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.resumes_repo.delete_resume(resume_id)
            self._load_resumes_table()

    # -------------------------------------------------------------
    # Tab 3: Candidate Profile
    # -------------------------------------------------------------
    def _create_profile_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(12)

        card = QFrame()
        card.setObjectName("cardFrame")
        c_layout = QVBoxLayout(card)
        c_layout.setContentsMargins(16, 14, 16, 14)
        c_layout.setSpacing(12)

        desc = QLabel("Your contact and profile details will be used by the AI to sign off cold emails and personalize applications.")
        desc.setStyleSheet("color: #94A3B8; font-size: 11px;")
        c_layout.addWidget(desc)

        grid = QGridLayout()
        grid.setHorizontalSpacing(14)
        grid.setVerticalSpacing(10)

        cfg = settings.get_config()

        grid.addWidget(QLabel("<b>Full Name:</b>"), 0, 0)
        self.user_name_input = QLineEdit()
        self.user_name_input.setPlaceholderText("e.g. Alex Johnson")
        self.user_name_input.setText(cfg.user_full_name)
        grid.addWidget(self.user_name_input, 0, 1)

        grid.addWidget(QLabel("<b>Email Address:</b>"), 1, 0)
        self.user_email_input = QLineEdit()
        self.user_email_input.setPlaceholderText("e.g. alex.johnson@gmail.com")
        self.user_email_input.setText(cfg.user_email)
        grid.addWidget(self.user_email_input, 1, 1)

        grid.addWidget(QLabel("<b>Phone Number:</b>"), 2, 0)
        self.user_phone_input = QLineEdit()
        self.user_phone_input.setPlaceholderText("e.g. +1 (555) 019-2834")
        self.user_phone_input.setText(cfg.user_phone)
        grid.addWidget(self.user_phone_input, 2, 1)

        grid.addWidget(QLabel("<b>LinkedIn URL:</b>"), 3, 0)
        self.user_linkedin_input = QLineEdit()
        self.user_linkedin_input.setPlaceholderText("e.g. https://linkedin.com/in/alexjohnson")
        self.user_linkedin_input.setText(cfg.user_linkedin)
        grid.addWidget(self.user_linkedin_input, 3, 1)

        grid.addWidget(QLabel("<b>Portfolio / GitHub:</b>"), 4, 0)
        self.user_portfolio_input = QLineEdit()
        self.user_portfolio_input.setPlaceholderText("e.g. https://github.com/alexjohnson")
        self.user_portfolio_input.setText(cfg.user_portfolio)
        grid.addWidget(self.user_portfolio_input, 4, 1)

        c_layout.addLayout(grid)
        layout.addWidget(card)
        layout.addStretch(1)
        return widget

    # -------------------------------------------------------------
    # Tab 4: Scraper & Browser Settings
    # -------------------------------------------------------------
    def _create_scraper_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(12)

        card = QFrame()
        card.setObjectName("cardFrame")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(16, 14, 16, 14)
        card_layout.setSpacing(12)

        grid = QGridLayout()
        grid.setHorizontalSpacing(16)
        grid.setVerticalSpacing(10)

        cfg = settings.get_config()

        grid.addWidget(QLabel("<b>Browser Engine:</b>"), 0, 0)
        self.browser_combo = QComboBox()
        self.browser_combo.addItems(["Chrome", "Edge (Chromium)"])
        self.browser_combo.setCurrentText(cfg.browser_type.title() if cfg.browser_type else "Chrome")
        grid.addWidget(self.browser_combo, 0, 1)

        grid.addWidget(QLabel("<b>Headless Automation:</b>"), 1, 0)
        self.headless_check = QCheckBox("Run scraping browser in background (Headless)")
        self.headless_check.setChecked(cfg.headless)
        grid.addWidget(self.headless_check, 1, 1)

        grid.addWidget(QLabel("<b>HTTP Request Timeout (sec):</b>"), 2, 0)
        self.req_timeout_spin = QSpinBox()
        self.req_timeout_spin.setRange(5, 120)
        self.req_timeout_spin.setValue(cfg.request_timeout)
        grid.addWidget(self.req_timeout_spin, 2, 1)

        grid.addWidget(QLabel("<b>Browser Page Timeout (sec):</b>"), 3, 0)
        self.page_timeout_spin = QSpinBox()
        self.page_timeout_spin.setRange(5, 120)
        self.page_timeout_spin.setValue(cfg.page_timeout)
        grid.addWidget(self.page_timeout_spin, 3, 1)

        grid.addWidget(QLabel("<b>Job Relevance Threshold (0-100):</b>"), 4, 0)
        self.relevance_spin = QSpinBox()
        self.relevance_spin.setRange(0, 100)
        self.relevance_spin.setValue(cfg.relevance_threshold)
        grid.addWidget(self.relevance_spin, 4, 1)

        grid.addWidget(QLabel("<b>Polite Delay Between Requests (sec):</b>"), 5, 0)
        self.delay_spin = QDoubleSpinBox()
        self.delay_spin.setRange(0.0, 10.0)
        self.delay_spin.setSingleStep(0.5)
        self.delay_spin.setValue(cfg.delay_between_requests)
        grid.addWidget(self.delay_spin, 5, 1)

        grid.addWidget(QLabel("<b>Career Search Fallback:</b>"), 6, 0)
        self.engine_combo = QComboBox()
        self.engine_combo.addItems(["auto", "duckduckgo", "google"])
        self.engine_combo.setCurrentText(cfg.search_engine_fallback)
        grid.addWidget(self.engine_combo, 6, 1)

        card_layout.addLayout(grid)
        layout.addWidget(card)
        layout.addStretch(1)
        return widget

    def _save_all_settings(self):
        # Extract selected model ID
        model_data = self.model_combo.currentData()
        model_str = model_data if model_data else self.model_combo.currentText().strip()
        # Clean model string if user kept the descriptive text
        if "(" in model_str and ")" in model_str:
            model_str = model_str.split("(")[-1].replace(")", "").strip()

        settings.save_settings(
            # AI
            openrouter_api_key=self.api_key_input.text().strip(),
            openrouter_model=model_str,
            auto_detect_hr_email=self.auto_hr_check.isChecked(),
            email_tone=self.tone_combo.currentText(),
            # Profile
            user_full_name=self.user_name_input.text().strip(),
            user_email=self.user_email_input.text().strip(),
            user_phone=self.user_phone_input.text().strip(),
            user_linkedin=self.user_linkedin_input.text().strip(),
            user_portfolio=self.user_portfolio_input.text().strip(),
            # Scraper
            browser_type=self.browser_combo.currentText().lower(),
            headless=self.headless_check.isChecked(),
            request_timeout=self.req_timeout_spin.value(),
            page_timeout=self.page_timeout_spin.value(),
            relevance_threshold=self.relevance_spin.value(),
            delay_between_requests=self.delay_spin.value(),
            search_engine_fallback=self.engine_combo.currentText()
        )
        QMessageBox.information(self, "Settings Saved", "All configuration settings have been updated successfully.")
