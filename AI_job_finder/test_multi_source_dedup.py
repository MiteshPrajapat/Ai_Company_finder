"""
Comprehensive verification test for multi-source job aggregation, normalization,
company aliasing, and position deduplication.
"""

import os
import tempfile
from database.database import Database
from database.models import NormalizedJob, SearchSession, Company, Job, JobSource
from database.repositories import CompaniesRepository, JobsRepository, JobSourcesRepository, CompanyAliasesRepository, SearchesRepository
from core.normalizer import JobNormalizer
from core.deduplication_service import DeduplicationService
from scrapers.adapters import CareerPortalAdapter, IndeedAdapter, UnstopAdapter, LinkedInAdapter, GlassdoorAdapter


def test_job_normalizer():
    print("Testing JobNormalizer...")
    norm = JobNormalizer()

    # 1. Company normalization
    c1 = norm.normalize_company_name("Google India Pvt. Ltd.")
    c2 = norm.normalize_company_name("Google LLC")
    c3 = norm.normalize_company_name("Google Inc.")
    assert c1 == "google", f"Expected 'google', got '{c1}'"
    assert c2 == "google", f"Expected 'google', got '{c2}'"
    assert c3 == "google", f"Expected 'google', got '{c3}'"

    t1 = norm.normalize_company_name("Tata Consultancy Services Limited")
    assert "tata consultancy" in t1

    # 2. Title normalization
    t_norm1 = norm.normalize_job_title("Sr. Software Engineer (Immediate Joiner)")
    assert "senior software engineer" in t_norm1, f"Got {t_norm1}"

    t_norm2 = norm.normalize_job_title("SWE II [Remote] - Urgent Hiring")
    assert "software engineer ii" in t_norm2, f"Got {t_norm2}"

    # 3. Skills extraction
    skills = norm.extract_skills("Looking for Senior Python Developer with React, Docker, and AWS experience.")
    assert "Python" in skills
    assert "React" in skills
    assert "Docker" in skills
    assert "AWS" in skills

    print("[PASS] JobNormalizer passed all checks.")


def test_deduplication_and_relational_storage():
    print("Testing DeduplicationService & Relational SQLite schema...")
    
    # Use temporary test database
    temp_dir = tempfile.mkdtemp()
    test_db_path = os.path.join(temp_dir, "test_job_finder.db")
    Database._instance = None
    db = Database(test_db_path)
    db.init_schema()

    comp_repo = CompaniesRepository(db)
    jobs_repo = JobsRepository(db)
    src_repo = JobSourcesRepository(db)
    alias_repo = CompanyAliasesRepository(db)
    search_repo = SearchesRepository(db)

    session_id = search_repo.create(SearchSession(city="Bangalore", country="India", profession="Software Engineer"))

    dedup = DeduplicationService(
        companies_repo=comp_repo,
        jobs_repo=jobs_repo,
        sources_repo=src_repo
    )

    # 1. Ingest Job from Career Portal: Google Software Engineer
    job1_norm = NormalizedJob(
        company_name="Google LLC",
        job_title="Software Engineer",
        source="career_portal",
        source_url="https://careers.google.com/jobs/results/123",
        company_domain="google.com",
        company_website="https://google.com",
        location="Bangalore, Karnataka, India",
        remote_type="Hybrid",
        description="Core software engineering role focusing on distributed systems, Python, and Go.",
        skills=["Python", "Go", "Docker"]
    )
    job1, is_new1 = dedup.process_normalized_job(job1_norm, search_id=session_id)
    assert is_new1 is True, "First job should be created as new"
    assert job1.company_id > 0
    assert len(job1.sources) == 1
    assert job1.sources[0].source == "career_portal"
    assert job1.sources[0].is_primary is True

    # 2. Ingest duplicate job from LinkedIn: Google India Pvt Ltd - Software Engineer Bangalore
    job2_norm = NormalizedJob(
        company_name="Google India Pvt Ltd",  # Different company name variation!
        job_title="Software Engineer",
        source="linkedin",
        source_url="https://linkedin.com/jobs/view/456",
        company_domain="google.com",
        location="Bangalore",
        description="Software Engineer at Google Bangalore",
        skills=["Python", "Distributed Systems"]
    )
    job2, is_new2 = dedup.process_normalized_job(job2_norm, search_id=session_id)
    assert is_new2 is False, "Same position across sources should be merged"
    assert job2.id == job1.id, "Job ID should match existing unified position"
    assert job2.company_id == job1.company_id, "Company ID should match resolved canonical company"
    assert len(job2.sources) == 2, f"Expected 2 attached sources, got {len(job2.sources)}"
    
    source_names = [s.source for s in job2.sources]
    assert "career_portal" in source_names
    assert "linkedin" in source_names

    # 3. Ingest duplicate job from Indeed: Google - Software Engineer
    job3_norm = NormalizedJob(
        company_name="Google",
        job_title="Software Engineer",
        source="indeed",
        source_url="https://indeed.com/viewjob?jk=789",
        company_domain="google.com",
        location="Bangalore",
        description="Indeed listing for Google Software Engineer"
    )
    job3, is_new3 = dedup.process_normalized_job(job3_norm, search_id=session_id)
    assert is_new3 is False, "Indeed listing should also merge into same position"
    assert len(job3.sources) == 3, f"Expected 3 attached sources, got {len(job3.sources)}"

    # 4. Ingest DIFFERENT position under same company: Google - Frontend Developer
    job4_norm = NormalizedJob(
        company_name="Google",
        job_title="Frontend Developer",  # Different position!
        source="career_portal",
        source_url="https://careers.google.com/jobs/results/999",
        company_domain="google.com",
        location="Bangalore",
        remote_type="Remote",
        description="Frontend Developer building UI with React and TypeScript.",
        skills=["React", "TypeScript", "CSS"]
    )
    job4, is_new4 = dedup.process_normalized_job(job4_norm, search_id=session_id)
    assert is_new4 is True, "Different position must be created as a separate job"
    assert job4.id != job1.id, "Different position must have a distinct job ID"
    assert job4.company_id == job1.company_id, "Must belong to the same parent Google company"

    # Verify positions under company
    all_google_jobs = jobs_repo.get_by_company(job1.company_id)
    assert len(all_google_jobs) == 2, f"Expected exactly 2 distinct positions, got {len(all_google_jobs)}"

    print("[PASS] Deduplication & Relational Storage passed all checks.")


