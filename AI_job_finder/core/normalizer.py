"""
Normalization layer converting disparate job postings from multiple sources into a consistent internal format.
Handles company name stripping, title expansion, location normalization, work mode, and skill extraction.
"""

import re
from typing import List, Optional, Dict, Any, Tuple
from utils.url_utils import extract_domain, clean_url
from utils.text_utils import sanitize_text

# Common legal and corporate suffixes to strip for canonical company matching
CORPORATE_SUFFIXES = [
    r"\bprivate\s+limited\b",
    r"\bpvt\s*\.?\s*ltd\b",
    r"\bltd\s*\.?\b",
    r"\bllc\b",
    r"\binc\s*\.?\b",
    r"\bincorporated\b",
    r"\bcorporation\b",
    r"\bcorp\s*\.?\b",
    r"\bgmbh\b",
    r"\bco\s*\.?\b",
    r"\bcompany\b",
    r"\btechnologies\b",
    r"\btechnology\b",
    r"\bsolutions\b",
    r"\bservices\b",
    r"\binfotech\b",
    r"\bsoftwares?\b",
    r"\bsystems\b",
    r"\bindia\b",
    r"\bllp\b",
    r"\bgroup\b"
]

# Standard tech skill dictionary for tagging
TECH_SKILLS = [
    "python", "javascript", "typescript", "react", "react.js", "react native",
    "angular", "vue", "vue.js", "node.js", "nodejs", "express", "django",
    "fastapi", "flask", "java", "spring boot", "spring", "c++", "c#", ".net",
    "golang", "go", "rust", "php", "laravel", "ruby", "rails", "swift",
    "kotlin", "flutter", "sql", "mysql", "postgresql", "postgres", "mongodb",
    "redis", "elasticsearch", "graphql", "rest api", "docker", "kubernetes",
    "aws", "azure", "gcp", "google cloud", "ci/cd", "git", "linux", "terraform",
    "machine learning", "deep learning", "ai", "artificial intelligence",
    "nlp", "computer vision", "pytorch", "tensorflow", "keras", "pandas",
    "numpy", "scikit-learn", "data engineering", "spark", "hadoop", "kafka",
    "snowflake", "airflow", "tableau", "power bi", "devops", "qa", "selenium",
    "playwright", "cypress", "unit testing", "microservices", "html", "css",
    "sass", "tailwind", "figma", "ui/ux", "agile", "scrum"
]

# Job title expansions & standardizations
TITLE_MAP = {
    r"\bsr\.?\s+": "senior ",
    r"\bjr\.?\s+": "junior ",
    r"\bswe\b": "software engineer",
    r"\bsde\s*1\b": "software development engineer i",
    r"\bsde\s*2\b": "software development engineer ii",
    r"\bsde\s*3\b": "software development engineer iii",
    r"\bsde\b": "software development engineer",
    r"\bdev\b": "developer",
    r"\bfullstack\b": "full stack developer",
    r"\bfull-stack\b": "full stack developer",
    r"\bfront-end\b": "frontend developer",
    r"\bfront\s*end\b": "frontend developer",
    r"\bback-end\b": "backend developer",
    r"\bback\s*end\b": "backend developer",
    r"\bml\b": "machine learning engineer",
    r"\bai\b": "ai engineer",
    r"\bqa\b": "qa engineer",
    r"\bui/ux\b": "ui/ux designer",
}


