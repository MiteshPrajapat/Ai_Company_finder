"""
Deduplication Service providing multi-signal matching for companies and job positions across multiple platforms.
Preserves distinct positions within the same company while merging identical listings across different job sources.
"""

from typing import List, Optional, Tuple, Dict, Any
from difflib import SequenceMatcher
from database.models import Company, Job, JobSource, NormalizedJob
from database.repositories import CompaniesRepository, JobsRepository, JobSourcesRepository
from core.normalizer import JobNormalizer
from utils.logger import get_logger
from utils.url_utils import extract_domain, clean_url

logger = get_logger("deduplication_service")

# Priority ranking of sources (lower index = higher priority)
SOURCE_PRIORITY_ORDER = [
    "career_portal",
    "indeed",
    "unstop",
    "linkedin",
    "glassdoor"
]


def get_source_rank(source_name: Optional[str]) -> int:
    s = (source_name or "").lower().strip()
    if s in SOURCE_PRIORITY_ORDER:
        return SOURCE_PRIORITY_ORDER.index(s)
    return 99


class DeduplicationService:
    """
    Intelligent company and job deduplication engine with multi-signal similarity scoring.
    """

    def __init__(
        self,
        companies_repo: Optional[CompaniesRepository] = None,
        jobs_repo: Optional[JobsRepository] = None,
        sources_repo: Optional[JobSourcesRepository] = None,
        merge_threshold: float = 75.0
    ):
        self.companies_repo = companies_repo or CompaniesRepository()
        self.jobs_repo = jobs_repo or JobsRepository()
        self.sources_repo = sources_repo or JobSourcesRepository()
        self.merge_threshold = merge_threshold
        self.normalizer = JobNormalizer()

    def process_normalized_job(
        self,
        norm_job: NormalizedJob,
        search_id: Optional[int] = None
    ) -> Tuple[Job, bool]:
        """
        Ingests a NormalizedJob, resolves or creates the company, and determines
        whether to merge into an existing position or create a new job position.
        Returns: (Job, is_new_job)
        """
        # 1. Company Resolution & Deduplication
        company = self.resolve_or_create_company(norm_job, search_id=search_id)

        # 2. Position Deduplication under this Company
        job, is_new = self.resolve_or_create_position(company, norm_job)
        return job, is_new

    def resolve_or_create_company(
        self,
        norm_job: NormalizedJob,
        search_id: Optional[int] = None
    ) -> Company:
        """
        Finds existing company using domain, aliases, and normalized name,
        or creates a new company entry with registered aliases.
        """
        raw_name = norm_job.company_name.strip()
        norm_name = self.normalizer.normalize_company_name(raw_name)
        domain = norm_job.company_domain or (extract_domain(norm_job.company_website) if norm_job.company_website else None)
        lat = norm_job.latitude
        lng = norm_job.longitude

        # Generate candidate company_key
        company_key = self.normalizer.generate_company_key(raw_name, lat, lng, domain)

        # -------------------------------------------------------------
        # Tier 1: Exact Verified Domain + Name (Strongest Identity)
        # -------------------------------------------------------------
        if domain:
            comp = self.companies_repo.find_by_domain(domain)
            if comp:
                # Merge newly available non-null data safely
                updated = False
                if lat is not None and comp.latitude is None:
                    comp.latitude = lat
                    updated = True
                if lng is not None and comp.longitude is None:
                    comp.longitude = lng
                    updated = True
                if norm_job.company_website and not comp.website_url:
                    comp.website_url = norm_job.company_website
                    comp.website = norm_job.company_website
                    updated = True
                if updated:
                    self.companies_repo.upsert(comp)
                self.companies_repo.aliases_repo.add_alias(comp.id, raw_name)
                return comp

        # -------------------------------------------------------------
        # Tier 2: Exact company_key Match (Name + Rounded Coordinates)
        # -------------------------------------------------------------
        if company_key:
            comp = self.companies_repo.find_by_key(company_key)
            if comp:
                self.companies_repo.aliases_repo.add_alias(comp.id, raw_name)
                return comp

        # -------------------------------------------------------------
        # Tier 3: Coordinate Proximity Match (Name + within 15 km)
        # -------------------------------------------------------------
        if lat is not None and lng is not None:
            nearby_matches = self.companies_repo.find_nearby_candidates(norm_name, lat, lng, max_km=15.0)
            if nearby_matches:
                # Use closest matching candidate
                comp = nearby_matches[0]
                self.companies_repo.aliases_repo.add_alias(comp.id, raw_name)
                return comp

        # -------------------------------------------------------------
        # Tier 4: Alias Exact Match
        # -------------------------------------------------------------
        alias_comp_id = self.companies_repo.aliases_repo.find_company_by_alias(raw_name)
        if alias_comp_id:
            comp = self.companies_repo.get_by_id(alias_comp_id)
            if comp:
                return comp

        # -------------------------------------------------------------
        # Tier 5: Create New Company Record
        # -------------------------------------------------------------
        new_comp = Company(
            company_key=company_key,
            search_id=search_id,
            name=raw_name,
            normalized_name=norm_name,
            latitude=lat,
            longitude=lng,
            official_domain=domain,
            website=norm_job.company_website,
            website_url=norm_job.company_website,
            website_domain=domain,
            city=norm_job.location,
            enrichment_status="PENDING"
        )
        comp_id = self.companies_repo.upsert(new_comp)
        new_comp.id = comp_id
        return new_comp

    def resolve_or_create_position(
        self,
        company: Company,
        norm_job: NormalizedJob
    ) -> Tuple[Job, bool]:
        """
        Compares incoming listing against all existing positions for this company.
        If similarity >= merge_threshold, merges sources into the existing position.
        Otherwise, creates a separate distinct position.
        """
        norm_title = self.normalizer.normalize_job_title(norm_job.job_title)
        existing_jobs = self.jobs_repo.get_by_company(company.id)

        best_match: Optional[Job] = None
        best_score = 0.0

        for candidate in existing_jobs:
            score = self.calculate_job_similarity(candidate, norm_job, norm_title)
            if score > best_score:
                best_score = score
                best_match = candidate

        # Build JobSource object for this incoming listing
        source_obj = JobSource(
            job_id=0,  # Will be set below
            source=norm_job.source,
            source_job_id=norm_job.source_job_id,
            source_url=norm_job.source_url,
            is_primary=(norm_job.source == "career_portal")
        )

        # Merge with existing position if confidence is high
        if best_match and best_score >= self.merge_threshold:
            logger.info(
                f"Duplicate position merged ({best_score:.1f}% match): "
                f"'{norm_job.job_title}' from {norm_job.source} -> existing '{best_match.title}' (ID #{best_match.id})"
            )
            source_obj.job_id = best_match.id

            # Determine if this incoming source should be the primary URL
            incoming_rank = get_source_rank(norm_job.source)
            existing_rank = get_source_rank(best_match.source)
            
            if incoming_rank < existing_rank or not best_match.job_url:
                best_match.job_url = norm_job.source_url
                best_match.source = norm_job.source
                source_obj.is_primary = True

            # Merge missing metadata
            if not best_match.description and norm_job.description:
                best_match.description = norm_job.description
            if not best_match.requirements and norm_job.requirements:
                best_match.requirements = norm_job.requirements
            if not best_match.salary and norm_job.salary:
                best_match.salary = norm_job.salary
            if not best_match.experience and norm_job.experience:
                best_match.experience = norm_job.experience
            if (not best_match.remote_type or best_match.remote_type == "On-site") and norm_job.remote_type:
                best_match.remote_type = norm_job.remote_type
                best_match.work_mode = norm_job.remote_type

            # Merge skills
            for sk in norm_job.skills:
                if sk not in best_match.skills:
                    best_match.skills.append(sk)

            best_match.sources.append(source_obj)
            self.jobs_repo.upsert(best_match)
            return best_match, False

        # Create a new distinct position under the company
        logger.info(f"Creating distinct position: '{norm_job.job_title}' for {company.name} from {norm_job.source}")
        
        new_job = Job(
            company_id=company.id,
            title=norm_job.job_title,
            normalized_title=norm_title,
            job_url=norm_job.source_url,
            location=norm_job.location,
            employment_type=norm_job.employment_type or "Full-time",
            department=norm_job.department,
            experience=norm_job.experience,
            remote_type=norm_job.remote_type or "On-site",
            posted_date=norm_job.posted_date,
            description=norm_job.description,
            requirements=norm_job.requirements,
            salary=norm_job.salary,
            work_mode=norm_job.remote_type or "On-site",
            source=norm_job.source,
            sources=[source_obj],
            skills=norm_job.skills,
            company_name=company.name
        )
        job_id = self.jobs_repo.upsert(new_job)
        new_job.id = job_id
        return new_job, True

    def calculate_job_similarity(
        self,
        existing: Job,
        incoming: NormalizedJob,
        norm_incoming_title: str
    ) -> float:
        """
        Calculates multi-signal similarity score (0 - 100):
        - Company Match: 40% (Guaranteed 40.0 since compared within same company)
        - Title Match: 25% (Normalized token similarity)
        - Location Match: 15% (City, state, remote similarity)
        - Skills Match: 10% (Jaccard similarity of extracted skills)
        - Description Match: 10% (Text overlap ratio)
        """
        # 1. Company Score: 40%
        company_score = 40.0

        # 2. Title Score: 25%
        cand_norm_title = existing.normalized_title or self.normalizer.normalize_job_title(existing.title)
        
        # Check exact normalized match
        if cand_norm_title == norm_incoming_title:
            title_sim = 1.0
        else:
            # Check for title level differences e.g. Senior vs Junior or II vs III
            cand_tokens = set(cand_norm_title.split())
            inc_tokens = set(norm_incoming_title.split())
            
            # Key differentiators: senior, junior, lead, principal, intern, architect, manager
            differentiators = {"senior", "junior", "lead", "principal", "intern", "architect", "manager", "director", "head", "ii", "iii", "iv", "staff"}
            diff_mismatch = (cand_tokens & differentiators) ^ (inc_tokens & differentiators)
            if diff_mismatch:
                # If seniority differs, penalize title match significantly so they remain separate positions
                title_sim = 0.3
            else:
                title_sim = SequenceMatcher(None, cand_norm_title, norm_incoming_title).ratio()

        title_score = title_sim * 25.0

        # 3. Location Score: 15%
        loc_score = 0.0
        loc1 = (existing.location or "").lower().strip()
        loc2 = (incoming.location or "").lower().strip()
        
        if not loc1 or not loc2 or loc1 == loc2:
            loc_score = 15.0
        elif (incoming.remote_type == "Remote" or existing.remote_type == "Remote"):
            loc_score = 14.0
        elif loc1 in loc2 or loc2 in loc1:
            loc_score = 15.0
        else:
            # Check city overlap
            loc_sim = SequenceMatcher(None, loc1, loc2).ratio()
            loc_score = loc_sim * 15.0

        # 4. Skills Match: 10%
        skills1 = set(s.lower() for s in (existing.skills or []))
        skills2 = set(s.lower() for s in (incoming.skills or []))
        if not skills1 or not skills2:
            skills_score = 7.0  # Neutral baseline if skills not extracted yet
        else:
            intersection = len(skills1 & skills2)
            union = len(skills1 | skills2)
            skills_score = (intersection / union) * 10.0 if union > 0 else 7.0

        # 5. Description Match: 10%
        desc1 = (existing.description or "")[:300].lower()
        desc2 = (incoming.description or "")[:300].lower()
        if not desc1 or not desc2:
            desc_score = 7.0
        else:
            desc_score = SequenceMatcher(None, desc1, desc2).ratio() * 10.0

        total_score = company_score + title_score + loc_score + skills_score + desc_score
        return round(total_score, 2)
