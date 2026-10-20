"""
Interactive modal dialog for AI Job + Resume Analysis, Match Scoring, Personalized Email Generation, and Chrome Automation.
"""

import os
import webbrowser
from typing import Optional, List, Dict, Any
from datetime import datetime
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QTextEdit, QLineEdit,
    QPushButton, QFrame, QGridLayout, QComboBox, QProgressBar,
    QMessageBox, QApplication, QScrollArea, QWidget, QSplitter, QCheckBox
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QFont, QClipboard

from database.models import Job, Company, Resume, JobApplication, AIAnalysisResult
from database.repositories import ResumesRepository, ApplicationsRepository, ContactsRepository, CompaniesRepository
from core.ai.openrouter_client import OpenRouterClient
from core.ai.prompt_builders import PromptBuilder
from browser.email_automation import EmailAutomationService
from config.settings import settings
from ui.styles import get_relevance_badge_style
from utils.logger import get_logger

logger = get_logger("contact_hr_dialog")


class LiveChromeSenderWorker(QThread):
    """Background worker for live Chrome automation: typing recipient, subject, body, attaching resume, and sending."""
    status_updated = pyqtSignal(str)
    finished = pyqtSignal(dict)

    def __init__(
        self,
        to_email: str,
        subject: str,
        body: str,
        resume_path: Optional[str] = None,
        auto_send: bool = True
    ):
        super().__init__()
        self.to_email = to_email
        self.subject = subject
        self.body = body
        self.resume_path = resume_path
        self.auto_send = auto_send

    def run(self):
        res = EmailAutomationService.live_chrome_auto_type_and_send(
            to_email=self.to_email,
            subject=self.subject,
            body=self.body,
            resume_path=self.resume_path,
            auto_send=self.auto_send,
            status_callback=self.status_updated.emit
        )
        self.finished.emit(res)


class HREmailHunterWorker(QThread):
    """Background worker for LinkedIn Company About & OSINT HR Email discovery."""
    finished = pyqtSignal(dict)

    def __init__(
        self,
        company_name: str,
        domain: Optional[str] = None,
        location: Optional[str] = None,
        linkedin_url: Optional[str] = None
    ):
        super().__init__()
        self.company_name = company_name
        self.domain = domain
        self.location = location
        self.linkedin_url = linkedin_url

    def run(self):
        try:
            from scrapers.linkedin_company_enricher import linkedin_enricher
            from core.hr_email_hunter import hr_hunter

            # Step 1: LinkedIn Company About / Fallback search & Website scraping
            li_enrich = linkedin_enricher.full_enrichment_flow(
                company_name=self.company_name,
                company_linkedin_url=self.linkedin_url,
                location=self.location
            )

            discovered_domain = self.domain or (li_enrich.get("website") if li_enrich.get("website") else None)

            # Step 2: Recruiter Dorks & MX Verification
            res = hr_hunter.hunt_hr_contacts(self.company_name, discovered_domain)

            # Merge any emails scraped directly from company website
            existing_emails = {c["email"] for c in res.get("email_candidates", [])}
            for w_em in li_enrich.get("emails", []):
                em_str = w_em["email"]
                if em_str not in existing_emails:
                    res["email_candidates"].insert(0, {
                        "email": em_str,
                        "confidence": 92,
                        "source": f"Official Website ({li_enrich.get('website')})"
                    })
                    existing_emails.add(em_str)

            # If no primary email, take top website email
            if not res.get("primary_email") and li_enrich.get("emails"):
                res["primary_email"] = li_enrich["emails"][0]["email"]

            res["website"] = li_enrich.get("website")
            res["phone"] = li_enrich.get("phone")
            res["industry"] = li_enrich.get("industry")
            res["headquarters"] = li_enrich.get("headquarters")

            self.finished.emit(res)
        except Exception as e:
            self.finished.emit({"success": False, "error": str(e)})


