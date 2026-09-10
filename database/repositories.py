"""
Repository layer providing CRUD operations, custom query filtering, and relational lookups.
Supports multi-source job associations, company deduplication lookups, and aliases.
"""

from typing import List, Optional, Dict, Any, Tuple
from datetime import datetime
from database.database import Database
from database.models import SearchSession, Company, Job, Contact, JobSource, JobSkill, CompanyAlias, Resume, JobApplication
from utils.logger import get_logger

logger = get_logger("repository")


class SearchesRepository:
    def __init__(self, db: Optional[Database] = None):
        self.db = db or Database()

    def create(self, session: SearchSession) -> int:
        conn = self.db.get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO searches (
                city, state, country, profession, custom_profession,
                company_type, custom_company_type, result_limit,
                enrich_enabled, auto_browser, status, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            session.city, session.state, session.country,
            session.profession, session.custom_profession,
            session.company_type, session.custom_company_type,
            session.result_limit, session.enrich_enabled,
            session.auto_browser, session.status, session.created_at
        ))
        conn.commit()
        session.id = cursor.lastrowid
        return session.id

    def update_status(self, search_id: int, status: str):
        conn = self.db.get_connection()
        conn.execute("UPDATE searches SET status = ? WHERE id = ?", (status, search_id))
        conn.commit()

    def get_all(self, limit: int = 50) -> List[Dict[str, Any]]:
        conn = self.db.get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT s.*, 
                   COUNT(DISTINCT c.id) AS company_count,
                   COUNT(DISTINCT j.id) AS job_count,
                   COUNT(DISTINCT ct.id) AS email_count
            FROM searches s
            LEFT JOIN companies c ON c.search_id = s.id
            LEFT JOIN jobs j ON j.company_id = c.id
            LEFT JOIN contacts ct ON ct.company_id = c.id
            GROUP BY s.id
            ORDER BY s.id DESC
            LIMIT ?
        """, (limit,))
        return [dict(row) for row in cursor.fetchall()]

    def get_by_id(self, search_id: int) -> Optional[SearchSession]:
        conn = self.db.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM searches WHERE id = ?", (search_id,))
        row = cursor.fetchone()
        if not row:
            return None
        return SearchSession(**dict(row))


class CompanyAliasesRepository:
    def __init__(self, db: Optional[Database] = None):
        self.db = db or Database()

    def add_alias(self, company_id: int, alias: str) -> int:
        if not alias or not alias.strip():
            return 0
        clean_alias = alias.strip().lower()
        conn = self.db.get_connection()
        cursor = conn.cursor()
        now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute("""
            INSERT OR IGNORE INTO company_aliases (company_id, alias, created_at)
            VALUES (?, ?, ?)
        """, (company_id, clean_alias, now))
        conn.commit()
        return cursor.lastrowid or 0

    def find_company_by_alias(self, alias: str) -> Optional[int]:
        if not alias:
            return None
        clean_alias = alias.strip().lower()
        conn = self.db.get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT company_id FROM company_aliases
            WHERE alias = ?
            LIMIT 1
        """, (clean_alias,))
        row = cursor.fetchone()
        return row["company_id"] if row else None

    def get_aliases_for_company(self, company_id: int) -> List[str]:
        conn = self.db.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT alias FROM company_aliases WHERE company_id = ?", (company_id,))
        return [row["alias"] for row in cursor.fetchall()]


