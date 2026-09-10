"""
Export dialog supporting CSV, Excel (.xlsx), and JSON formats for companies, jobs, and contacts.
"""

import json
from pathlib import Path
import pandas as pd
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel,
    QComboBox, QRadioButton, QButtonGroup, QPushButton,
    QFileDialog, QMessageBox, QFrame
)
from database.repositories import CompaniesRepository, JobsRepository, ContactsRepository


class ExportDialog(QDialog):
    """Wizard dialog for exporting collected data."""

    def __init__(self, search_id: int = None, parent=None):
        super().__init__(parent)
        self.search_id = search_id
        self.companies_repo = CompaniesRepository()
        self.jobs_repo = JobsRepository()
        self.contacts_repo = ContactsRepository()

        self.setWindowTitle("Export Results")
        self.resize(480, 320)
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(16)

        card = QFrame()
        card.setObjectName("cardFrame")
        card_layout = QVBoxLayout(card)
        card_layout.setSpacing(12)

        title = QLabel("Select Export Options")
        title.setObjectName("sectionTitle")
        card_layout.addWidget(title)

        # 1. Dataset Selection
        card_layout.addWidget(QLabel("<b>Choose Data to Export:</b>"))
        self.dataset_group = QButtonGroup(self)
        self.rb_all = QRadioButton("Complete Master Sheet (Companies, Jobs & Emails)")
        self.rb_companies = QRadioButton("Companies Only")
        self.rb_jobs = QRadioButton("Job Openings Only")
        self.rb_contacts = QRadioButton("Business Contacts / Emails Only")
        self.rb_all.setChecked(True)

        self.dataset_group.addButton(self.rb_all, 1)
        self.dataset_group.addButton(self.rb_companies, 2)
        self.dataset_group.addButton(self.rb_jobs, 3)
        self.dataset_group.addButton(self.rb_contacts, 4)

        card_layout.addWidget(self.rb_all)
        card_layout.addWidget(self.rb_companies)
        card_layout.addWidget(self.rb_jobs)
        card_layout.addWidget(self.rb_contacts)

        # 2. Format Selection
        format_layout = QHBoxLayout()
        format_layout.addWidget(QLabel("<b>Format:</b>"))
        self.format_combo = QComboBox()
        self.format_combo.addItems(["CSV (*.csv)", "Excel Spreadsheet (*.xlsx)", "JSON (*.json)"])
        format_layout.addWidget(self.format_combo)
        card_layout.addLayout(format_layout)

        layout.addWidget(card)

        # Action Buttons
        btn_row = QHBoxLayout()
        btn_row.addStretch()

        export_btn = QPushButton("💾  Export Now")
        export_btn.setObjectName("btnPrimary")
        export_btn.clicked.connect(self._do_export)
        btn_row.addWidget(export_btn)

        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)

        layout.addLayout(btn_row)

    def _do_export(self):
        selected_fmt = self.format_combo.currentText()
        ext = ".csv" if "CSV" in selected_fmt else ".xlsx" if "Excel" in selected_fmt else ".json"
        filter_str = "CSV Files (*.csv)" if ext == ".csv" else "Excel Files (*.xlsx)" if ext == ".xlsx" else "JSON Files (*.json)"

        file_path, _ = QFileDialog.getSaveFileName(self, "Save Export File", f"job_finder_export{ext}", filter_str)
        if not file_path:
            return

        try:
            target_id = self.dataset_group.checkedId()

            if target_id == 1:
                # Master dataset
                comps = [c.to_dict() for c in self.companies_repo.get_companies(search_id=self.search_id, limit=2000)]
                df = pd.DataFrame(comps)
            elif target_id == 2:
                comps = [c.to_dict() for c in self.companies_repo.get_companies(search_id=self.search_id, limit=2000)]
                df = pd.DataFrame(comps)
            elif target_id == 3:
                jobs = [j.to_dict() for j in self.jobs_repo.get_all_jobs(limit=5000)]
                df = pd.DataFrame(jobs)
            else:
                contacts = self.contacts_repo.get_all_contacts(limit=5000)
                df = pd.DataFrame(contacts)

            if ext == ".csv":
                df.to_csv(file_path, index=False, encoding="utf-8-sig")
            elif ext == ".xlsx":
                df.to_excel(file_path, index=False, engine="openpyxl")
            elif ext == ".json":
                df.to_json(file_path, orient="records", indent=2)

            QMessageBox.information(self, "Export Successful", f"Successfully exported {len(df)} records to:\n{file_path}")
            self.accept()
        except Exception as e:
            QMessageBox.critical(self, "Export Failed", f"Failed to export file:\n{str(e)}")