class AIAnalysisWorker(QThread):
    """Background worker for non-blocking OpenRouter LLM analysis and email generation."""
    finished = pyqtSignal(dict)  # {"success": bool, "result": AIAnalysisResult, "error": str}

    def __init__(
        self,
        job_title: str,
        company_name: str,
        job_description: str,
        resume_text: str,
        candidate_info: Dict[str, str],
        tone: str = "Professional & Concise",
        custom_instructions: Optional[str] = None
    ):
        super().__init__()
        self.job_title = job_title
        self.company_name = company_name
        self.job_description = job_description
        self.resume_text = resume_text
        self.candidate_info = candidate_info
        self.tone = tone
        self.custom_instructions = custom_instructions

    def run(self):
        client = OpenRouterClient()
        if not client.is_configured():
            self.finished.emit({
                "success": False,
                "error": "OpenRouter API Key is missing. Please configure it in Settings."
            })
            return

        try:
            if self.custom_instructions:
                prompt = PromptBuilder.build_regenerate_email_prompt(
                    job_title=self.job_title,
                    company_name=self.company_name,
                    job_description=self.job_description,
                    resume_text=self.resume_text,
                    candidate_info=self.candidate_info,
                    custom_instructions=self.custom_instructions,
                    tone=self.tone
                )
            else:
                prompt = PromptBuilder.build_analysis_and_email_prompt(
                    job_title=self.job_title,
                    company_name=self.company_name,
                    job_description=self.job_description,
                    resume_text=self.resume_text,
                    candidate_info=self.candidate_info,
                    tone=self.tone
                )

            resp = client.complete(
                prompt=prompt,
                system_prompt=PromptBuilder.SYSTEM_PROMPT,
                temperature=0.4
            )

            if not resp.get("success"):
                self.finished.emit({
                    "success": False,
                    "error": resp.get("error", "AI generation failed.")
                })
                return

            analysis_result = PromptBuilder.parse_ai_response(resp.get("content", ""))
            self.finished.emit({
                "success": True,
                "result": analysis_result
            })

        except Exception as e:
            logger.error(f"Error in AI worker: {e}", exc_info=True)
            self.finished.emit({
                "success": False,
                "error": str(e)
            })