class CompaniesRepository:
    def __init__(self, db: Optional[Database] = None):
        self.db = db or Database()
        self.aliases_repo = CompanyAliasesRepository(self.db)

    def find_by_key(self, company_key: str) -> Optional[Company]:
        if not company_key:
            return None
        conn = self.db.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM companies WHERE company_key = ? LIMIT 1", (company_key,))
        row = cursor.fetchone()
        if not row:
            return None
        return self._row_to_company(dict(row))

    def find_by_domain(self, domain: str) -> Optional[Company]:
        if not domain:
            return None
        clean_domain = domain.lower().replace("www.", "").strip()
        conn = self.db.get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM companies 
            WHERE website_domain = ? OR official_domain = ? OR website_url LIKE ?
            LIMIT 1
        """, (clean_domain, clean_domain, f"%{clean_domain}%"))
        row = cursor.fetchone()
        if not row:
            return None
        return self._row_to_company(dict(row))

    def find_by_normalized_name(self, normalized_name: str) -> Optional[Company]:
        if not normalized_name:
            return None
        clean_name = normalized_name.strip().lower()
        conn = self.db.get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM companies 
            WHERE LOWER(normalized_name) = ?
            LIMIT 1
        """, (clean_name,))
        row = cursor.fetchone()
        if not row:
            # Try alias lookup
            comp_id = self.aliases_repo.find_company_by_alias(clean_name)
            if comp_id:
                return self.get_by_id(comp_id)
            return None
        return self._row_to_company(dict(row))

    def find_nearby_candidates(self, normalized_name: str, latitude: float, longitude: float, max_km: float = 15.0) -> List[Company]:
        """Finds candidate companies with matching normalized name or alias within max_km distance."""
        from core.normalizer import JobNormalizer
        conn = self.db.get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM companies 
            WHERE (LOWER(normalized_name) = ? OR id IN (SELECT company_id FROM company_aliases WHERE LOWER(alias) = ?))
              AND latitude IS NOT NULL AND longitude IS NOT NULL
        """, (normalized_name.lower(), normalized_name.lower()))
        rows = cursor.fetchall()
        matched = []
        for r in rows:
            c = self._row_to_company(dict(r))
            if c.latitude is not None and c.longitude is not None:
                dist = JobNormalizer.calculate_distance_km(latitude, longitude, c.latitude, c.longitude)
                if dist <= max_km:
                    matched.append(c)
        return matched

    def upsert(self, company: Company) -> int:
        """Inserts a new company or safely updates existing non-null fields if matching company exists."""
        conn = self.db.get_connection()
        cursor = conn.cursor()
        now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")

        # 1. Match by company_key
        existing = None
        if company.company_key:
            cursor.execute("SELECT id FROM companies WHERE company_key = ? LIMIT 1", (company.company_key,))
            existing = cursor.fetchone()

        # 2. Match by exact domain + normalized name (Strongest Identity)
        if not existing and company.website_domain and company.normalized_name:
            cursor.execute("""
                SELECT id FROM companies 
                WHERE normalized_name = ? AND (website_domain = ? OR official_domain = ?)
                LIMIT 1
            """, (company.normalized_name, company.website_domain, company.website_domain))
            existing = cursor.fetchone()

        # 3. Match by maps_url
        if not existing and company.maps_url:
            cursor.execute("SELECT id FROM companies WHERE maps_url = ? LIMIT 1", (company.maps_url,))
            existing = cursor.fetchone()

        # 4. Match by domain alone if domain is verified
        if not existing and company.website_domain:
            cursor.execute("""
                SELECT id FROM companies 
                WHERE website_domain = ? OR official_domain = ?
                LIMIT 1
            """, (company.website_domain, company.website_domain))
            existing = cursor.fetchone()

        official_dom = company.official_domain or company.website_domain
        web = company.website or company.website_url

        if not company.company_key:
            from core.normalizer import JobNormalizer
            company.company_key = JobNormalizer.generate_company_key(
                company.name or company.normalized_name,
                company.latitude,
                company.longitude,
                official_dom
            )

        if existing:
            company.id = existing["id"]
            cursor.execute("""
                UPDATE companies SET
                    search_id = COALESCE(?, search_id),
                    name = CASE WHEN ? IS NOT NULL AND ? != '' THEN ? ELSE name END,
                    company_key = COALESCE(?, company_key),
                    latitude = COALESCE(?, latitude),
                    longitude = COALESCE(?, longitude),
                    official_domain = COALESCE(?, official_domain),
                    website = COALESCE(?, website),
                    company_type = COALESCE(?, company_type),
                    company_type_source = COALESCE(?, company_type_source),
                    address = COALESCE(?, address),
                    city = COALESCE(?, city),
                    state = COALESCE(?, state),
                    country = COALESCE(?, country),
                    phone = COALESCE(?, phone),
                    email = COALESCE(?, email),
                    maps_url = COALESCE(?, maps_url),
                    rating = COALESCE(?, rating),
                    review_count = COALESCE(?, review_count),
                    category = COALESCE(?, category),
                    website_url = COALESCE(?, website_url),
                    website_domain = COALESCE(?, website_domain),
                    website_status = CASE WHEN ? != 'UNKNOWN' THEN ? ELSE website_status END,
                    website_checked_at = COALESCE(?, website_checked_at),
                    career_url = COALESCE(?, career_url),
                    career_url_source = COALESCE(?, career_url_source),
                    career_status = CASE WHEN ? != 'PENDING' THEN ? ELSE career_status END,
                    linkedin_url = COALESCE(?, linkedin_url),
                    facebook_url = COALESCE(?, facebook_url),
                    instagram_url = COALESCE(?, instagram_url),
                    twitter_url = COALESCE(?, twitter_url),
                    youtube_url = COALESCE(?, youtube_url),
                    github_url = COALESCE(?, github_url),
                    other_social_urls = COALESCE(?, other_social_urls),
                    enrichment_status = CASE WHEN ? != 'PENDING' THEN ? ELSE enrichment_status END,
                    updated_at = ?
                WHERE id = ?
            """, (
                company.search_id, company.name, company.name, company.name,
                company.company_key, company.latitude, company.longitude,
                official_dom, web, company.company_type, company.company_type_source,
                company.address, company.city, company.state, company.country, company.phone,
                company.email, company.maps_url, company.rating, company.review_count, company.category,
                company.website_url, company.website_domain, company.website_status, company.website_status,
                company.website_checked_at, company.career_url, company.career_url_source,
                company.career_status, company.career_status, company.linkedin_url,
                company.facebook_url, company.instagram_url, company.twitter_url,
                company.youtube_url, company.github_url, company.other_social_urls,
                company.enrichment_status, company.enrichment_status, now, company.id
            ))
        else:
            cursor.execute("""
                INSERT INTO companies (
                    company_key, search_id, name, normalized_name, latitude, longitude,
                    official_domain, website, company_type, company_type_source,
                    address, city, state, country, phone, email, maps_url, rating, review_count,
                    category, website_url, website_domain, website_status, website_checked_at,
                    career_url, career_url_source, career_status, linkedin_url, facebook_url,
                    instagram_url, twitter_url, youtube_url, github_url, other_social_urls,
                    enrichment_status, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                company.company_key, company.search_id, company.name, company.normalized_name,
                company.latitude, company.longitude, official_dom, web, company.company_type,
                company.company_type_source, company.address, company.city, company.state,
                company.country, company.phone, company.email, company.maps_url, company.rating,
                company.review_count, company.category, company.website_url,
                company.website_domain, company.website_status, company.website_checked_at,
                company.career_url, company.career_url_source, company.career_status,
                company.linkedin_url, company.facebook_url, company.instagram_url,
                company.twitter_url, company.youtube_url, company.github_url,
                company.other_social_urls, company.enrichment_status, now, now
            ))
            company.id = cursor.lastrowid

        # Register aliases if provided
        if company.id:
            if company.name:
                self.aliases_repo.add_alias(company.id, company.name)
            if company.normalized_name:
                self.aliases_repo.add_alias(company.id, company.normalized_name)
            for alias in company.aliases:
                self.aliases_repo.add_alias(company.id, alias)

        conn.commit()
        return company.id

    def _row_to_company(self, data: Dict[str, Any]) -> Company:
        job_count = data.pop("job_count", 0)
        email_count = data.pop("email_count", 0)
        comp_id = data.get("id")
        comp = Company(**data)
        comp.job_count = job_count
        comp.email_count = email_count
        if comp_id:
            comp.aliases = self.aliases_repo.get_aliases_for_company(comp_id)
        return comp

    def get_by_id(self, company_id: int) -> Optional[Company]:
        conn = self.db.get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT c.*,
                   (SELECT COUNT(*) FROM jobs WHERE company_id = c.id) AS job_count,
                   (SELECT COUNT(*) FROM contacts WHERE company_id = c.id) AS email_count
            FROM companies c
            WHERE c.id = ?
        """, (company_id,))
        row = cursor.fetchone()
        if not row:
            return None
        return self._row_to_company(dict(row))

    def get_companies(
        self,
        search_id: Optional[int] = None,
        filter_text: Optional[str] = None,
        company_type: Optional[str] = None,
        website_status: Optional[str] = None,
        enrichment_status: Optional[str] = None,
        has_jobs_only: bool = False,
        has_emails_only: bool = False,
        limit: int = 500
    ) -> List[Company]:
        conn = self.db.get_connection()
        cursor = conn.cursor()

        query = """
            SELECT c.*,
                   (SELECT COUNT(*) FROM jobs WHERE company_id = c.id) AS job_count,
                   (SELECT COUNT(*) FROM contacts WHERE company_id = c.id) AS email_count
            FROM companies c
            WHERE 1=1
        """
        params: List[Any] = []

        if search_id:
            query += " AND c.search_id = ?"
            params.append(search_id)

        if filter_text:
            query += " AND (c.name LIKE ? OR c.address LIKE ? OR c.city LIKE ? OR c.website_domain LIKE ?)"
            pattern = f"%{filter_text}%"
            params.extend([pattern, pattern, pattern, pattern])

        if company_type and company_type != "All":
            query += " AND c.company_type LIKE ?"
            params.append(f"%{company_type}%")

        if website_status and website_status != "All":
            query += " AND c.website_status = ?"
            params.append(website_status)

        if enrichment_status and enrichment_status != "All":
            query += " AND c.enrichment_status = ?"
            params.append(enrichment_status)

        if has_jobs_only:
            query += " AND (SELECT COUNT(*) FROM jobs WHERE company_id = c.id) > 0"

        if has_emails_only:
            query += " AND (SELECT COUNT(*) FROM contacts WHERE company_id = c.id) > 0"

        query += " ORDER BY c.id DESC LIMIT ?"
        params.append(limit)

        cursor.execute(query, tuple(params))
        results = []
        for row in cursor.fetchall():
            results.append(self._row_to_company(dict(row)))
        return results

    def get_pending_enrichment_companies(self, search_id: Optional[int] = None) -> List[Company]:
        """Gets companies that have not completed enrichment yet."""
        conn = self.db.get_connection()
        cursor = conn.cursor()
        query = """
            SELECT c.*,
                   (SELECT COUNT(*) FROM jobs WHERE company_id = c.id) AS job_count,
                   (SELECT COUNT(*) FROM contacts WHERE company_id = c.id) AS email_count
            FROM companies c
            WHERE c.enrichment_status IN ('PENDING', 'FAILED', 'STOPPED')
        """
        params = []
        if search_id:
            query += " AND c.search_id = ?"
            params.append(search_id)
        query += " ORDER BY c.id ASC"
        cursor.execute(query, tuple(params))
        results = []
        for row in cursor.fetchall():
            results.append(self._row_to_company(dict(row)))
        return results

    def update_enrichment_status(self, company_id: int, status: str):
        conn = self.db.get_connection()
        now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
        conn.execute("UPDATE companies SET enrichment_status = ?, updated_at = ? WHERE id = ?", (status, now, company_id))
        conn.commit()


class JobSourcesRepository:
    def __init__(self, db: Optional[Database] = None):
        self.db = db or Database()

    def upsert(self, source: JobSource) -> int:
        conn = self.db.get_connection()
        cursor = conn.cursor()
        now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")

        # Check existing source by job_id and (source, source_url) or (source, source_job_id)
        cursor.execute("""
            SELECT id FROM job_sources 
            WHERE job_id = ? AND source = ? AND (source_url = ? OR (source_job_id IS NOT NULL AND source_job_id = ?))
            LIMIT 1
        """, (source.job_id, source.source, source.source_url, source.source_job_id or ""))
        existing = cursor.fetchone()

        if existing:
            source.id = existing["id"]
            cursor.execute("""
                UPDATE job_sources SET
                    source_job_id = COALESCE(?, source_job_id),
                    source_url = COALESCE(?, source_url),
                    is_primary = CASE WHEN ? = 1 THEN 1 ELSE is_primary END,
                    last_seen = ?,
                    is_active = ?
                WHERE id = ?
            """, (source.source_job_id, source.source_url, 1 if source.is_primary else 0, now, 1 if source.is_active else 0, source.id))
        else:
            cursor.execute("""
                INSERT INTO job_sources (
                    job_id, source, source_job_id, source_url, is_primary, first_seen, last_seen, is_active
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                source.job_id, source.source, source.source_job_id, source.source_url,
                1 if source.is_primary else 0, now, now, 1 if source.is_active else 0
            ))
            source.id = cursor.lastrowid

        conn.commit()
        return source.id

    def get_by_job(self, job_id: int) -> List[JobSource]:
        conn = self.db.get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM job_sources 
            WHERE job_id = ? 
            ORDER BY is_primary DESC, id ASC
        """, (job_id,))
        sources = []
        for row in cursor.fetchall():
            d = dict(row)
            d["is_primary"] = bool(d.get("is_primary"))
            d["is_active"] = bool(d.get("is_active"))
            sources.append(JobSource(**d))
        return sources

    def set_primary_source(self, job_id: int, source_id: int):
        conn = self.db.get_connection()
        conn.execute("UPDATE job_sources SET is_primary = 0 WHERE job_id = ?", (job_id,))
        conn.execute("UPDATE job_sources SET is_primary = 1 WHERE id = ?", (source_id,))
        conn.commit()


class JobsRepository:
    def __init__(self, db: Optional[Database] = None):
        self.db = db or Database()
        self.sources_repo = JobSourcesRepository(self.db)

    def upsert(self, job: Job) -> int:
        conn = self.db.get_connection()
        cursor = conn.cursor()
        now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")

        clean_title = (job.title or "").strip().lower()
        norm_title = (job.normalized_title or clean_title).strip().lower()

        # Find existing job under same company by exact title or normalized_title
        existing = None
        if job.id:
            cursor.execute("SELECT id FROM jobs WHERE id = ? LIMIT 1", (job.id,))
            existing = cursor.fetchone()

        if not existing:
            cursor.execute("""
                SELECT id FROM jobs 
                WHERE company_id = ? AND (LOWER(TRIM(title)) = ? OR LOWER(TRIM(normalized_title)) = ?)
                LIMIT 1
            """, (job.company_id, clean_title, norm_title))
            existing = cursor.fetchone()

        if existing:
            job.id = existing["id"]
            cursor.execute("""
                UPDATE jobs SET
                    title = COALESCE(?, title),
                    normalized_title = COALESCE(?, normalized_title),
                    location = COALESCE(?, location),
                    employment_type = COALESCE(?, employment_type),
                    department = COALESCE(?, department),
                    experience = COALESCE(?, experience),
                    remote_type = COALESCE(?, remote_type),
                    posted_date = COALESCE(?, posted_date),
                    description = COALESCE(?, description),
                    requirements = COALESCE(?, requirements),
                    salary = COALESCE(?, salary),
                    work_mode = COALESCE(?, work_mode),
                    source = COALESCE(?, source),
                    relevance_score = CASE WHEN ? > 0 THEN ? ELSE relevance_score END,
                    is_active = ?,
                    updated_at = ?
                WHERE id = ?
            """, (
                job.title, job.normalized_title or norm_title, job.location, job.employment_type,
                job.department, job.experience, job.remote_type, job.posted_date,
                job.description, job.requirements, job.salary, job.work_mode,
                job.source, job.relevance_score, job.relevance_score,
                1 if job.is_active else 0, now, job.id
            ))
        else:
            cursor.execute("""
                INSERT INTO jobs (
                    company_id, title, normalized_title, job_url, location, employment_type, department,
                    experience, remote_type, posted_date, description, requirements, salary, work_mode,
                    source, relevance_score, is_active, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                job.company_id, job.title, job.normalized_title or norm_title, job.job_url,
                job.location, job.employment_type, job.department, job.experience, job.remote_type,
                job.posted_date, job.description, job.requirements, job.salary, job.work_mode,
                job.source, job.relevance_score, 1 if job.is_active else 0, now, now
            ))
            job.id = cursor.lastrowid

        # Attach and sync job sources
        if job.id and job.sources:
            for s in job.sources:
                s.job_id = job.id
                self.sources_repo.upsert(s)

        # Attach and sync skills
        if job.id and job.skills:
            for sk in job.skills:
                self.add_skill(job.id, sk)

        conn.commit()
        return job.id

    def add_skill(self, job_id: int, skill: str):
        if not skill or not skill.strip():
            return
        conn = self.db.get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT OR IGNORE INTO job_skills (job_id, skill)
            VALUES (?, ?)
        """, (job_id, skill.strip().lower()))
        conn.commit()

    def get_skills(self, job_id: int) -> List[str]:
        conn = self.db.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT skill FROM job_skills WHERE job_id = ? ORDER BY skill ASC", (job_id,))
        return [row["skill"] for row in cursor.fetchall()]

    def _row_to_job(self, data: Dict[str, Any]) -> Job:
        job_id = data.get("id")
        comp_name = data.pop("company_name", None)
        d = dict(data)
        d["is_active"] = bool(d.get("is_active", 1))
        job = Job(**d)
        job.company_name = comp_name
        if job_id:
            job.sources = self.sources_repo.get_by_job(job_id)
            job.skills = self.get_skills(job_id)
        return job

    def get_by_company(self, company_id: int) -> List[Job]:
        conn = self.db.get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT j.*, c.name AS company_name 
            FROM jobs j
            JOIN companies c ON c.id = j.company_id
            WHERE j.company_id = ?
            ORDER BY j.relevance_score DESC, j.id DESC
        """, (company_id,))
        return [self._row_to_job(dict(row)) for row in cursor.fetchall()]

    def get_all_jobs(self, min_relevance: int = 0, source_filter: Optional[str] = None, limit: int = 1000) -> List[Job]:
        conn = self.db.get_connection()
        cursor = conn.cursor()
        
        query = """
            SELECT DISTINCT j.*, c.name AS company_name 
            FROM jobs j
            JOIN companies c ON c.id = j.company_id
            LEFT JOIN job_sources js ON js.job_id = j.id
            WHERE j.relevance_score >= ?
        """
        params: List[Any] = [min_relevance]

        if source_filter and source_filter != "All":
            query += " AND (j.source = ? OR js.source = ?)"
            params.extend([source_filter.lower(), source_filter.lower()])

        query += " ORDER BY j.relevance_score DESC, j.id DESC LIMIT ?"
        params.append(limit)

        cursor.execute(query, tuple(params))
        return [self._row_to_job(dict(row)) for row in cursor.fetchall()]