def test_adapters_instantiation():
    print("Testing adapter initialization...")
    c_ad = CareerPortalAdapter()
    i_ad = IndeedAdapter()
    u_ad = UnstopAdapter()
    l_ad = LinkedInAdapter()
    g_ad = GlassdoorAdapter()

    assert c_ad.source_name == "career_portal"
    assert i_ad.source_name == "indeed"
    assert u_ad.source_name == "unstop"
    assert l_ad.source_name == "linkedin"
    assert g_ad.source_name == "glassdoor"
    print("[PASS] All 5 source adapters initialized successfully.")


def test_user_requested_scenario():
    print("Testing User Requested Scenario (Google Maps -> Career Portal -> Indeed -> LinkedIn)...")
    temp_dir = tempfile.mkdtemp()
    test_db_path = os.path.join(temp_dir, "test_scenario.db")
    Database._instance = None
    db = Database(test_db_path)
    db.init_schema()

    comp_repo = CompaniesRepository(db)
    jobs_repo = JobsRepository(db)
    src_repo = JobSourcesRepository(db)
    search_repo = SearchesRepository(db)

    session_id = search_repo.create(SearchSession(city="Jaipur", country="India", profession="Software Engineer"))

    dedup = DeduplicationService(
        companies_repo=comp_repo,
        jobs_repo=jobs_repo,
        sources_repo=src_repo
    )

    # 1. Google Maps result -> ABC Company (lat: 26.9124, lng: 75.7873, website: abc.com)
    # Discovered via Career Portal: Software Engineer
    job1_norm = NormalizedJob(
        company_name="ABC Company Limited",
        job_title="Software Engineer",
        source="career_portal",
        source_url="https://abc.com/careers/swe",
        company_domain="abc.com",
        company_website="https://abc.com",
        latitude=26.9124,
        longitude=75.7873,
        location="Jaipur, Rajasthan",
        description="Software Engineer at ABC Company"
    )
    job1, is_new1 = dedup.process_normalized_job(job1_norm, search_id=session_id)
    assert is_new1 is True

    # 2. Indeed: ABC Company - Software Engineer
    job2_norm = NormalizedJob(
        company_name="ABC Company",
        job_title="Software Engineer",
        source="indeed",
        source_url="https://indeed.com/viewjob?id=abc1",
        company_domain="abc.com",
        location="Jaipur",
        description="Indeed Software Engineer role at ABC Company"
    )
    job2, is_new2 = dedup.process_normalized_job(job2_norm, search_id=session_id)
    assert is_new2 is False
    assert job2.id == job1.id
    assert job2.company_id == job1.company_id

    # 3. LinkedIn: ABC Company - Java Developer (Different position under same company)
    job3_norm = NormalizedJob(
        company_name="ABC Company Pvt Ltd",
        job_title="Java Developer",
        source="linkedin",
        source_url="https://linkedin.com/jobs/view/abc2",
        company_domain="abc.com",
        location="Jaipur",
        description="Java Developer building backend services at ABC Company"
    )
    job3, is_new3 = dedup.process_normalized_job(job3_norm, search_id=session_id)
    assert is_new3 is True
    assert job3.id != job1.id
    assert job3.company_id == job1.company_id

    # Verify Expected Database Structure:
    # 1. Exact 1 Company: ABC Company
    all_comps = comp_repo.get_companies(search_id=session_id)
    assert len(all_comps) == 1, f"Expected 1 company, got {len(all_comps)}"
    company = all_comps[0]
    assert "abc" in company.normalized_name

    # 2. Exact 2 Jobs under company 1: Software Engineer & Java Developer
    comp_jobs = jobs_repo.get_by_company(company.id)
    assert len(comp_jobs) == 2, f"Expected 2 jobs, got {len(comp_jobs)}"

    # 3. job_sources: Software Engineer has Career Portal + Indeed, Java Developer has LinkedIn
    swe_job = next(j for j in comp_jobs if "software engineer" in j.normalized_title.lower())
    java_job = next(j for j in comp_jobs if "java developer" in j.normalized_title.lower())

    swe_sources = [s.source for s in swe_job.sources]
    java_sources = [s.source for s in java_job.sources]

    assert "career_portal" in swe_sources, f"Expected career_portal in swe_sources, got {swe_sources}"
    assert "indeed" in swe_sources, f"Expected indeed in swe_sources, got {swe_sources}"
    assert "linkedin" in java_sources, f"Expected linkedin in java_sources, got {java_sources}"

    print("[PASS] User Requested Scenario passed with exact expected database state!")


if __name__ == "__main__":
    test_job_normalizer()
    test_deduplication_and_relational_storage()
    test_user_requested_scenario()
    test_adapters_instantiation()
    print("\n[SUCCESS] ALL MULTI-SOURCE & DEDUPLICATION TESTS PASSED!")
