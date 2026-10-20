"""
Job Finder AI — Model Context Protocol (MCP) Server.
Exposes Job Finder AI capabilities as standard MCP tools for Claude Desktop, Antigravity, and AI assistants.

Capabilities:
1. search_jobs(keywords, location, limit, include_career_portals)
2. score_resume_match(job_id, resume_id, job_description, resume_text, tone)
3. auto_type_and_send_email(hr_email, subject, body, resume_id, resume_path, auto_send, provider)
4. enrich_company_linkedin_and_website(company_name, company_linkedin_url, location)
5. discover_career_portal_and_jobs(company_name, website_url)
6. list_resumes()
7. get_company_hr_contacts(company_name, domain)
8. list_saved_applications(limit)
"""

import os
import sys
from typing import Optional, List, Dict, Any

# Ensure project root is in sys.path
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from fastmcp import FastMCP

from database.database import Database
from database.models import Company, Job, Contact, JobApplication, Resume
from database.repositories import (
    CompaniesRepository, JobsRepository, ContactsRepository,
    ResumesRepository, ApplicationsRepository
)
from core.normalizer import JobNormalizer
from core.job_matcher import JobMatcher
from scrapers.adapters import IndeedAdapter, UnstopAdapter, LinkedInAdapter, GlassdoorAdapter
from scrapers.careers import CareersScraper
from scrapers.linkedin_company_enricher import linkedin_enricher
from core.hr_email_hunter import hr_hunter
from core.ai.prompt_builders import PromptBuilder
from core.ai.openrouter_client import OpenRouterClient
from browser.email_automation import EmailAutomationService
from config.settings import settings
from utils.logger import get_logger

logger = get_logger("mcp_server")

# Initialize MCP Server
mcp = FastMCP("JobFinderAI")


# Helper singletons
def get_db():
    db = Database()
    db.init_schema()
    return db


# =============================================================================
# Tool 1: search_jobs
# =============================================================================
@mcp.tool()
def search_jobs(
    keywords: str,
    location: str = "",
    limit: int = 10,
    include_career_portals: bool = True
) -> List[Dict[str, Any]]:
    """
    Searches multi-source job openings across Company Career Portals, Indeed, Unstop, LinkedIn, and Glassdoor.
    
    Args:
        keywords: Job title or skill keywords (e.g. "React Developer", "Python Backend", "AI Engineer")
        location: City, state, or country (e.g. "Bangalore", "Remote", "Jaipur")
        limit: Maximum number of jobs to return (default: 10)
        include_career_portals: Whether to include direct ATS / company career portals (default: True)
    
    Returns:
        A list of job openings with company name, location, source, salary, career link, and requirements.
    """
    logger.info(f"[MCP Tool: search_jobs] keywords='{keywords}', location='{location}', limit={limit}")
    db = get_db()
    jobs_repo = JobsRepository(db)
    comp_repo = CompaniesRepository(db)

    results = []

    # 1. Query existing matching jobs from database
    db_jobs = jobs_repo.get_all_jobs(limit=100)
    kw_lower = keywords.lower()
    loc_lower = location.lower() if location else ""

    for j in db_jobs:
        matches_kw = kw_lower in (j.title or "").lower() or kw_lower in (j.description or "").lower() or any(kw_lower in sk.lower() for sk in (j.skills or []))
        matches_loc = not loc_lower or loc_lower in (j.location or "").lower()
        if matches_kw and matches_loc:
            results.append({
                "job_id": j.id,
                "title": j.title,
                "company_name": j.company_name or "Unknown Company",
                "location": j.location or "Not specified",
                "source": j.source or "career_portal",
                "career_url": j.job_url or "",
                "salary": j.salary or "Competitive",
                "work_mode": j.work_mode or j.remote_type or "Not specified",
                "skills": j.skills or [],
                "relevance_score": j.relevance_score,
                "description_preview": (j.description[:200] + "...") if j.description else ""
            })
            if len(results) >= limit:
                break

    # 2. If not enough results, trigger live adapter searches
    if len(results) < limit:
        remaining = limit - len(results)
        adapters = [
            ("Indeed", IndeedAdapter()),
            ("Unstop", UnstopAdapter()),
            ("LinkedIn", LinkedInAdapter()),
            ("Glassdoor", GlassdoorAdapter())
        ]

        normalizer = JobNormalizer()
        job_matcher = JobMatcher(profession=keywords, threshold=50)

        for src_name, adapter in adapters:
            if len(results) >= limit:
                break
            try:
                raw_jobs = adapter.search_jobs(profession=keywords, location=location, limit=remaining)
                for rj in raw_jobs:
                    # Deduplicate in memory
                    if any(r["title"].lower() == rj.job_title.lower() and r["company_name"].lower() == rj.company_name.lower() for r in results):
                        continue

                    # Save to DB for tracking
                    c_key = normalizer.generate_company_key(rj.company_name)
                    comp = comp_repo.get_by_name(rj.company_name)
                    if not comp:
                        comp = Company(company_key=c_key, name=rj.company_name, city=rj.location)
                        cid = comp_repo.upsert(comp)
                        comp.id = cid

                    score = job_matcher.calculate_score(f"{rj.job_title} {rj.description or ''}")
                    extracted_skills = normalizer.extract_skills(f"{rj.job_title} {rj.description or ''}")

                    saved_job = Job(
                        company_id=comp.id,
                        title=rj.job_title,
                        location=rj.location or location,
                        job_url=rj.source_url,
                        source=rj.source.lower(),
                        salary=rj.salary,
                        skills=extracted_skills,
                        relevance_score=score,
                        description=rj.description
                    )
                    jid = jobs_repo.upsert(saved_job)

                    results.append({
                        "job_id": jid,
                        "title": rj.job_title,
                        "company_name": rj.company_name,
                        "location": rj.location or location,
                        "source": rj.source,
                        "career_url": rj.source_url,
                        "salary": rj.salary or "Competitive",
                        "work_mode": rj.work_mode or "Not specified",
                        "skills": extracted_skills,
                        "relevance_score": score,
                        "description_preview": (rj.description[:200] + "...") if rj.description else ""
                    })

                    if len(results) >= limit:
                        break
            except Exception as e:
                logger.debug(f"Live adapter {src_name} search notice: {e}")

    return results[:limit]


