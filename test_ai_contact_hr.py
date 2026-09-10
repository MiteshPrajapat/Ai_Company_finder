"""
Comprehensive test suite for AI Contact HR, OpenRouter prompt engineering, Resume parsing, and Application repositories.
"""

import os
import sys
import tempfile
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from database.database import Database
from database.models import Resume, JobApplication, Job, Company
from database.repositories import ResumesRepository, ApplicationsRepository, CompaniesRepository, JobsRepository
from core.ai.resume_extractor import ResumeExtractor
from core.ai.prompt_builders import PromptBuilder
from core.ai.openrouter_client import OpenRouterClient
from browser.email_automation import EmailAutomationService


def test_resume_extraction():
    print("Testing Resume Extraction...")
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False, encoding="utf-8") as f:
        f.write("John Doe\nExperienced Java & Spring Boot Developer with 3 years of building REST APIs.")
        temp_path = f.name

    try:
        extracted = ResumeExtractor.extract_text(temp_path)
        assert "Java" in extracted
        assert "Spring Boot" in extracted
        print("  [OK] Plain text / Markdown resume extraction passed.")
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)


def test_resumes_repository():
    print("Testing Resumes Repository...")
    db_file = os.path.join(tempfile.gettempdir(), "test_job_finder_ai.db")
    if os.path.exists(db_file):
        os.remove(db_file)

    db = Database(db_file)
    repo = ResumesRepository(db)

    # 1. Add resume
    r1 = Resume(name="Backend_Resume.pdf", file_path="/path/to/resume1.pdf", extracted_text="Java Developer", is_default=True)
    r1_id = repo.add_resume(r1)
    assert r1_id > 0

    # 2. Add second resume
    r2 = Resume(name="Fullstack_Resume.pdf", file_path="/path/to/resume2.pdf", extracted_text="Fullstack Developer", is_default=False)
    r2_id = repo.add_resume(r2)

    # 3. Check default resume
    def_resume = repo.get_default_resume()
    assert def_resume is not None
    assert def_resume.id == r1_id

    # 4. Set second resume as default
    repo.set_default_resume(r2_id)
    def_resume_2 = repo.get_default_resume()
    assert def_resume_2.id == r2_id

    # 5. List all
    all_resumes = repo.get_all_resumes()
    assert len(all_resumes) == 2
    print("  [OK] Resumes Repository CRUD and default toggle passed.")


def test_applications_repository():
    print("Testing Applications Repository...")
    db_file = os.path.join(tempfile.gettempdir(), "test_job_finder_ai.db")
    db = Database(db_file)

    comp_repo = CompaniesRepository(db)
    jobs_repo = JobsRepository(db)
    apps_repo = ApplicationsRepository(db)

    # Setup company and job
    comp = Company(company_key="test_corp", name="Test Corp")
    comp_id = comp_repo.upsert(comp)

    job = Job(company_id=comp_id, title="Senior Java Developer", relevance_score=90)
    job_id = jobs_repo.upsert(job)

    # Create application
    app = JobApplication(
        job_id=job_id,
        company_id=comp_id,
        hr_email="recruiter@testcorp.com",
        subject="Application for Senior Java Developer - John Doe",
        email_body="Dear Hiring Manager,\n\nI am thrilled to apply...",
        match_score=92,
        status="DRAFT"
    )
    app_id = apps_repo.save_application(app)
    assert app_id > 0

    # Retrieve
    saved_app = apps_repo.get_application(app_id)
    assert saved_app is not None
    assert saved_app.hr_email == "recruiter@testcorp.com"
    assert saved_app.match_score == 92

    # Update status
    apps_repo.update_status(app_id, "SENT", "Sent email to recruiter")
    updated = apps_repo.get_application(app_id)
    assert updated.status == "SENT"
    assert "Sent email to recruiter" in updated.activity_log
    print("  [OK] Applications Repository saving, status updates, and activity logs passed.")


def test_prompt_builder_and_parser():
    print("Testing Prompt Builder and Parser...")
    job_desc = "Looking for a Senior Java Developer with Spring Boot, Microservices, and SQL skills."
    resume_text = "John Doe. 3+ years experience with Java, Spring Boot, PostgreSQL, Docker."
    cand_info = {
        "name": "John Doe",
        "email": "john@example.com",
        "phone": "+1-555-0123",
        "linkedin": "https://linkedin.com/in/johndoe"
    }

    prompt = PromptBuilder.build_analysis_and_email_prompt(
        job_title="Senior Java Developer",
        company_name="Test Corp",
        job_description=job_desc,
        resume_text=resume_text,
        candidate_info=cand_info,
        tone="Professional & Concise"
    )
    assert "Senior Java Developer" in prompt
    assert "John Doe" in prompt

    # Test parser with mock LLM response
    mock_json_response = """```json
{
  "match_score": 88,
  "required_skills": ["Java", "Spring Boot", "Microservices", "SQL"],
  "preferred_skills": ["Docker", "Kubernetes"],
  "matched_skills": ["Java", "Spring Boot", "SQL", "Docker"],
  "missing_skills": ["Microservices", "Kubernetes"],
  "experience_level": "3+ years",
  "summary": "Strong backend fit with Java and Spring Boot experience.",
  "generated_subject": "Application for Senior Java Developer - John Doe",
  "generated_body": "Dear Hiring Manager,\\n\\nI am writing to express my enthusiasm for the Senior Java Developer position at Test Corp."
}
```"""

    res = PromptBuilder.parse_ai_response(mock_json_response)
    assert res.match_score == 88
    assert "Java" in res.matched_skills
    assert "Microservices" in res.missing_skills
    assert "Application for Senior Java Developer" in res.generated_subject
    print("  [OK] Prompt Builder and JSON parsing passed.")


def test_email_automation_urls():
    print("Testing Email Automation URLs...")
    gmail_url = EmailAutomationService.create_gmail_compose_url(
        to_email="hr@testcorp.com",
        subject="Application for Developer",
        body="Hello Hiring Manager,\n\nTest application."
    )
    assert "mail.google.com" in gmail_url
    assert "to=hr%40testcorp.com" in gmail_url or "to=hr" in gmail_url

    outlook_url = EmailAutomationService.create_outlook_compose_url(
        to_email="hr@testcorp.com",
        subject="Application",
        body="Test"
    )
    assert "outlook.live.com" in outlook_url

    mailto_url = EmailAutomationService.create_mailto_url(
        to_email="hr@testcorp.com",
        subject="Application",
        body="Test"
    )
    assert mailto_url.startswith("mailto:hr@testcorp.com?")
    print("  [OK] Email Automation compose URL construction passed.")


if __name__ == "__main__":
    print("\n" + "="*50)
    print("  RUNNING JOB FINDER AI -- AI & CONTACT HR TEST SUITE")
    print("="*50 + "\n")
    test_resume_extraction()
    test_resumes_repository()
    test_applications_repository()
    test_prompt_builder_and_parser()
    test_email_automation_urls()
    print("\n" + "="*50)
    print("  ALL TESTS PASSED SUCCESSFULLY! [OK]")
    print("="*50 + "\n")
