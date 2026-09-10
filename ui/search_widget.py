"""
Search Requirements form widget with compact grid layout, dynamic custom inputs, limits, and workflow triggers.
"""

from typing import Optional
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel,
    QLineEdit, QComboBox, QSpinBox, QCheckBox, QPushButton,
    QFrame, QMessageBox, QSizePolicy
)
from PyQt6.QtCore import pyqtSignal, Qt
from database.models import SearchSession
from config.settings import settings

PROFESSIONS = [
    "All", "Web Developer", "Frontend Developer", "Backend Developer", "Full Stack Developer",
    "Python Developer", "Java Developer", "Software Engineer", "AI Engineer",
    "ML Engineer", "Data Scientist", "Data Engineer", "DevOps Engineer",
    "Cloud Engineer", "Mobile Developer", "QA Engineer", "Cyber Security",
    "UI/UX Designer", "Sales", "Marketing", "HR", "Other"
]

COMPANY_TYPES = [
    "IT Company", "Software Company", "Technology Company", "Startup",
    "Consulting Company", "Sales Company", "Marketing Company", "Finance Company",
    "Bank", "E-commerce", "Manufacturing", "Healthcare", "Education",
    "Recruitment", "Logistics", "Real Estate", "Other"
]

RESULT_LIMIT_OPTIONS = ["10", "20", "30", "50", "100", "Custom"]