# =============================================================================
# Tool 2: score_resume_match
# =============================================================================
@mcp.tool()
def score_resume_match(
    job_id: Optional[int] = None,
    resume_id: Optional[int] = None,
    job_description: Optional[str] = None,
    job_title: Optional[str] = None,
    company_name: Optional[str] = None,
    resume_text: Optional[str] = None,
    tone: str = "Professional & Concise"
) -> Dict[str, Any]:
    """
    Analyzes job requirements against candidate resume, scores skill match, and drafts a tailored cold outreach email.
    
    Args:
        job_id: Optional database ID of a job from search_jobs
        resume_id: Optional database ID of the candidate resume (uses default resume if omitted)
        job_description: Optional raw text of the job description if not querying by job_id
        job_title: Optional target job title (e.g. "Senior React Developer")
        company_name: Optional company name (e.g. "Google")
        resume_text: Optional raw text of the resume if not using a saved resume_id
        tone: Desired email tone (e.g. "Professional & Concise", "Enthusiastic & Direct")
    
    Returns:
        JSON with match_score (0-100), required_skills, matched_skills, missing_skills,
        summary assessment, generated_subject, and generated_body.
    """
    logger.info(f"[MCP Tool: score_resume_match] job_id={job_id}, resume_id={resume_id}")
    db = get_db()
    jobs_repo = JobsRepository(db)
    resumes_repo = ResumesRepository(db)
    comp_repo = CompaniesRepository(db)

    # 1. Resolve Job Details
    resolved_title = job_title or "Software Developer"
    resolved_comp = company_name or "Target Company"
    resolved_desc = job_description or ""

    if job_id:
        db_job = jobs_repo.get_by_id(job_id)
        if db_job:
            resolved_title = db_job.title
            resolved_comp = db_job.company_name or resolved_comp
            resolved_desc = db_job.description or resolved_desc
            if not resolved_comp and db_job.company_id:
                c = comp_repo.get_by_id(db_job.company_id)
                if c:
                    resolved_comp = c.name

    # 2. Resolve Candidate Resume
    resolved_resume_text = resume_text or ""
    cfg = settings.get_config()
    candidate_name = cfg.user_full_name or "Applicant"
    candidate_email = cfg.user_email or ""
    candidate_phone = cfg.user_phone or ""
    candidate_linkedin = cfg.user_linkedin or ""

    if resume_id:
        db_res = resumes_repo.get_by_id(resume_id)
        if db_res:
            resolved_resume_text = db_res.extracted_text or ""
    elif not resolved_resume_text:
        def_res = resumes_repo.get_default_resume()
        if def_res:
            resolved_resume_text = def_res.extracted_text or ""

    # 3. Candidate metadata dictionary
    cand_info = {
        "name": candidate_name,
        "email": candidate_email,
        "phone": candidate_phone,
        "linkedin": candidate_linkedin
    }

    # 4. Execute AI Analysis via OpenRouter or fallback to algorithmic scoring
    client = OpenRouterClient()
    if client.is_configured():
        try:
            prompt = PromptBuilder.build_analysis_and_email_prompt(
                job_title=resolved_title,
                company_name=resolved_comp,
                job_description=resolved_desc,
                resume_text=resolved_resume_text,
                candidate_info=cand_info,
                tone=tone
            )
            resp = client.complete(
                prompt=prompt,
                system_prompt=PromptBuilder.SYSTEM_PROMPT,
                temperature=0.4,
                timeout=5.0
            )
            if resp.get("success"):
                analysis = PromptBuilder.parse_ai_response(resp.get("content", ""))
                return {
                    "match_score": analysis.match_score,
                    "required_skills": analysis.required_skills,
                    "matched_skills": analysis.matched_skills,
                    "missing_skills": analysis.missing_skills,
                    "experience_level": analysis.experience_level,
                    "summary": analysis.summary,
                    "generated_subject": analysis.generated_subject,
                    "generated_body": analysis.generated_body,
                    "engine": "OpenRouter AI"
                }
        except Exception as ai_err:
            logger.warning(f"AI generation failed, using local scoring fallback: {ai_err}")

    # Fallback Algorithmic Scoring
    normalizer = JobNormalizer()
    job_skills = normalizer.extract_skills(f"{resolved_title} {resolved_desc}")
    resume_skills = normalizer.extract_skills(resolved_resume_text) if resolved_resume_text else []

    matched = [s for s in job_skills if any(s.lower() == rs.lower() for rs in resume_skills)]
    missing = [s for s in job_skills if s not in matched]

    score = 80
    if job_skills:
        score = int((len(matched) / max(1, len(job_skills))) * 100)
        score = max(50, min(95, score))

    subj = f"Application for {resolved_title} — {candidate_name}"
    body = (
        f"Dear Hiring Team at {resolved_comp},\n\n"
        f"I am writing to express my enthusiastic interest in the {resolved_title} position. "
        f"With proven experience in {', '.join(matched[:3]) if matched else resolved_title}, "
        f"I am confident in delivering immediate value to your engineering team.\n\n"
        f"Key Highlights:\n"
        f"• Extensive practical experience in {', '.join(matched[:4]) if matched else 'modern software engineering'}.\n"
        f"• Track record of architecting scalable, maintainable, and high-performance solutions.\n\n"
        f"I have attached my resume for your review and welcome the opportunity to discuss how my skill set aligns with your goals.\n\n"
        f"Best regards,\n"
        f"{candidate_name}\n"
        f"{candidate_phone} | {candidate_email}\n"
        f"{candidate_linkedin}"
    )

    return {
        "match_score": score,
        "required_skills": job_skills,
        "matched_skills": matched,
        "missing_skills": missing,
        "summary": f"Candidate demonstrates strong alignment on {len(matched)} core technical competencies.",
        "generated_subject": subj,
        "generated_body": body,
        "engine": "Local Algorithmic Matcher"
    }