class JobNormalizer:
    """Normalizes raw unstructured job data across all providers."""

    @staticmethod
    def normalize_company_name(name: str) -> str:
        """
        Normalizes company names into canonical match keys.
        Example: 'Google India Pvt Ltd' -> 'google'
                 'Tata Consultancy Services Ltd.' -> 'tata consultancy'
        """
        if not name:
            return ""

        text = name.lower().strip()
        # Remove text in parentheses (e.g. 'Infosys (India)')
        text = re.sub(r"\(.*?\)", "", text)
        # Remove pipe or dash taglines (e.g. 'Synarion IT | App Development Company')
        if "|" in text:
            text = text.split("|")[0]
        if " - " in text:
            text = text.split(" - ")[0]
        if " — " in text:
            text = text.split(" — ")[0]

        # Strip standard corporate suffixes
        for suffix_pat in CORPORATE_SUFFIXES:
            text = re.sub(suffix_pat, "", text, flags=re.IGNORECASE)

        # Remove special characters and redundant spaces
        text = re.sub(r"[^a-z0-9\s]", " ", text)
        text = re.sub(r"\s+", " ", text).strip()
        return text

    @staticmethod
    def normalize_job_title(title: str) -> str:
        """
        Standardizes job titles to facilitate cross-source position deduplication.
        Example: 'Sr. Python Dev (Urgent)' -> 'senior python developer'
        """
        if not title:
            return ""

        text = title.lower().strip() + " "
        # Remove tags in brackets/parentheses e.g. [Immediate Joiner] or (Remote)
        text = re.sub(r"\[.*?\]", "", text)
        text = re.sub(r"\(.*?(?:remote|immediate|urgent|full\s*time|part\s*time|m/f/d|experience).*?\)", "", text)
        
        # Remove common marketing fluff
        fluff_patterns = [
            r"\burgent\s*hiring\b",
            r"\bhiring\s*now\b",
            r"\bimmediate\s*joiner\b",
            r"\bimmediate\s*requirement\b",
            r"\bwe\s*are\s*hiring\b",
            r"\bopening\s*for\b",
            r"\bjob\s*opening\b",
            r"\bm/f/d\b",
            r"\bexp\s*:\s*\d+.*?\b",
            r"\b\d+\+?\s*years?\s*exp.*?\b"
        ]
        for pat in fluff_patterns:
            text = re.sub(pat, "", text, flags=re.IGNORECASE)

        # Expand title abbreviations
        for pat, replacement in TITLE_MAP.items():
            text = re.sub(pat, replacement, text, flags=re.IGNORECASE)

        # Clean noise & punctuation
        text = re.sub(r"[^a-z0-9\s]", " ", text)
        text = re.sub(r"\s+", " ", text).strip()
        return text

    @staticmethod
    def normalize_location(location: Optional[str]) -> Tuple[Optional[str], bool]:
        """
        Normalizes location string and identifies if remote.
        Returns: (clean_location, is_remote)
        """
        if not location:
            return None, False

        loc_lower = location.lower().strip()
        is_remote = "remote" in loc_lower or "anywhere" in loc_lower or "work from home" in loc_lower or "wfh" in loc_lower

        # Clean up separators
        clean_loc = sanitize_text(location)
        clean_loc = re.sub(r"\s*,\s*", ", ", clean_loc)
        return clean_loc if clean_loc else None, is_remote

    @staticmethod
    def normalize_remote_type(text: Optional[str], location: Optional[str] = None) -> str:
        """
        Determines work mode: 'Remote', 'Hybrid', or 'On-site'.
        """
        combined = f"{text or ''} {location or ''}".lower()
        if "remote" in combined or "work from home" in combined or "wfh" in combined:
            return "Remote"
        if "hybrid" in combined or "flexible" in combined:
            return "Hybrid"
        return "On-site"

    @staticmethod
    def normalize_employment_type(text: Optional[str]) -> str:
        """
        Determines standard employment type: 'Full-time', 'Part-time', 'Contract', 'Internship'.
        """
        if not text:
            return "Full-time"
        t = text.lower()
        if "intern" in t:
            return "Internship"
        if "contract" in t or "freelance" in t or "temp" in t:
            return "Contract"
        if "part" in t:
            return "Part-time"
        return "Full-time"

    @staticmethod
    def extract_skills(text: Optional[str]) -> List[str]:
        """
        Extracts tech skills mentioned in title, description, or requirements.
        """
        if not text:
            return []

        text_lower = f" {text.lower()} "
        found_skills = set()

        for skill in TECH_SKILLS:
            # Word boundary matching for short skills (e.g. 'c++', 'go', 'ai')
            pattern = rf"(?:\b|\s){re.escape(skill)}(?:\b|\s)"
            if re.search(pattern, text_lower):
                found_skills.add(skill.title() if len(skill) > 3 else skill.upper())

        return sorted(list(found_skills))

    @staticmethod
    def extract_coordinates_from_url(maps_url: Optional[str]) -> Tuple[Optional[float], Optional[float]]:
        """
        Extracts latitude and longitude from Google Maps URLs.
        Supports /@lat,lng, !3dlat!4dlng, and ?q=lat,lng patterns.
        """
        if not maps_url:
            return None, None
        try:
            # Pattern 1: !3d26.9124!4d75.7873
            m_3d = re.search(r"!3d(-?\d+\.\d+)!4d(-?\d+\.\d+)", maps_url)
            if m_3d:
                return float(m_3d.group(1)), float(m_3d.group(2))

            # Pattern 2: /@26.9124,75.7873
            m_at = re.search(r"/@(-?\d+\.\d+),(-?\d+\.\d+)", maps_url)
            if m_at:
                return float(m_at.group(1)), float(m_at.group(2))

            # Pattern 3: query coords ?q=26.9124,75.7873
            m_q = re.search(r"[?&]q=(-?\d+\.\d+),(-?\d+\.\d+)", maps_url)
            if m_q:
                return float(m_q.group(1)), float(m_q.group(2))
        except Exception:
            pass
        return None, None

    @staticmethod
    def calculate_distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """Calculates distance in kilometers using the Haversine formula."""
        import math
        R = 6371.0  # Earth's radius in km
        dlat = math.radians(lat2 - lat1)
        dlon = math.radians(lon2 - lon1)
        a = (
            math.sin(dlat / 2) ** 2
            + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
        )
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
        return R * c

    @staticmethod
    def generate_company_key(
        company_name: str,
        latitude: Optional[float] = None,
        longitude: Optional[float] = None,
        domain: Optional[str] = None
    ) -> str:
        """
        Generates a deterministic candidate company_key using normalized name and rounded coordinates.
        Example: 'tcs_26.912_75.787' or fallback 'tcs_tcs.com' / 'tcs'
        """
        norm_name = JobNormalizer.normalize_company_name(company_name)
        clean_dom = extract_domain(domain) if domain else None

        if latitude is not None and longitude is not None:
            r_lat = round(float(latitude), 3)
            r_lng = round(float(longitude), 3)
            return f"{norm_name}_{r_lat:.3f}_{r_lng:.3f}"

        if clean_dom:
            return f"{norm_name}_{clean_dom}"

        return norm_name

    @staticmethod
    def normalize_salary(salary_text: Optional[str]) -> Optional[str]:
        """
        Cleans salary information into a clean readable string.
        """
        if not salary_text:
            return None
        clean = sanitize_text(salary_text).strip()
        if len(clean) < 3 or clean.lower() in ["not disclosed", "competitive", "best in industry"]:
            return None
        return clean
