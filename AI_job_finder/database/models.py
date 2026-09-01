"""
Data models for Job Finder AI.
Supports multi-source aggregation, job deduplication, company aliasing, and source tracking.
"""

from dataclasses import dataclass, field, asdict
from typing import Optional, List, Dict, Any
from datetime import datetime


@dataclass
class SearchSession:
    id: Optional[int] = None
    city: str = ""
    state: str = ""
    country: str = ""
    profession: str = ""
    custom_profession: Optional[str] = None
    company_type: str = ""
    custom_company_type: Optional[str] = None
    result_limit: int = 10
    enrich_enabled: bool = True
    auto_browser: bool = True
    status: str = "PENDING"  # PENDING, RUNNING, COMPLETED, STOPPED, FAILED
    created_at: str = field(default_factory=lambda: datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"))

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class CompanyAlias:
    id: Optional[int] = None
    company_id: int = 0
    alias: str = ""
    created_at: str = field(default_factory=lambda: datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"))

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class Company:
    id: Optional[int] = None
    company_key: str = ""
    search_id: Optional[int] = None
    name: str = ""
    normalized_name: str = ""
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    official_domain: Optional[str] = None
    website: Optional[str] = None
    company_type: Optional[str] = None
    company_type_source: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    country: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    maps_url: Optional[str] = None
    rating: Optional[float] = None
    review_count: Optional[int] = None
    category: Optional[str] = None
    website_url: Optional[str] = None
    website_domain: Optional[str] = None
    website_status: str = "UNKNOWN"  # LIVE, OFFLINE, TIMEOUT, BLOCKED, UNKNOWN
    website_checked_at: Optional[str] = None
    career_url: Optional[str] = None
    career_url_source: Optional[str] = None
    career_status: str = "PENDING"  # PENDING, FOUND, NOT_FOUND, BLOCKED
    linkedin_url: Optional[str] = None
    facebook_url: Optional[str] = None
    instagram_url: Optional[str] = None
    twitter_url: Optional[str] = None
    youtube_url: Optional[str] = None
    github_url: Optional[str] = None
    other_social_urls: Optional[str] = None
    enrichment_status: str = "PENDING"  # PENDING, ENRICHING, COMPLETED, FAILED, STOPPED, OFFLINE
    created_at: str = field(default_factory=lambda: datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"))
    updated_at: str = field(default_factory=lambda: datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"))

    # Joined / in-memory collections
    aliases: List[str] = field(default_factory=list)
    job_count: int = 0
    email_count: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class JobSource:
    id: Optional[int] = None
    job_id: int = 0
    source: str = "career_portal"  # career_portal, indeed, unstop, linkedin, glassdoor
    source_job_id: Optional[str] = None
    source_url: str = ""
    is_primary: bool = False
    first_seen: str = field(default_factory=lambda: datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"))
    last_seen: str = field(default_factory=lambda: datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"))
    is_active: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class JobSkill:
    id: Optional[int] = None
    job_id: int = 0
    skill: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class Job:
    id: Optional[int] = None
    company_id: int = 0
    title: str = ""
    normalized_title: Optional[str] = None
    job_url: Optional[str] = None
    location: Optional[str] = None
    employment_type: Optional[str] = None  # Full Time, Part Time, Contract, Internship
    department: Optional[str] = None
    experience: Optional[str] = None
    remote_type: Optional[str] = None  # Remote, Hybrid, On-site
    posted_date: Optional[str] = None
    description: Optional[str] = None
    requirements: Optional[str] = None
    salary: Optional[str] = None
    work_mode: Optional[str] = None  # Remote, Hybrid, On-site
    source: Optional[str] = None  # Primary source or initial source
    relevance_score: int = 0  # 0 - 100
    is_active: bool = True
    created_at: str = field(default_factory=lambda: datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"))
    updated_at: str = field(default_factory=lambda: datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"))

    # Auxiliary display fields & relational collections
    company_name: Optional[str] = None
    sources: List[JobSource] = field(default_factory=list)
    skills: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["sources"] = [s.to_dict() if isinstance(s, JobSource) else s for s in self.sources]
        return d


@dataclass
class NormalizedJob:
    """
    Standard intermediate representation output by every source adapter before deduplication.
    """
    company_name: str
    job_title: str
    source: str  # career_portal, indeed, unstop, linkedin, glassdoor
    source_url: str
    source_job_id: Optional[str] = None
    company_domain: Optional[str] = None
    company_website: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    location: Optional[str] = None
    remote_type: Optional[str] = None  # Remote, Hybrid, On-site
    employment_type: Optional[str] = None  # Full Time, Part Time, Contract, Internship
    experience: Optional[str] = None
    salary: Optional[str] = None
    description: Optional[str] = None
    requirements: Optional[str] = None
    skills: List[str] = field(default_factory=list)
    posted_date: Optional[str] = None
    department: Optional[str] = None
    raw_data: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class Contact:
    id: Optional[int] = None
    company_id: int = 0
    email: str = ""
    email_type: str = "General"  # Careers, HR, Jobs, General, Sales, Support
    source_url: Optional[str] = None
    created_at: str = field(default_factory=lambda: datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"))

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