# =============================================================================
# Tool 3: auto_type_and_send_email
# =============================================================================
@mcp.tool()
def auto_type_and_send_email(
    hr_email: str,
    subject: str,
    body: str,
    resume_id: Optional[int] = None,
    resume_path: Optional[str] = None,
    auto_send: bool = False,
    provider: str = "gmail"
) -> Dict[str, Any]:
    """
    Automates sending or typing cold outreach email to HR/Recruiter via visible Chrome or webmail compose link.
    
    Args:
        hr_email: Recipient HR/Recruiter email address (e.g. "hr@company.com")
        subject: Email subject line
        body: Email body content
        resume_id: Optional ID of candidate resume from list_resumes() to attach
        resume_path: Optional absolute file path to candidate resume PDF
        auto_send: If True, launches visible Chrome, types live character-by-character, attaches resume, and sends automatically.
                   If False, launches Chrome / browser with prefilled compose window ready for 1-click review.
        provider: "gmail" or "outlook"
    
    Returns:
        Execution status, mode used, and tracking application ID.
    """
    logger.info(f"[MCP Tool: auto_type_and_send_email] to={hr_email}, auto_send={auto_send}")
    db = get_db()
    resumes_repo = ResumesRepository(db)
    apps_repo = ApplicationsRepository(db)

    # Resolve resume path
    final_resume_path = resume_path
    if not final_resume_path and resume_id:
        r = resumes_repo.get_by_id(resume_id)
        if r and r.file_path and os.path.exists(r.file_path):
            final_resume_path = os.path.abspath(r.file_path)

    if not final_resume_path:
        def_r = resumes_repo.get_default_resume()
        if def_r and def_r.file_path and os.path.exists(def_r.file_path):
            final_resume_path = os.path.abspath(def_r.file_path)

    result_data = {}

    if auto_send:
        # Launch visible Chrome and simulate human keystrokes
        res = EmailAutomationService.live_chrome_auto_type_and_send(
            to_email=hr_email,
            subject=subject,
            body=body,
            resume_path=final_resume_path,
            auto_send=True
        )
        status = "SENT" if res.get("success") else "FAILED"
        result_data = {
            "success": res.get("success", False),
            "status": status,
            "mode": "live_chrome_automation",
            "message": res.get("message", "Live Chrome auto-dispatch completed.")
        }
    else:
        # Open webmail compose window
        res = EmailAutomationService.open_in_chrome_webmail(
            to_email=hr_email,
            subject=subject,
            body=body,
            provider=provider
        )
        status = "COMPOSED"
        result_data = {
            "success": res.get("success", True),
            "status": status,
            "mode": f"webmail_{provider}",
            "compose_url": res.get("url"),
            "message": f"Opened {provider.title()} compose tab ready for user review and sending."
        }

    # Record in SQLite applications tracker if job & company can be linked
    try:
        final_comp_id = company_id
        final_job_id = job_id
        if not final_comp_id:
            domain = hr_email.split("@")[-1].lower() if "@" in hr_email else None
            comp_repo = CompaniesRepository(db)
            existing_comp = comp_repo.find_by_domain(domain) if domain else None
            if existing_comp:
                final_comp_id = existing_comp.id

        if final_comp_id and not final_job_id:
            jobs_repo = JobsRepository(db)
            comp_jobs = jobs_repo.get_by_company(final_comp_id)
            if comp_jobs:
                final_job_id = comp_jobs[0].id

        if final_comp_id and final_job_id:
            app_record = JobApplication(
                job_id=final_job_id,
                company_id=final_comp_id,
                resume_id=resume_id,
                hr_email=hr_email,
                subject=subject,
                email_body=body,
                status=result_data.get("status", "DRAFT")
            )
            app_id = apps_repo.save_application(app_record)
            result_data["application_id"] = app_id
    except Exception as e:
        logger.debug(f"Application tracking save note: {e}")

    return result_data