class ContactsRepository:
    def __init__(self, db: Optional[Database] = None):
        self.db = db or Database()

    def upsert(self, contact: Contact) -> int:
        conn = self.db.get_connection()
        cursor = conn.cursor()
        now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")

        clean_email = (contact.email or "").strip().lower()
        cursor.execute("""
            SELECT id FROM contacts 
            WHERE company_id = ? AND LOWER(TRIM(email)) = ? 
            LIMIT 1
        """, (contact.company_id, clean_email))
        existing = cursor.fetchone()

        if existing:
            contact.id = existing["id"]
            cursor.execute("""
                UPDATE contacts SET
                    email_type = ?,
                    source_url = COALESCE(?, source_url)
                WHERE id = ?
            """, (contact.email_type, contact.source_url, contact.id))
        else:
            cursor.execute("""
                INSERT INTO contacts (company_id, email, email_type, source_url, created_at)
                VALUES (?, ?, ?, ?, ?)
            """, (contact.company_id, contact.email, contact.email_type, contact.source_url, now))
            contact.id = cursor.lastrowid

        conn.commit()
        return contact.id

    def get_by_company(self, company_id: int) -> List[Contact]:
        conn = self.db.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM contacts WHERE company_id = ? ORDER BY id ASC", (company_id,))
        return [Contact(**dict(row)) for row in cursor.fetchall()]

    def get_all_contacts(self, limit: int = 1000) -> List[Dict[str, Any]]:
        conn = self.db.get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT ct.*, c.name AS company_name, c.website_url, c.city, c.state
            FROM contacts ct
            JOIN companies c ON c.id = ct.company_id
            ORDER BY ct.id DESC
            LIMIT ?
        """, (limit,))
        return [dict(row) for row in cursor.fetchall()]


class ResumesRepository:
    def __init__(self, db: Optional[Database] = None):
        self.db = db or Database()

    def add_resume(self, resume: Resume) -> int:
        conn = self.db.get_connection()
        cursor = conn.cursor()
        now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
        resume.created_at = resume.created_at or now

        # If this is set as default, reset others
        if resume.is_default:
            cursor.execute("UPDATE resumes SET is_default = 0")

        cursor.execute("""
            INSERT INTO resumes (name, file_path, extracted_text, is_default, created_at)
            VALUES (?, ?, ?, ?, ?)
        """, (resume.name, resume.file_path, resume.extracted_text, 1 if resume.is_default else 0, resume.created_at))
        conn.commit()
        resume.id = cursor.lastrowid
        return resume.id

    def get_resume(self, resume_id: int) -> Optional[Resume]:
        conn = self.db.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM resumes WHERE id = ?", (resume_id,))
        row = cursor.fetchone()
        if not row:
            return None
        d = dict(row)
        d["is_default"] = bool(d.get("is_default", 0))
        return Resume(**d)

    def get_default_resume(self) -> Optional[Resume]:
        conn = self.db.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM resumes WHERE is_default = 1 ORDER BY id DESC LIMIT 1")
        row = cursor.fetchone()
        if not row:
            # Fallback to the latest uploaded resume
            cursor.execute("SELECT * FROM resumes ORDER BY id DESC LIMIT 1")
            row = cursor.fetchone()
        if not row:
            return None
        d = dict(row)
        d["is_default"] = bool(d.get("is_default", 0))
        return Resume(**d)

    def get_all_resumes(self) -> List[Resume]:
        conn = self.db.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM resumes ORDER BY is_default DESC, id DESC")
        resumes = []
        for row in cursor.fetchall():
            d = dict(row)
            d["is_default"] = bool(d.get("is_default", 0))
            resumes.append(Resume(**d))
        return resumes

    def set_default_resume(self, resume_id: int):
        conn = self.db.get_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE resumes SET is_default = 0")
        cursor.execute("UPDATE resumes SET is_default = 1 WHERE id = ?", (resume_id,))
        conn.commit()

    def update_resume_text(self, resume_id: int, extracted_text: str):
        conn = self.db.get_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE resumes SET extracted_text = ? WHERE id = ?", (extracted_text, resume_id))
        conn.commit()

    def delete_resume(self, resume_id: int) -> bool:
        conn = self.db.get_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM resumes WHERE id = ?", (resume_id,))
        conn.commit()
        return cursor.rowcount > 0


class ApplicationsRepository:
    def __init__(self, db: Optional[Database] = None):
        self.db = db or Database()

    def save_application(self, app: JobApplication) -> int:
        conn = self.db.get_connection()
        cursor = conn.cursor()
        now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
        app.created_at = app.created_at or now
        app.updated_at = now

        # Check if already exists for this job
        cursor.execute("SELECT id FROM applications WHERE job_id = ? LIMIT 1", (app.job_id,))
        existing = cursor.fetchone()

        if existing:
            app.id = existing["id"]
            cursor.execute("""
                UPDATE applications SET
                    company_id = ?,
                    resume_id = ?,
                    hr_email = ?,
                    subject = ?,
                    email_body = ?,
                    match_score = ?,
                    status = ?,
                    activity_log = ?,
                    applied_at = COALESCE(?, applied_at),
                    updated_at = ?
                WHERE id = ?
            """, (
                app.company_id, app.resume_id, app.hr_email,
                app.subject, app.email_body, app.match_score,
                app.status, app.activity_log, app.applied_at,
                app.updated_at, app.id
            ))
        else:
            cursor.execute("""
                INSERT INTO applications (
                    job_id, company_id, resume_id, hr_email, subject,
                    email_body, match_score, status, activity_log,
                    applied_at, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                app.job_id, app.company_id, app.resume_id, app.hr_email,
                app.subject, app.email_body, app.match_score,
                app.status, app.activity_log, app.applied_at,
                app.created_at, app.updated_at
            ))
            app.id = cursor.lastrowid

        conn.commit()
        return app.id

    def get_application(self, app_id: int) -> Optional[JobApplication]:
        conn = self.db.get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT a.*, j.title AS job_title, c.name AS company_name, r.name AS resume_name
            FROM applications a
            JOIN jobs j ON j.id = a.job_id
            JOIN companies c ON c.id = a.company_id
            LEFT JOIN resumes r ON r.id = a.resume_id
            WHERE a.id = ?
        """, (app_id,))
        row = cursor.fetchone()
        if not row:
            return None
        return JobApplication(**dict(row))

    def get_by_job_id(self, job_id: int) -> Optional[JobApplication]:
        conn = self.db.get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT a.*, j.title AS job_title, c.name AS company_name, r.name AS resume_name
            FROM applications a
            JOIN jobs j ON j.id = a.job_id
            JOIN companies c ON c.id = a.company_id
            LEFT JOIN resumes r ON r.id = a.resume_id
            WHERE a.job_id = ?
            LIMIT 1
        """, (job_id,))
        row = cursor.fetchone()
        if not row:
            return None
        return JobApplication(**dict(row))

    def get_all_applications(self, status_filter: Optional[str] = None, limit: int = 500) -> List[JobApplication]:
        conn = self.db.get_connection()
        cursor = conn.cursor()
        query = """
            SELECT a.*, j.title AS job_title, c.name AS company_name, r.name AS resume_name
            FROM applications a
            JOIN jobs j ON j.id = a.job_id
            JOIN companies c ON c.id = a.company_id
            LEFT JOIN resumes r ON r.id = a.resume_id
        """
        params: List[Any] = []
        if status_filter and status_filter != "All":
            query += " WHERE a.status = ?"
            params.append(status_filter)

        query += " ORDER BY a.updated_at DESC, a.id DESC LIMIT ?"
        params.append(limit)

        cursor.execute(query, tuple(params))
        return [JobApplication(**dict(row)) for row in cursor.fetchall()]

    def update_status(self, app_id: int, status: str, log_message: Optional[str] = None):
        conn = self.db.get_connection()
        cursor = conn.cursor()
        now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
        applied_at = now if status in ("SENT", "BROWSER_OPENED") else None

        if log_message:
            cursor.execute("SELECT activity_log FROM applications WHERE id = ?", (app_id,))
            row = cursor.fetchone()
            current_log = row["activity_log"] if row and row["activity_log"] else ""
            timestamp = datetime.now().strftime("%H:%M")
            new_log = f"{current_log}\n{timestamp}  {log_message}".strip()
            cursor.execute("""
                UPDATE applications SET
                    status = ?,
                    activity_log = ?,
                    applied_at = COALESCE(?, applied_at),
                    updated_at = ?
                WHERE id = ?
            """, (status, new_log, applied_at, now, app_id))
        else:
            cursor.execute("""
                UPDATE applications SET
                    status = ?,
                    applied_at = COALESCE(?, applied_at),
                    updated_at = ?
                WHERE id = ?
            """, (status, applied_at, now, app_id))

        conn.commit()

    def append_log(self, app_id: int, log_message: str):
        conn = self.db.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT activity_log FROM applications WHERE id = ?", (app_id,))
        row = cursor.fetchone()
        current_log = row["activity_log"] if row and row["activity_log"] else ""
        timestamp = datetime.now().strftime("%H:%M")
        new_log = f"{current_log}\n{timestamp}  {log_message}".strip()
        now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute("UPDATE applications SET activity_log = ?, updated_at = ? WHERE id = ?", (new_log, now, app_id))
        conn.commit()

    def delete_application(self, app_id: int) -> bool:
        conn = self.db.get_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM applications WHERE id = ?", (app_id,))
        conn.commit()
        return cursor.rowcount > 0