class SearchWidget(QWidget):
    """Compact form widget for defining search requirements."""

    search_requested = pyqtSignal(SearchSession)
    stop_requested = pyqtSignal()
    resume_requested = pyqtSignal(SearchSession)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)
        self._init_ui()

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(14, 12, 14, 6)
        main_layout.setSpacing(8)

        card_frame = QFrame()
        card_frame.setObjectName("compactCard")
        card_layout = QVBoxLayout(card_frame)
        card_layout.setContentsMargins(14, 10, 14, 10)
        card_layout.setSpacing(8)

        # Title Row
        title_row = QHBoxLayout()
        title_label = QLabel("Search Requirements")
        title_label.setObjectName("sectionTitle")
        title_row.addWidget(title_label)
        title_row.addStretch()
        card_layout.addLayout(title_row)

        # Compact Grid
        grid = QGridLayout()
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(6)

        # Row 0: Location (City, State, Country)
        grid.addWidget(QLabel("City:"), 0, 0)
        self.city_input = QLineEdit("Jaipur")
        self.city_input.setPlaceholderText("City name")
        self.city_input.textChanged.connect(self._handle_location_autofill)
        grid.addWidget(self.city_input, 0, 1)

        grid.addWidget(QLabel("State:"), 0, 2)
        self.state_input = QLineEdit("Rajasthan")
        self.state_input.setPlaceholderText("State name")
        grid.addWidget(self.state_input, 0, 3)

        grid.addWidget(QLabel("Country:"), 0, 4)
        self.country_input = QLineEdit("India")
        self.country_input.setPlaceholderText("Country")
        grid.addWidget(self.country_input, 0, 5)

        # Row 1: Profession & Company Type
        grid.addWidget(QLabel("Profession:"), 1, 0)
        self.profession_combo = QComboBox()
        self.profession_combo.addItems(PROFESSIONS)
        self.profession_combo.setCurrentText("Web Developer")
        self.profession_combo.currentTextChanged.connect(self._on_profession_changed)
        grid.addWidget(self.profession_combo, 1, 1)

        self.custom_prof_container = QWidget()
        custom_prof_layout = QHBoxLayout(self.custom_prof_container)
        custom_prof_layout.setContentsMargins(0, 0, 0, 0)
        custom_prof_layout.setSpacing(4)
        self.custom_profession_input = QLineEdit()
        self.custom_profession_input.setPlaceholderText("Custom profession...")
        custom_prof_layout.addWidget(self.custom_profession_input)
        self.custom_prof_container.setVisible(False)
        grid.addWidget(self.custom_prof_container, 1, 2, 1, 1)

        grid.addWidget(QLabel("Company Type:"), 1, 3)
        self.type_combo = QComboBox()
        self.type_combo.addItems(COMPANY_TYPES)
        self.type_combo.setCurrentText("IT Company")
        self.type_combo.currentTextChanged.connect(self._on_type_changed)
        grid.addWidget(self.type_combo, 1, 4)

        self.custom_type_container = QWidget()
        custom_type_layout = QHBoxLayout(self.custom_type_container)
        custom_type_layout.setContentsMargins(0, 0, 0, 0)
        custom_type_layout.setSpacing(4)
        self.custom_type_input = QLineEdit()
        self.custom_type_input.setPlaceholderText("Custom company type...")
        custom_type_layout.addWidget(self.custom_type_input)
        self.custom_type_container.setVisible(False)
        grid.addWidget(self.custom_type_container, 1, 5, 1, 1)

        # Row 2: Results & Options
        grid.addWidget(QLabel("Results:"), 2, 0)
        limit_layout = QHBoxLayout()
        limit_layout.setSpacing(6)
        self.limit_combo = QComboBox()
        self.limit_combo.addItems(RESULT_LIMIT_OPTIONS)
        self.limit_combo.setCurrentText("10")
        self.limit_combo.setFixedWidth(80)
        self.limit_combo.currentTextChanged.connect(self._on_limit_changed)
        limit_layout.addWidget(self.limit_combo)

        self.custom_limit_spin = QSpinBox()
        self.custom_limit_spin.setRange(1, 200)
        self.custom_limit_spin.setValue(15)
        self.custom_limit_spin.setFixedWidth(70)
        self.custom_limit_spin.setVisible(False)
        limit_layout.addWidget(self.custom_limit_spin)
        limit_layout.addStretch()
        grid.addLayout(limit_layout, 2, 1)

        opts_layout = QHBoxLayout()
        opts_layout.setSpacing(16)
        self.enrich_check = QCheckBox("Enrich Results (Website, Careers, Contacts)")
        self.enrich_check.setChecked(True)
        self.auto_browser_check = QCheckBox("Auto Browser")
        self.auto_browser_check.setChecked(True)
        opts_layout.addWidget(self.enrich_check)
        opts_layout.addWidget(self.auto_browser_check)
        opts_layout.addStretch()
        grid.addLayout(opts_layout, 2, 2, 1, 4)

        card_layout.addLayout(grid)

        # Buttons Row (Compact 36-38px)
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)

        self.search_btn = QPushButton("🔎  START SEARCH")
        self.search_btn.setObjectName("btnPrimary")
        self.search_btn.setMinimumHeight(34)
        self.search_btn.clicked.connect(self._on_search_clicked)
        btn_layout.addWidget(self.search_btn, 3)

        self.stop_btn = QPushButton("⏹  STOP")
        self.stop_btn.setObjectName("btnDanger")
        self.stop_btn.setMinimumHeight(34)
        self.stop_btn.setEnabled(False)
        self.stop_btn.clicked.connect(self.stop_requested.emit)
        btn_layout.addWidget(self.stop_btn, 1)

        self.resume_btn = QPushButton("▶  RESUME ENRICHMENT")
        self.resume_btn.setObjectName("btnSuccess")
        self.resume_btn.setMinimumHeight(34)
        self.resume_btn.clicked.connect(self._on_resume_clicked)
        btn_layout.addWidget(self.resume_btn, 2)

        card_layout.addLayout(btn_layout)
        main_layout.addWidget(card_frame)

    def _handle_location_autofill(self, text: str):
        """Allows pasting 'Jaipur, Rajasthan, India' into city to automatically split."""
        if "," in text:
            parts = [p.strip() for p in text.split(",") if p.strip()]
            if len(parts) >= 2:
                self.city_input.blockSignals(True)
                self.city_input.setText(parts[0])
                self.city_input.blockSignals(False)
                self.state_input.setText(parts[1])
                if len(parts) >= 3:
                    self.country_input.setText(parts[2])

    def _on_profession_changed(self, text: str):
        is_other = (text == "Other")
        self.custom_prof_container.setVisible(is_other)

    def _on_type_changed(self, text: str):
        is_other = (text == "Other")
        self.custom_type_container.setVisible(is_other)

    def _on_limit_changed(self, text: str):
        is_custom = (text == "Custom")
        self.custom_limit_spin.setVisible(is_custom)

    def get_result_limit(self) -> int:
        selected = self.limit_combo.currentText()
        if selected == "Custom":
            return self.custom_limit_spin.value()
        try:
            return int(selected)
        except ValueError:
            return 10

    def build_session(self) -> Optional[SearchSession]:
        city = self.city_input.text().strip()
        state = self.state_input.text().strip()
        country = self.country_input.text().strip()

        if not city:
            QMessageBox.warning(self, "Validation Error", "Please enter at least a City for the search location.")
            return None

        prof = self.profession_combo.currentText()
        custom_prof = self.custom_profession_input.text().strip() if prof == "Other" else None
        if prof == "Other" and not custom_prof:
            QMessageBox.warning(self, "Validation Error", "Please enter your desired custom profession.")
            return None

        comp_type = self.type_combo.currentText()
        custom_type = self.custom_type_input.text().strip() if comp_type == "Other" else None
        if comp_type == "Other" and not custom_type:
            QMessageBox.warning(self, "Validation Error", "Please enter your desired custom company type.")
            return None

        return SearchSession(
            city=city,
            state=state,
            country=country,
            profession=prof,
            custom_profession=custom_prof,
            company_type=comp_type,
            custom_company_type=custom_type,
            result_limit=self.get_result_limit(),
            enrich_enabled=self.enrich_check.isChecked(),
            auto_browser=self.auto_browser_check.isChecked()
        )

    def _on_search_clicked(self):
        session = self.build_session()
        if session:
            self.set_running_state(True)
            self.search_requested.emit(session)

    def _on_resume_clicked(self):
        session = self.build_session()
        if session:
            self.set_running_state(True)
            self.resume_requested.emit(session)

    def set_running_state(self, is_running: bool):
        self.search_btn.setEnabled(not is_running)
        self.resume_btn.setEnabled(not is_running)
        self.stop_btn.setEnabled(is_running)