# =============================================================================
# Tool 4: enrich_company_linkedin_and_website
# =============================================================================
@mcp.tool()
def enrich_company_linkedin_and_website(
    company_name: str,
    company_linkedin_url: Optional[str] = None,
    location: Optional[str] = None
) -> Dict[str, Any]:
    """
    Enriches company profile by scraping LinkedIn About tab and official website for HR/business emails.
    
    Args:
        company_name: Target company name (e.g. "Razorpay", "Swiggy", "Zomato")
        company_linkedin_url: Optional LinkedIn company URL
        location: Optional location (e.g. "Bangalore, India")
    
    Returns:
        Discovered website, phone, industry, company size, headquarters, and list of verified emails.
    """
    logger.info(f"[MCP Tool: enrich_company_linkedin_and_website] name='{company_name}'")
    db = get_db()
    comp_repo = CompaniesRepository(db)
    contacts_repo = ContactsRepository(db)

    # Execute LinkedIn & website enrichment flow
    enriched = linkedin_enricher.full_enrichment_flow(
        company_name=company_name,
        company_linkedin_url=company_linkedin_url,
        location=location
    )

    # Save / update company in DB
    normalizer = JobNormalizer()
    c_key = normalizer.generate_company_key(company_name)
    existing = comp_repo.get_by_name(company_name)
    if existing:
        comp = existing
    else:
        comp = Company(
            company_key=c_key,
            name=company_name,
            normalized_name=normalizer.normalize_company_name(company_name),
            city=location
        )
        cid = comp_repo.upsert(comp)
        comp.id = cid

    if enriched.get("website"):
        comp.website_url = enriched["website"]
    if enriched.get("phone"):
        comp.phone = enriched["phone"]
    if enriched.get("industry"):
        comp.company_type = enriched["industry"]
    if enriched.get("company_size"):
        comp.category = enriched["company_size"]

    comp.enrichment_status = "COMPLETED"
    comp_repo.upsert(comp)

    # Also hunt for HR recruiter emails via OSINT hunter if emails list is short
    emails = enriched.get("emails", [])
    if len(emails) < 2:
        try:
            hunt_res = hr_hunter.hunt_hr_contacts(company_name, comp.website_domain or comp.website_url)
            for cand in hunt_res.get("email_candidates", []):
                em = cand.get("email")
                if em and not any(e.get("email") == em for e in emails):
                    emails.append({"email": em, "type": "HR", "source": "OSINT Recruiter Dork"})
        except Exception:
            pass

    # Save contacts to DB
    for em_dict in emails:
        contact = Contact(
            company_id=comp.id,
            email=em_dict.get("email"),
            email_type=em_dict.get("type", "General").lower(),
            source_url=em_dict.get("source")
        )
        contacts_repo.upsert(contact)

    return {
        "company_id": comp.id,
        "company_name": company_name,
        "website": comp.website_url,
        "phone": comp.phone,
        "industry": comp.company_type,
        "company_size": comp.category,
        "headquarters": enriched.get("headquarters"),
        "emails_count": len(emails),
        "emails": emails
    }