class ContactHRDialog(QDialog):
    """Full-featured AI Application & Cold Outreach Dialog."""

    def __init__(
        self,
        job: Optional[Job] = None,
        company: Optional[Company] = None,
        target_email: Optional[str] = None,
        parent=None
    ):
        super().__init__(parent)
        self.company = company
        self.target_email = target_email

        if job is not None:
            self.job = job
        elif company is not None:
            self.job = Job(
                company_id=company.id or 0,
                title="Software Engineer / Technical Role",
                company_name=company.name,
                location=company.address or company.city or ""
            )
        else:
            self.job = Job(title="Software Engineer", company_name="Company")

        self.resumes_repo = ResumesRepository()
        self.apps_repo = ApplicationsRepository()
        self.contacts_repo = ContactsRepository()
        self.companies_repo = CompaniesRepository()

        self.current_resume: Optional[Resume] = None
        self.analysis_result: Optional[AIAnalysisResult] = None
        self.worker: Optional[AIAnalysisWorker] = None

        self.setWindowTitle(f"AI Application & Contact HR: {self.job.title} — {self.job.company_name or 'Company'}")
        self.resize(900, 720)
        self.setMinimumSize(780, 580)
        self._init_ui()
        self._load_data()

    def _init_ui(self):
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(16, 14, 16, 14)
        root_layout.setSpacing(10)

        # 1. Top Header Card (Job info + Detected HR Email + Resume Selection)
        top_card = QFrame()
        top_card.setObjectName("cardFrame")
        tc_layout = QVBoxLayout(top_card)
        tc_layout.setContentsMargins(14, 10, 14, 10)
        tc_layout.setSpacing(8)

        # Title & Company
        h_row = QHBoxLayout()
        job_lbl = QLabel(f"🎯  {self.job.title}")
        job_lbl.setObjectName("headerTitle")
        job_lbl.setStyleSheet("font-size: 16px; font-weight: 800; color: #38BDF8;")
        h_row.addWidget(job_lbl, 3)

        if self.job.company_name:
            comp_badge = QLabel(f"🏢 {self.job.company_name}")
            comp_badge.setStyleSheet("background-color: #1E293B; color: #94A3B8; font-weight: 700; padding: 4px 10px; border-radius: 6px; border: 1px solid #334155;")
            h_row.addWidget(comp_badge)
        h_row.addStretch(1)
        tc_layout.addLayout(h_row)

        # Controls Grid (HR Email + Resume Picker + Tone)
        grid = QGridLayout()
        grid.setSpacing(8)

        # HR Email with OSINT Hunt Button
        grid.addWidget(QLabel("<b>✉️ Recipient HR Email:</b>"), 0, 0)
        email_h_layout = QHBoxLayout()
        self.hr_email_input = QLineEdit()
        self.hr_email_input.setPlaceholderText("e.g. hr@company.com or recruiter@company.com")
        email_h_layout.addWidget(self.hr_email_input, 1)

        self.hunt_hr_btn = QPushButton("🎯 Hunt HR")
        self.hunt_hr_btn.setObjectName("btnAction")
        self.hunt_hr_btn.setToolTip("Hunt HR & Recruiter emails via Google & LinkedIn OSINT Dorks")
        self.hunt_hr_btn.clicked.connect(lambda: self._hunt_hr_email(auto=False))
        email_h_layout.addWidget(self.hunt_hr_btn)
        grid.addLayout(email_h_layout, 0, 1)

        # Resume Selector
        grid.addWidget(QLabel("<b>📄 Selected Resume:</b>"), 0, 2)
        self.resume_combo = QComboBox()
        self.resume_combo.currentIndexChanged.connect(self._on_resume_changed)
        grid.addWidget(self.resume_combo, 0, 3)

        # Tone Selector
        grid.addWidget(QLabel("<b>🎨 Email Tone:</b>"), 1, 0)
        self.tone_combo = QComboBox()
        self.tone_combo.addItems([
            "Professional & Concise",
            "Confident & High-Impact",
            "Enthusiastic & Friendly",
            "Formal & Executive",
            "Direct & Technical"
        ])
        grid.addWidget(self.tone_combo, 1, 1)

        # Custom AI Instructions
        grid.addWidget(QLabel("<b>💡 Custom Tweak:</b>"), 1, 2)
        self.custom_prompt_input = QLineEdit()
        self.custom_prompt_input.setPlaceholderText("Optional: e.g. Emphasize backend APIs & fast learning")
        grid.addWidget(self.custom_prompt_input, 1, 3)

        tc_layout.addLayout(grid)

        # OSINT Hunter Status Badge
        self.hunt_status_lbl = QLabel("")
        self.hunt_status_lbl.setStyleSheet("color: #38BDF8; font-size: 11px; font-weight: 600; padding: 2px 4px;")
        self.hunt_status_lbl.setVisible(False)
        tc_layout.addWidget(self.hunt_status_lbl)

        root_layout.addWidget(top_card)

        # 2. Match Score & Skills Breakdown Section
        self.analysis_card = QFrame()
        self.analysis_card.setObjectName("compactCard")
        ac_layout = QVBoxLayout(self.analysis_card)
        ac_layout.setContentsMargins(12, 8, 12, 8)
        ac_layout.setSpacing(6)

        self.score_row = QHBoxLayout()
        self.match_badge = QLabel("⚡ Match Score: Calculating...")
        self.match_badge.setStyleSheet(get_relevance_badge_style(75))
        self.score_row.addWidget(self.match_badge)

        self.analysis_summary_lbl = QLabel("Analyzing job requirements and matching against your selected resume...")
        self.analysis_summary_lbl.setStyleSheet("color: #94A3B8; font-size: 11px;")
        self.analysis_summary_lbl.setWordWrap(True)
        self.score_row.addWidget(self.analysis_summary_lbl, 1)
        ac_layout.addLayout(self.score_row)

        # Skills badges container
        self.skills_container = QWidget()
        self.skills_layout = QHBoxLayout(self.skills_container)
        self.skills_layout.setContentsMargins(0, 0, 0, 0)
        self.skills_layout.setSpacing(6)
        ac_layout.addWidget(self.skills_container)

        root_layout.addWidget(self.analysis_card)

        # Progress bar during AI generation
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0)  # indeterminate animation
        self.progress_bar.setFixedHeight(4)
        self.progress_bar.setStyleSheet("QProgressBar { border: none; background-color: #1E293B; } QProgressBar::chunk { background-color: #38BDF8; }")
        self.progress_bar.setVisible(False)
        root_layout.addWidget(self.progress_bar)

        # 3. Subject & Email Body Editor Card
        editor_card = QFrame()
        editor_card.setObjectName("cardFrame")
        ec_layout = QVBoxLayout(editor_card)
        ec_layout.setContentsMargins(14, 10, 14, 10)
        ec_layout.setSpacing(8)

        # Subject Row
        sub_row = QHBoxLayout()
        sub_row.addWidget(QLabel("<b>Subject:</b>"))
        self.subject_input = QLineEdit()
        self.subject_input.setPlaceholderText("Email subject line...")
        sub_row.addWidget(self.subject_input, 1)
        ec_layout.addLayout(sub_row)

        # Body Text Editor
        ec_layout.addWidget(QLabel("<b>Personalized Email Body:</b>"))
        self.body_edit = QTextEdit()
        self.body_edit.setPlaceholderText("AI-generated email will appear here. You can freely edit or tweak any text...")
        ec_layout.addWidget(self.body_edit, 1)

        root_layout.addWidget(editor_card, 1)

        # Live Automation Status Bar
        self.live_status_lbl = QLabel("Ready to dispatch")
        self.live_status_lbl.setStyleSheet("color: #38BDF8; font-size: 11px; font-weight: 600; padding: 4px 10px; background-color: #0B0F19; border: 1px solid #0284C7; border-radius: 4px;")
        self.live_status_lbl.setVisible(False)
        root_layout.addWidget(self.live_status_lbl)

        # 4. Bottom Action Bar
        action_bar = QHBoxLayout()
        action_bar.setSpacing(8)

        # Regenerate AI Button
        self.regen_btn = QPushButton("✨ Regenerate with AI")
        self.regen_btn.setObjectName("btnAction")
        self.regen_btn.clicked.connect(self._regenerate_email)
        action_bar.addWidget(self.regen_btn)

        # Copy to Clipboard Button
        self.copy_btn = QPushButton("📋 Copy Email")
        self.copy_btn.setObjectName("btnAction")
        self.copy_btn.clicked.connect(self._copy_email_to_clipboard)
        action_bar.addWidget(self.copy_btn)

        action_bar.addStretch(1)

        # Auto-send checkbox
        self.auto_send_check = QCheckBox("⚡ Live Auto-Type, Attach & Send")
        self.auto_send_check.setChecked(True)
        self.auto_send_check.setToolTip("Opens visible Chrome, types email character-by-character in front of you, attaches resume, and sends automatically.")
        action_bar.addWidget(self.auto_send_check)

        # Webmail Provider Selector
        action_bar.addWidget(QLabel("Send via:"))
        self.provider_combo = QComboBox()
        self.provider_combo.addItems(["Gmail (Live Chrome)", "Outlook (Web)", "Default Email App"])
        action_bar.addWidget(self.provider_combo)

        # Save Draft Button
        self.save_draft_btn = QPushButton("💾 Save Draft")
        self.save_draft_btn.setObjectName("btnAction")
        self.save_draft_btn.clicked.connect(self._save_draft)
        action_bar.addWidget(self.save_draft_btn)

        # Primary Dispatch Button: Open in Chrome & Send
        self.send_btn = QPushButton("🚀 Live Send with Chrome")
        self.send_btn.setObjectName("btnPrimary")
        self.send_btn.setFixedHeight(34)
        self.send_btn.clicked.connect(self._open_in_chrome_and_send)
        action_bar.addWidget(self.send_btn)

        root_layout.addLayout(action_bar)

    def _load_data(self):
        """Loads resumes, detected HR emails, and triggers initial AI generation."""
        # 1. Populate Resumes
        resumes = self.resumes_repo.get_all_resumes()
        self.resume_combo.clear()
        if not resumes:
            self.resume_combo.addItem("⚠️ No resume found (Upload in Settings)", None)
        else:
            default_idx = 0
            for i, r in enumerate(resumes):
                prefix = "⭐ " if r.is_default else "📄 "
                self.resume_combo.addItem(f"{prefix}{r.name}", r)
                if r.is_default:
                    default_idx = i
            self.resume_combo.setCurrentIndex(default_idx)
            self.current_resume = resumes[default_idx]

        # 2. Detect HR / Recruiter Email
        if self.target_email:
            self.hr_email_input.setText(self.target_email)
        else:
            detected_email = self._find_best_contact_email()
            if detected_email:
                self.hr_email_input.setText(detected_email)
            else:
                # Automatically hunt HR via OSINT dorks in background!
                self._hunt_hr_email(auto=True)

        # 3. Check for existing application draft
        if self.job.id:
            existing_app = self.apps_repo.get_by_job_id(self.job.id)
            if existing_app and existing_app.email_body:
                self.subject_input.setText(existing_app.subject)
                self.body_edit.setText(existing_app.email_body)
                if existing_app.hr_email:
                    self.hr_email_input.setText(existing_app.hr_email)
                if existing_app.match_score > 0:
                    self.match_badge.setText(f"⚡ Match Score: {existing_app.match_score}%")
                    self.match_badge.setStyleSheet(get_relevance_badge_style(existing_app.match_score))
                self.analysis_summary_lbl.setText("Loaded saved draft for this position.")
                return

        # 4. Trigger initial AI analysis
        self._start_ai_generation()

    def _find_best_contact_email(self) -> str:
        """Finds HR or careers email associated with the job's company."""
        if not self.job.company_id:
            return ""

        contacts = self.contacts_repo.get_by_company(self.job.company_id)
        if not contacts:
            return ""

        # Priority: HR -> Careers -> Jobs -> General -> Others
        priority_types = ["hr", "careers", "jobs", "general"]
        for ptype in priority_types:
            for ct in contacts:
                if (ct.email_type or "").lower() == ptype:
                    return ct.email

        # If none matched priority, return first available
        return contacts[0].email if contacts else ""

    def _hunt_hr_email(self, auto: bool = False):
        """Discovers HR & Recruiter emails via OSINT / LinkedIn search dorks."""
        company_name = self.job.company_name or ""
        if not company_name:
            if not auto:
                QMessageBox.warning(self, "Company Name Required", "Please ensure the job has a company name to hunt HR.")
            return

        domain = None
        linkedin_url = None
        if self.job and self.job.company_id:
            try:
                comp = self.companies_repo.get_by_id(self.job.company_id)
                if comp:
                    if comp.website_url:
                        domain = comp.website_domain or comp.website_url
                    linkedin_url = comp.linkedin_url
            except Exception as e:
                logger.debug(f"Failed to fetch company for domain: {e}")

        self.hunt_hr_btn.setEnabled(False)
        self.hunt_hr_btn.setText("🎯 Hunting...")
        self.hunt_status_lbl.setVisible(True)
        self.hunt_status_lbl.setStyleSheet("color: #38BDF8; font-size: 11px;")
        self.hunt_status_lbl.setText(f"🔍 Checking LinkedIn About, Website & OSINT dorks for {company_name}...")

        self.hunter_worker = HREmailHunterWorker(
            company_name=company_name,
            domain=domain,
            location=self.job.location,
            linkedin_url=linkedin_url
        )
        self.hunter_worker.finished.connect(self._on_hunter_finished)
        self.hunter_worker.start()

    def _on_hunter_finished(self, res: dict):
        self.hunt_hr_btn.setEnabled(True)
        self.hunt_hr_btn.setText("🎯 Hunt HR")
        primary = res.get("primary_email", "")
        recruiters = res.get("recruiters", [])
        candidates = res.get("email_candidates", [])
        website = res.get("website")
        phone = res.get("phone")
        industry = res.get("industry")

        # Persist company website, phone, industry if newly found
        if self.job.company_id:
            try:
                comp = self.companies_repo.get_by_id(self.job.company_id)
                if comp:
                    updated = False
                    if website and not comp.website_url:
                        comp.website_url = website
                        comp.website = website
                        updated = True
                    if phone and not comp.phone:
                        comp.phone = phone
                        updated = True
                    if industry and not comp.category:
                        comp.category = industry
                        updated = True
                    if updated:
                        self.companies_repo.upsert(comp)
            except Exception as ce:
                logger.debug(f"Could not update company details: {ce}")

        if primary:
            if not self.hr_email_input.text().strip():
                self.hr_email_input.setText(primary)

            info_tags = []
            if website:
                clean_w = website.replace("https://", "").replace("http://", "").rstrip("/")
                info_tags.append(f"🌐 {clean_w}")
            if phone:
                info_tags.append(f"📞 {phone}")
            if recruiters:
                info_tags.append(f"👤 {recruiters[0]['name']}")
            info_str = f" | {', '.join(info_tags)}" if info_tags else ""

            self.hunt_status_lbl.setText(
                f"✅ Found: {primary}{info_str} ({len(candidates)} emails available)"
            )
            self.hunt_status_lbl.setStyleSheet("color: #34D399; font-size: 11px; font-weight: 600;")

            # Persist to company contacts repository
            if self.job.company_id:
                try:
                    self.contacts_repo.upsert(Contact(
                        company_id=self.job.company_id,
                        email=primary,
                        email_type="hr",
                        name=recruiters[0]["name"] if recruiters else None,
                        role=recruiters[0]["title"] if recruiters else "HR / Recruiter",
                        source_url=website or "OSINT Search Dork"
                    ))
                except Exception as e:
                    logger.debug(f"Failed to save hunter contact: {e}")
        else:
            self.hunt_status_lbl.setText("⚠️ No direct HR email discovered via OSINT. Please enter manually.")
            self.hunt_status_lbl.setStyleSheet("color: #FBBF24; font-size: 11px;")

    def _on_resume_changed(self, index: int):
        resume_data = self.resume_combo.currentData()
        if isinstance(resume_data, Resume):
            self.current_resume = resume_data

    def _get_candidate_info(self) -> Dict[str, str]:
        cfg = settings.get_config()
        return {
            "name": cfg.user_full_name or "[Your Name]",
            "email": cfg.user_email or "[Your Email]",
            "phone": cfg.user_phone or "[Your Phone]",
            "linkedin": cfg.user_linkedin or "[LinkedIn Profile]",
            "portfolio": cfg.user_portfolio or ""
        }

    def _start_ai_generation(self, custom_instructions: Optional[str] = None):
        """Launches the background worker for OpenRouter analysis."""
        cfg = settings.get_config()
        if not cfg.openrouter_api_key:
            self.analysis_summary_lbl.setText("💡 Add your OpenRouter API Key in Settings to enable automated AI match scoring and email generation.")
            self._fill_fallback_template()
            return

        resume_text = self.current_resume.extracted_text if self.current_resume else ""
        candidate_info = self._get_candidate_info()
        tone = self.tone_combo.currentText()

        self.progress_bar.setVisible(True)
        self.regen_btn.setEnabled(False)
        self.send_btn.setEnabled(False)
        self.analysis_summary_lbl.setText("Connecting to OpenRouter AI...")

        self.worker = AIAnalysisWorker(
            job_title=self.job.title,
            company_name=self.job.company_name or "Company",
            job_description=self.job.description or self.job.requirements or "",
            resume_text=resume_text,
            candidate_info=candidate_info,
            tone=tone,
            custom_instructions=custom_instructions
        )
        self.worker.finished.connect(self._on_ai_finished)
        self.worker.start()

    def _on_ai_finished(self, data: Dict[str, Any]):
        self.progress_bar.setVisible(False)
        self.regen_btn.setEnabled(True)
        self.send_btn.setEnabled(True)

        if not data.get("success"):
            err = data.get("error", "AI generation error")
            logger.warning(f"AI Generation warning: {err}")
            self.analysis_summary_lbl.setText(f"⚠️ AI Notice: {err}")
            if not self.body_edit.toPlainText().strip():
                self._fill_fallback_template()
            return

        res: AIAnalysisResult = data.get("result")
        self.analysis_result = res

        # Update Match Score Badge
        self.match_badge.setText(f"⚡ Match Score: {res.match_score}%")
        self.match_badge.setStyleSheet(get_relevance_badge_style(res.match_score))
        self.analysis_summary_lbl.setText(res.summary or "AI analysis completed.")

        # Render Skills Badges
        self._render_skills_badges(res)

        # Fill Subject and Body
        if res.generated_subject:
            self.subject_input.setText(res.generated_subject)
        if res.generated_body:
            self.body_edit.setText(res.generated_body)

    def _render_skills_badges(self, res: AIAnalysisResult):
        # Clear existing badges
        while self.skills_layout.count():
            item = self.skills_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if res.matched_skills:
            lbl = QLabel("<b>Matched Skills:</b>")
            lbl.setStyleSheet("font-size: 11px; color: #34D399;")
            self.skills_layout.addWidget(lbl)
            for sk in res.matched_skills[:6]:
                badge = QLabel(f"✓ {sk}")
                badge.setStyleSheet("background-color: #064E3B; color: #34D399; border: 1px solid #059669; padding: 2px 6px; border-radius: 4px; font-size: 10px; font-weight: 700;")
                self.skills_layout.addWidget(badge)

        if res.missing_skills:
            lbl_miss = QLabel("<b>Preferred / Missing:</b>")
            lbl_miss.setStyleSheet("font-size: 11px; color: #94A3B8; margin-left: 8px;")
            self.skills_layout.addWidget(lbl_miss)
            for sk in res.missing_skills[:4]:
                badge = QLabel(f"- {sk}")
                badge.setStyleSheet("background-color: #1E293B; color: #94A3B8; border: 1px solid #334155; padding: 2px 6px; border-radius: 4px; font-size: 10px;")
                self.skills_layout.addWidget(badge)

        self.skills_layout.addStretch(1)

    def _fill_fallback_template(self):
        """Populates a professional email template if OpenRouter is not configured."""
        cand = self._get_candidate_info()
        comp = self.job.company_name or "your company"
        title = self.job.title

        subject = f"Application for {title} – {cand['name']}"
        body = (
            f"Dear Hiring Manager,\n\n"
            f"I am writing to express my strong interest in the {title} position at {comp}.\n\n"
            f"With my background in software development and proven experience in building scalable solutions, "
            f"I am confident in my ability to make an immediate positive contribution to your team.\n\n"
            f"I have attached my resume for your consideration. I would welcome the opportunity to discuss "
            f"how my experience and skills align with your engineering goals.\n\n"
            f"Thank you for your time and consideration.\n\n"
            f"Best regards,\n"
            f"{cand['name']}\n"
            f"{cand['phone']}\n"
            f"{cand['email']}\n"
            f"{cand['linkedin']}"
        )
        self.subject_input.setText(subject)
        self.body_edit.setText(body)

    def _regenerate_email(self):
        custom = self.custom_prompt_input.text().strip()
        self._start_ai_generation(custom_instructions=custom if custom else "Refine and make more impactful.")

    def _copy_email_to_clipboard(self):
        subject = self.subject_input.text().strip()
        body = self.body_edit.toPlainText().strip()
        full_text = f"Subject: {subject}\n\n{body}"
        QApplication.clipboard().setText(full_text)
        QMessageBox.information(self, "Copied", "Email subject and body have been copied to your clipboard.")

    def _save_draft(self) -> int:
        """Saves or updates application draft in database."""
        hr_email = self.hr_email_input.text().strip()
        subject = self.subject_input.text().strip()
        body = self.body_edit.toPlainText().strip()
        score = self.analysis_result.match_score if self.analysis_result else self.job.relevance_score
        resume_id = self.current_resume.id if self.current_resume else None

        app = JobApplication(
            job_id=self.job.id or 0,
            company_id=self.job.company_id or 0,
            resume_id=resume_id,
            hr_email=hr_email,
            subject=subject,
            email_body=body,
            match_score=score,
            status="DRAFT",
            activity_log=f"{datetime.now().strftime('%H:%M')}  Application draft saved"
        )
        app_id = self.apps_repo.save_application(app)
        QMessageBox.information(self, "Draft Saved", "Application draft saved successfully.")
        return app_id

    def _open_in_chrome_and_send(self):
        """
        Executes the Chrome webmail dispatch workflow:
        1. Validates HR recipient, subject, and body.
        2. If Live Auto-Type is checked: launches visible Chrome, types live in front of user, attaches resume, and sends!
        3. Updates application status in database with timestamped activity log.
        """
        hr_email = self.hr_email_input.text().strip()
        subject = self.subject_input.text().strip()
        body = self.body_edit.toPlainText().strip()

        if not hr_email:
            reply = QMessageBox.question(
                self,
                "No HR Email Specified",
                "No HR email was entered. Would you like to proceed anyway and enter the email manually in Chrome?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if reply != QMessageBox.StandardButton.Yes:
                return

        provider_choice = self.provider_combo.currentText()
        provider = "gmail"
        if "Outlook" in provider_choice:
            provider = "outlook"
        elif "Default" in provider_choice:
            provider = "mailto"

        resume_path = None
        if self.current_resume and self.current_resume.file_path:
            resume_path = os.path.abspath(self.current_resume.file_path)

        score = self.analysis_result.match_score if self.analysis_result else self.job.relevance_score
        resume_id = self.current_resume.id if self.current_resume else None

        app = JobApplication(
            job_id=self.job.id or 0,
            company_id=self.job.company_id or 0,
            resume_id=resume_id,
            hr_email=hr_email,
            subject=subject,
            email_body=body,
            match_score=score,
            status="BROWSER_OPENED",
            activity_log=(
                f"{datetime.now().strftime('%H:%M')}  Job analyzed & match score {score}%\n"
                f"{datetime.now().strftime('%H:%M')}  Personalized email generated\n"
                f"{datetime.now().strftime('%H:%M')}  Chrome automation initiated"
            )
        )
        self.active_app_id = self.apps_repo.save_application(app)

        if provider == "gmail":
            auto_send = self.auto_send_check.isChecked()
            # Launch Live Chrome Worker with Real-Time Typing & Auto Attach & Send
            self.live_status_lbl.setVisible(True)
            self.live_status_lbl.setText("🚀 Launching Chrome in front of you...")
            self.send_btn.setEnabled(False)
            self.send_btn.setText("⏳ Automating in Chrome...")

            self.chrome_worker = LiveChromeSenderWorker(
                to_email=hr_email,
                subject=subject,
                body=body,
                resume_path=resume_path,
                auto_send=auto_send
            )
            self.chrome_worker.status_updated.connect(self._on_chrome_status_updated)
            self.chrome_worker.finished.connect(self._on_chrome_worker_finished)
            self.chrome_worker.start()
        elif provider == "mailto":
            mailto_url = EmailAutomationService.create_mailto_url(hr_email, subject, body)
            webbrowser.open(mailto_url)
            self._finalize_dispatch(is_live=False)
        else:
            EmailAutomationService.open_in_chrome_webmail(
                to_email=hr_email,
                subject=subject,
                body=body,
                provider=provider,
                use_selenium=False
            )
            self._finalize_dispatch(is_live=False)

    def _on_chrome_status_updated(self, msg: str):
        self.live_status_lbl.setText(f"⚡ {msg}")

    def _on_chrome_worker_finished(self, result: dict):
        self.send_btn.setEnabled(True)
        self.send_btn.setText("🚀 Live Send with Chrome")
        if result.get("success"):
            self.live_status_lbl.setText("✅ Email typed, resume attached, and sent successfully!")
            if hasattr(self, "active_app_id") and self.active_app_id:
                self.apps_repo.update_status(
                    self.active_app_id,
                    "SENT",
                    "Automated live Chrome dispatch: typed email, attached resume, and clicked Send"
                )
            QMessageBox.information(
                self,
                "Application Sent Successfully",
                "Chrome live automation complete!\n\n"
                "• Recipient typed live\n"
                "• Personalized email typed live\n"
                "• Resume attached\n"
                "• Send button clicked automatically\n\n"
                "Your application status has been marked as SENT."
            )
            self.accept()
        else:
            err = result.get("error", "Unknown error")
            self.live_status_lbl.setText(f"⚠️ {err}")
            QMessageBox.warning(
                self,
                "Automation Notice",
                f"Chrome was opened. If Google login was required, please complete the sign-in in the opened Chrome window:\n{err}"
            )

    def _finalize_dispatch(self, is_live: bool = False):
        resume_notice = ""
        if self.current_resume and self.current_resume.file_path:
            rpath = os.path.abspath(self.current_resume.file_path)
            resume_notice = f"\n\n📎 Resume Path (ready to attach):\n{rpath}"

        QMessageBox.information(
            self,
            "Browser Opened — Final Confirmation",
            f"Chrome has been launched with your prefilled application!{resume_notice}\n\n"
            f"Review your message in Chrome, attach your resume, and click Send when ready.\n\n"
            f"Your application has been logged to the Applications Tracker."
        )
        self.accept()
