"""
SQLite Database manager with schema migration, WAL mode, and connection pooling.
"""

import sqlite3
import threading
from pathlib import Path
from typing import Optional
from utils.logger import get_logger
from config.settings import settings

logger = get_logger("database")


class Database:
    """Thread-safe SQLite Database manager with connection lifecycle handling."""
    _instance = None
    _lock = threading.Lock()

    def __new__(cls, db_path: Optional[str] = None):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(Database, cls).__new__(cls)
                cls._instance._init_db(db_path)
            return cls._instance

    def _init_db(self, db_path: Optional[str] = None):
        self.db_path = db_path or settings.get_config().database_path
        # Ensure parent directory exists
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self.local = threading.local()
        self.init_schema()

    def get_connection(self) -> sqlite3.Connection:
        """Retrieves or creates a thread-local SQLite connection."""
        if not hasattr(self.local, "conn") or self.local.conn is None:
            conn = sqlite3.connect(self.db_path, check_same_thread=False, timeout=30.0)
            conn.row_factory = sqlite3.Row
            # Enable performance optimizations & integrity
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute("PRAGMA synchronous=NORMAL;")
            conn.execute("PRAGMA foreign_keys=ON;")
            self.local.conn = conn
        return self.local.conn

    def init_schema(self):
        """Initializes database tables, triggers, and indices."""
        conn = self.get_connection()
        cursor = conn.cursor()

        # 1. Searches Table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS searches (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                city TEXT,
                state TEXT,
                country TEXT,
                profession TEXT,
                custom_profession TEXT,
                company_type TEXT,
                custom_company_type TEXT,
                result_limit INTEGER DEFAULT 10,
                enrich_enabled BOOLEAN DEFAULT 1,
                auto_browser BOOLEAN DEFAULT 1,
                status TEXT DEFAULT 'PENDING',
                created_at TEXT
            );
        """)

        # 2. Companies Table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS companies (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                company_key TEXT NOT NULL UNIQUE,
                search_id INTEGER,
                name TEXT NOT NULL,
                normalized_name TEXT NOT NULL,
                latitude REAL,
                longitude REAL,
                official_domain TEXT,
                website TEXT,
                company_type TEXT,
                company_type_source TEXT,
                address TEXT,
                city TEXT,
                state TEXT,
                country TEXT,
                phone TEXT,
                email TEXT,
                maps_url TEXT,
                rating REAL,
                review_count INTEGER,
                category TEXT,
                website_url TEXT,
                website_domain TEXT,
                website_status TEXT DEFAULT 'UNKNOWN',
                website_checked_at TEXT,
                career_url TEXT,
                career_url_source TEXT,
                career_status TEXT DEFAULT 'PENDING',
                linkedin_url TEXT,
                facebook_url TEXT,
                instagram_url TEXT,
                twitter_url TEXT,
                youtube_url TEXT,
                github_url TEXT,
                other_social_urls TEXT,
                enrichment_status TEXT DEFAULT 'PENDING',
                created_at TEXT,
                updated_at TEXT,
                FOREIGN KEY (search_id) REFERENCES searches(id) ON DELETE SET NULL
            );
        """)

        # 3. Jobs Table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS jobs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                company_id INTEGER NOT NULL,
                title TEXT NOT NULL,
                normalized_title TEXT,
                job_url TEXT,
                location TEXT,
                employment_type TEXT,
                department TEXT,
                experience TEXT,
                remote_type TEXT,
                posted_date TEXT,
                description TEXT,
                requirements TEXT,
                salary TEXT,
                work_mode TEXT,
                source TEXT,
                relevance_score INTEGER DEFAULT 0,
                is_active BOOLEAN DEFAULT 1,
                created_at TEXT,
                updated_at TEXT,
                FOREIGN KEY (company_id) REFERENCES companies(id) ON DELETE RESTRICT
            );
        """)

        # 4. Contacts Table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS contacts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                company_id INTEGER NOT NULL,
                email TEXT NOT NULL,
                email_type TEXT DEFAULT 'General',
                source_url TEXT,
                created_at TEXT,
                FOREIGN KEY (company_id) REFERENCES companies(id) ON DELETE RESTRICT,
                UNIQUE (company_id, email)
            );
        """)

        # 5. Company Aliases Table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS company_aliases (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                company_id INTEGER NOT NULL,
                alias TEXT NOT NULL,
                created_at TEXT,
                FOREIGN KEY (company_id) REFERENCES companies(id) ON DELETE RESTRICT,
                UNIQUE (company_id, alias)
            );
        """)

        # 6. Job Sources Table (Multi-Source links per position)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS job_sources (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_id INTEGER NOT NULL,
                source TEXT NOT NULL,
                source_job_id TEXT,
                source_url TEXT NOT NULL,
                is_primary BOOLEAN DEFAULT 0,
                first_seen TEXT,
                last_seen TEXT,
                is_active BOOLEAN DEFAULT 1,
                FOREIGN KEY (job_id) REFERENCES jobs(id) ON DELETE CASCADE,
                UNIQUE (job_id, source, source_url)
            );
        """)

        # 7. Job Skills Table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS job_skills (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_id INTEGER NOT NULL,
                skill TEXT NOT NULL,
                FOREIGN KEY (job_id) REFERENCES jobs(id) ON DELETE CASCADE,
                UNIQUE (job_id, skill)
            );
        """)

        # Run safe column additions for backward compatibility
        self._run_migrations(conn)

        # Indices for performance
        cursor.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_companies_company_key ON companies(company_key);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_companies_search_id ON companies(search_id);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_companies_domain ON companies(website_domain);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_companies_norm_name ON companies(normalized_name);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_companies_enrich_status ON companies(enrichment_status);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_company_aliases_alias ON company_aliases(alias);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_company_aliases_comp ON company_aliases(company_id);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_jobs_company_id ON jobs(company_id);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_jobs_norm_title ON jobs(normalized_title);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_jobs_relevance ON jobs(relevance_score);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_job_sources_job_id ON job_sources(job_id);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_job_sources_source ON job_sources(source);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_job_skills_job_id ON job_skills(job_id);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_job_skills_skill ON job_skills(skill);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_contacts_company_id ON contacts(company_id);")

        conn.commit()
        logger.info(f"Database schema initialized at {self.db_path}")

    def _run_migrations(self, conn: sqlite3.Connection):
        """Adds missing columns safely if database already exists."""
        cursor = conn.cursor()
        
        # Check jobs table columns
        cursor.execute("PRAGMA table_info(jobs);")
        existing_job_cols = {row["name"] for row in cursor.fetchall()}
        
        if "normalized_title" not in existing_job_cols:
            try:
                cursor.execute("ALTER TABLE jobs ADD COLUMN normalized_title TEXT;")
            except Exception:
                pass
        if "experience" not in existing_job_cols:
            try:
                cursor.execute("ALTER TABLE jobs ADD COLUMN experience TEXT;")
            except Exception:
                pass
        if "remote_type" not in existing_job_cols:
            try:
                cursor.execute("ALTER TABLE jobs ADD COLUMN remote_type TEXT;")
            except Exception:
                pass
        if "is_active" not in existing_job_cols:
            try:
                cursor.execute("ALTER TABLE jobs ADD COLUMN is_active BOOLEAN DEFAULT 1;")
            except Exception:
                pass

        # Check companies table columns
        cursor.execute("PRAGMA table_info(companies);")
        existing_comp_cols = {row["name"] for row in cursor.fetchall()}
        
        if "company_key" not in existing_comp_cols:
            try:
                cursor.execute("ALTER TABLE companies ADD COLUMN company_key TEXT;")
            except Exception:
                pass
        if "latitude" not in existing_comp_cols:
            try:
                cursor.execute("ALTER TABLE companies ADD COLUMN latitude REAL;")
            except Exception:
                pass
        if "longitude" not in existing_comp_cols:
            try:
                cursor.execute("ALTER TABLE companies ADD COLUMN longitude REAL;")
            except Exception:
                pass
        if "email" not in existing_comp_cols:
            try:
                cursor.execute("ALTER TABLE companies ADD COLUMN email TEXT;")
            except Exception:
                pass
        if "official_domain" not in existing_comp_cols:
            try:
                cursor.execute("ALTER TABLE companies ADD COLUMN official_domain TEXT;")
            except Exception:
                pass
        if "website" not in existing_comp_cols:
            try:
                cursor.execute("ALTER TABLE companies ADD COLUMN website TEXT;")
            except Exception:
                pass

        # Backfill company_key for existing rows without company_key
        try:
            cursor.execute("SELECT id, name, normalized_name, latitude, longitude, website_domain FROM companies WHERE company_key IS NULL OR company_key = '';")
            rows = cursor.fetchall()
            from core.normalizer import JobNormalizer
            for r in rows:
                c_id = r["id"]
                c_name = r["name"] or r["normalized_name"] or f"company_{c_id}"
                c_lat = r["latitude"]
                c_lng = r["longitude"]
                c_dom = r["website_domain"]
                c_key = JobNormalizer.generate_company_key(c_name, c_lat, c_lng, c_dom)
                # Ensure uniqueness during backfill
                cursor.execute("UPDATE companies SET company_key = ? WHERE id = ?;", (c_key or f"comp_{c_id}", c_id))
        except Exception as e:
            logger.debug(f"Migration backfill note: {e}")

        conn.commit()

    def close(self):
        """Closes thread-local connection."""
        if hasattr(self.local, "conn") and self.local.conn is not None:
            try:
                self.local.conn.close()
            except Exception:
                pass
            self.local.conn = None