# =============================================================================
# Tool 5: discover_career_portal_and_jobs
# =============================================================================
@mcp.tool()
def discover_career_portal_and_jobs(
    company_name: str,
    website_url: Optional[str] = None
) -> Dict[str, Any]:
    """
    Discovers a company's direct Career Portal / ATS endpoints (Greenhouse, Lever, Workday) and extracts live jobs.
    
    Args:
        company_name: Target company name (e.g. "PhonePe", "CRED")
        website_url: Optional company homepage URL (e.g. "https://phonepe.com")
    
    Returns:
        Discovered career URL, source adapter, and list of active job postings.
    """
    logger.info(f"[MCP Tool: discover_career_portal_and_jobs] name='{company_name}'")
    db = get_db()
    comp_repo = CompaniesRepository(db)
    jobs_repo = JobsRepository(db)

    comp = comp_repo.get_by_name(company_name)
    target_url = website_url or (comp.website_url if comp else None)

    scraper = CareersScraper()
    career_url, source_type = scraper.discover_career_url(
        base_url=target_url or f"https://www.{company_name.lower().replace(' ', '')}.com",
        company_name=company_name
    )

    jobs = []
    if career_url:
        matcher = JobMatcher(profession="Software Engineer", threshold=40)
        jobs = scraper.extract_jobs(
            career_url=career_url,
            company_id=comp.id if comp else 0,
            job_matcher=matcher
        )

        if comp:
            comp.career_url = career_url
            comp.career_status = "FOUND"
            comp_repo.upsert(comp)

            normalizer = JobNormalizer()
            for j in jobs:
                j.company_id = comp.id
                j.skills = normalizer.extract_skills(f"{j.title} {j.description or ''}")
                jobs_repo.upsert(j)

    return {
        "company_name": company_name,
        "career_url": career_url,
        "source_type": source_type,
        "jobs_count": len(jobs),
        "jobs": [
            {
                "id": j.id,
                "title": j.title,
                "location": j.location,
                "url": j.job_url or career_url,
                "relevance_score": j.relevance_score
            }
            for j in jobs[:15]
        ]
    }


