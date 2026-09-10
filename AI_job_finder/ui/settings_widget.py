"""
Settings configuration view for browser preferences, timeouts, matching thresholds, and delays.
"""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel,
    QComboBox, QCheckBox, QSpinBox, QDoubleSpinBox, QPushButton,
    QFrame, QMessageBox
)
from PyQt6.QtCore import Qt
from config.settings import settings


class SettingsWidget(QWidget):
    """Application settings panel."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(12)

        card = QFrame()
        card.setObjectName("cardFrame")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(18, 16, 18, 16)
        card_layout.setSpacing(14)

        title = QLabel("Application Settings & Scraper Configuration")
        title.setObjectName("sectionTitle")
        card_layout.addWidget(title)

        grid = QGridLayout()
        grid.setHorizontalSpacing(16)
        grid.setVerticalSpacing(10)

        cfg = settings.get_config()

        # 1. Browser Type
        grid.addWidget(QLabel("<b>Browser Engine:</b>"), 0, 0)
        self.browser_combo = QComboBox()
        self.browser_combo.addItems(["Chrome", "Edge (Chromium)"])
        self.browser_combo.setCurrentText("Chrome")
        grid.addWidget(self.browser_combo, 0, 1)

        # 2. Headless Mode
        grid.addWidget(QLabel("<b>Headless Automation:</b>"), 1, 0)
        self.headless_check = QCheckBox("Run browser in background (Headless)")
        self.headless_check.setChecked(cfg.headless)
        grid.addWidget(self.headless_check, 1, 1)

        # 3. HTTP Request Timeout
        grid.addWidget(QLabel("<b>HTTP Request Timeout (seconds):</b>"), 2, 0)
        self.req_timeout_spin = QSpinBox()
        self.req_timeout_spin.setRange(5, 120)
        self.req_timeout_spin.setValue(cfg.request_timeout)
        grid.addWidget(self.req_timeout_spin, 2, 1)

        # 4. Browser Page Timeout
        grid.addWidget(QLabel("<b>Browser Page Timeout (seconds):</b>"), 3, 0)
        self.page_timeout_spin = QSpinBox()
        self.page_timeout_spin.setRange(5, 120)
        self.page_timeout_spin.setValue(cfg.page_timeout)
        grid.addWidget(self.page_timeout_spin, 3, 1)

        # 5. Job Relevance Threshold
        grid.addWidget(QLabel("<b>Job Relevance Threshold (0 - 100):</b>"), 4, 0)
        self.relevance_spin = QSpinBox()
        self.relevance_spin.setRange(0, 100)
        self.relevance_spin.setValue(cfg.relevance_threshold)
        grid.addWidget(self.relevance_spin, 4, 1)

        # 6. Delay Between Requests
        grid.addWidget(QLabel("<b>Polite Delay Between Requests (sec):</b>"), 5, 0)
        self.delay_spin = QDoubleSpinBox()
        self.delay_spin.setRange(0.0, 10.0)
        self.delay_spin.setSingleStep(0.5)
        self.delay_spin.setValue(cfg.delay_between_requests)
        grid.addWidget(self.delay_spin, 5, 1)

        # 7. Search Engine Fallback
        grid.addWidget(QLabel("<b>Career Search Fallback:</b>"), 6, 0)
        self.engine_combo = QComboBox()
        self.engine_combo.addItems(["auto", "duckduckgo", "google"])
        self.engine_combo.setCurrentText(cfg.search_engine_fallback)
        grid.addWidget(self.engine_combo, 6, 1)

        card_layout.addLayout(grid)

        # Save Button
        btn_row = QHBoxLayout()
        btn_row.addStretch()

        save_btn = QPushButton("💾  Save Settings")
        save_btn.setObjectName("btnPrimary")
        save_btn.clicked.connect(self._save_settings)
        btn_row.addWidget(save_btn)

        card_layout.addLayout(btn_row)
        layout.addWidget(card)
        layout.addStretch()

    def _save_settings(self):
        settings.save_settings(
            headless=self.headless_check.isChecked(),
            request_timeout=self.req_timeout_spin.value(),
            page_timeout=self.page_timeout_spin.value(),
            relevance_threshold=self.relevance_spin.value(),
            delay_between_requests=self.delay_spin.value(),
            search_engine_fallback=self.engine_combo.currentText()
        )
        QMessageBox.information(self, "Settings Saved", "Application settings have been updated and saved.")