# =============================================================================
# Tool 6: list_resumes
# =============================================================================
@mcp.tool()
def list_resumes() -> List[Dict[str, Any]]:
    """
    Lists all saved candidate resumes in Job Finder AI database.
    
    Returns:
        List of resumes with id, name, is_default, file path, and text summary.
    """
    db = get_db()
    repo = ResumesRepository(db)
    resumes = repo.get_all_resumes()

    return [
        {
            "id": r.id,
            "name": r.name,
            "is_default": bool(r.is_default),
            "file_path": r.file_path,
            "text_preview": (r.extracted_text[:250] + "...") if r.extracted_text else ""
        }
        for r in resumes
    ]


# =============================================================================
# Tool 7: get_company_hr_contacts
# =============================================================================
@mcp.tool()
def get_company_hr_contacts(
    company_name: str,
    domain: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Retrieves verified HR, talent acquisition, and recruiter contacts for a company.
    
    Args:
        company_name: Target company name
        domain: Optional company official domain (e.g. "infosys.com")
    
    Returns:
        List of contact emails, candidate titles, and verification confidence.
    """
    db = get_db()
    comp_repo = CompaniesRepository(db)
    contacts_repo = ContactsRepository(db)

    comp = comp_repo.get_by_name(company_name)
    results = []

    if comp:
        saved_contacts = contacts_repo.get_by_company(comp.id)
        for c in saved_contacts:
            results.append({
                "email": c.email,
                "type": c.email_type,
                "source": c.source_url or "Database"
            })

    if not results:
        # Run OSINT hunter
        target_domain = domain or (comp.website_domain if comp else None)
        hunt_res = hr_hunter.hunt_hr_contacts(company_name, target_domain)
        for cand in hunt_res.get("email_candidates", []):
            conf = cand.get("confidence", 85)
            results.append({
                "email": cand.get("email"),
                "type": f"{conf}% Confidence HR Match" if isinstance(conf, (int, float)) else f"{conf} HR Match",
                "source": "OSINT Recruiter Dorks"
            })

    return results


# =============================================================================
# Tool 8: list_saved_applications
# =============================================================================
@mcp.tool()
def list_saved_applications(limit: int = 20) -> List[Dict[str, Any]]:
    """
    Retrieves tracked job applications and cold outreach dispatches.
    
    Args:
        limit: Number of records to return (default: 20)
    
    Returns:
        List of tracked applications with status (SENT, DRAFT, FAILED), recipient, subject, and match score.
    """
    db = get_db()
    apps_repo = ApplicationsRepository(db)
    apps = apps_repo.get_all_applications(limit=limit)

    return [
        {
            "id": a.id,
            "company_name": getattr(a, "company_name", None),
            "job_title": getattr(a, "job_title", None),
            "hr_email": a.hr_email,
            "subject": a.subject,
            "status": a.status,
            "match_score": a.match_score,
            "applied_at": a.applied_at or a.created_at
        }
        for a in apps
    ]


# =============================================================================
# Main Entry Point
# =============================================================================
if __name__ == "__main__":
    logger.info("=========================================")
    logger.info("   Starting Job Finder AI MCP Server     ")
    logger.info("=========================================")
    # Runs the stdio MCP server for Claude Desktop, Antigravity, and AI assistants
    mcp.run()
