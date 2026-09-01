"""
Job matching engine, synonym mapping, and relevance scoring system.
Evaluates job titles, descriptions, and requirements against target professions.
"""

import re
from typing import Dict, List, Set, Optional
from utils.text_utils import extract_keywords, sanitize_text

# Comprehensive synonym and skill mapping for presets
PROFESSION_SYNONYMS: Dict[str, Dict[str, List[str]]] = {
    "Web Developer": {
        "titles": [
            "web developer", "frontend developer", "front-end developer", "backend developer",
            "back-end developer", "full stack developer", "full-stack developer", "fullstack developer",
            "javascript developer", "typescript developer", "react developer", "vue developer",
            "angular developer", "node developer", "web engineer", "web designer", "web programmer"
        ],
        "keywords": ["html", "css", "javascript", "typescript", "react", "vue", "angular", "node", "rest", "api", "responsive", "frontend", "backend", "web"]
    },
    "Frontend Developer": {
        "titles": [
            "frontend developer", "front-end developer", "frontend engineer", "front-end engineer",
            "ui developer", "react developer", "vue developer", "angular developer", "nextjs developer",
            "javascript developer", "client-side developer", "web ui developer"
        ],
        "keywords": ["html5", "css3", "sass", "javascript", "typescript", "react", "vue", "angular", "next.js", "tailwind", "webpack", "redux", "ui/ux"]
    },
    "Backend Developer": {
        "titles": [
            "backend developer", "back-end developer", "backend engineer", "back-end engineer",
            "server-side developer", "api developer", "python developer", "java developer",
            "node.js developer", "golang developer", "php developer", "django developer"
        ],
        "keywords": ["python", "java", "node", "golang", "php", "django", "fastapi", "spring", "sql", "postgresql", "mongodb", "redis", "rest api", "microservices"]
    },
    "Full Stack Developer": {
        "titles": [
            "full stack developer", "full-stack developer", "fullstack developer", "full stack engineer",
            "fullstack engineer", "mern developer", "mean developer", "full-stack software engineer"
        ],
        "keywords": ["full stack", "fullstack", "mern", "mean", "react", "node", "express", "sql", "nosql", "frontend", "backend", "api"]
    },
    "Python Developer": {
        "titles": [
            "python developer", "python engineer", "python backend developer", "django developer",
            "flask developer", "fastapi developer", "python programmer"
        ],
        "keywords": ["python", "django", "flask", "fastapi", "pandas", "numpy", "sqlalchemy", "celery", "pyqt", "automation"]
    },
    "Java Developer": {
        "titles": [
            "java developer", "java engineer", "java software engineer", "j2ee developer",
            "spring boot developer", "java backend developer"
        ],
        "keywords": ["java", "spring", "spring boot", "hibernate", "jpa", "microservices", "maven", "gradle", "jvm", "rest"]
    },
    "Software Engineer": {
        "titles": [
            "software engineer", "software developer", "swe", "sde", "sde 1", "sde 2", "sde 3",
            "senior software engineer", "lead software engineer", "programmer", "coder",
            "application developer", "systems engineer"
        ],
        "keywords": ["software", "algorithms", "data structures", "system design", "git", "ci/cd", "development", "architecture", "coding"]
    },
    "AI Engineer": {
        "titles": [
            "ai engineer", "artificial intelligence engineer", "ai developer", "generative ai engineer",
            "prompt engineer", "llm engineer", "deep learning engineer", "nlp engineer", "computer vision engineer"
        ],
        "keywords": ["artificial intelligence", "ai", "llm", "deep learning", "neural network", "openai", "transformers", "nlp", "computer vision", "langchain", "pytorch"]
    },
    "ML Engineer": {
        "titles": [
            "ml engineer", "machine learning engineer", "machine learning scientist",
            "applied ml engineer", "mlops engineer"
        ],
        "keywords": ["machine learning", "ml", "scikit-learn", "tensorflow", "pytorch", "keras", "xgboost", "model training", "features", "mlops"]
    },
    "Data Scientist": {
        "titles": [
            "data scientist", "lead data scientist", "senior data scientist", "data science analyst",
            "decision scientist", "research scientist"
        ],
        "keywords": ["data science", "statistics", "machine learning", "python", "r", "pandas", "matplotlib", "predictive modeling", "hypothesis testing"]
    },
    "Data Engineer": {
        "titles": [
            "data engineer", "big data engineer", "etl developer", "data warehouse engineer",
            "data platform engineer", "analytics engineer"
        ],
        "keywords": ["etl", "pipeline", "spark", "hadoop", "airflow", "kafka", "snowflake", "databricks", "sql", "data warehouse", "dbt"]
    },
    "DevOps Engineer": {
        "titles": [
            "devops engineer", "site reliability engineer", "sre", "cloud devops engineer",
            "infrastructure engineer", "build and release engineer", "platform engineer"
        ],
        "keywords": ["devops", "docker", "kubernetes", "k8s", "ci/cd", "jenkins", "gitlab", "terraform", "ansible", "aws", "linux", "prometheus", "grafana"]
    },
    "Cloud Engineer": {
        "titles": [
            "cloud engineer", "cloud architect", "aws engineer", "azure engineer", "gcp engineer",
            "cloud solutions architect", "cloud infrastructure engineer"
        ],
        "keywords": ["cloud", "aws", "azure", "gcp", "iam", "serverless", "lambda", "ec2", "s3", "cloudformation", "terraform", "infrastructure"]
    },
    "Mobile Developer": {
        "titles": [
            "mobile developer", "mobile app developer", "android developer", "ios developer",
            "flutter developer", "react native developer", "swift developer", "kotlin developer"
        ],
        "keywords": ["android", "ios", "flutter", "react native", "swift", "kotlin", "mobile app", "xcode", "android studio", "dart"]
    },
    "QA Engineer": {
        "titles": [
            "qa engineer", "quality assurance engineer", "software test engineer", "sdet",
            "automation test engineer", "manual tester", "qa analyst", "test lead"
        ],
        "keywords": ["qa", "testing", "quality assurance", "test cases", "selenium", "cypress", "playwright", "junit", "pytest", "bug tracking", "sdet", "regression"]
    },
    "Cyber Security": {
        "titles": [
            "cyber security engineer", "security analyst", "infosec engineer", "penetration tester",
            "ethical hacker", "soc analyst", "security architect", "information security specialist"
        ],
        "keywords": ["cyber security", "infosec", "soc", "penetration testing", "vulnerability", "siem", "firewall", "encryption", "owasp", "incident response"]
    },
    "UI/UX Designer": {
        "titles": [
            "ui/ux designer", "ui designer", "ux designer", "product designer",
            "user interface designer", "user experience researcher", "visual designer", "interaction designer"
        ],
        "keywords": ["ui", "ux", "figma", "sketch", "adobe xd", "wireframe", "prototyping", "user research", "user flow", "design system"]
    },
    "Sales": {
        "titles": [
            "sales executive", "business development executive", "bde", "account executive",
            "sales manager", "inside sales representative", "lead generation specialist", "sales director"
        ],
        "keywords": ["sales", "b2b", "b2c", "revenue", "lead generation", "crm", "cold calling", "client acquisition", "negotiation", "prospecting"]
    },
    "Marketing": {
        "titles": [
            "marketing executive", "digital marketing specialist", "marketing manager",
            "seo specialist", "content marketer", "growth marketer", "social media manager", "performance marketer"
        ],
        "keywords": ["marketing", "seo", "sem", "google ads", "content marketing", "social media", "campaigns", "analytics", "branding", "copywriting"]
    },
    "HR": {
        "titles": [
            "hr executive", "human resources specialist", "talent acquisition specialist",
            "technical recruiter", "hr generalist", "hr manager", "people operations", "recruitment specialist"
        ],
        "keywords": ["hr", "human resources", "recruitment", "talent acquisition", "sourcing", "onboarding", "payroll", "interviews", "employee relations"]
    }
}

# Negative keywords for tech jobs to filter out completely irrelevant roles
IRRELEVANT_JOB_TERMS = [
    "driver", "cook", "chef", "gardener", "housekeeping", "security guard",
    "delivery boy", "waiter", "electrician", "plumber", "carpenter",
    "receptionist", "office assistant", "peon", "janitor"
]


class JobMatcher:
    """Intelligent job filtering and multi-factor relevance scoring engine."""

    def __init__(self, profession: str, custom_profession: Optional[str] = None, threshold: int = 50):
        self.profession = profession
        self.custom_profession = custom_profession
        self.threshold = threshold
        self._setup_criteria()

    def _setup_criteria(self):
        """Prepares matching titles and keyword sets based on selected profession."""
        target_pref = self.profession
        if target_pref == "Other" and self.custom_profession:
            target_pref = self.custom_profession.strip()

        if target_pref == "All":
            self.is_all_professions = True
            self.target_titles = []
            self.target_keywords = []
            return

        self.is_all_professions = False

        # Check if known preset
        if target_pref in PROFESSION_SYNONYMS:
            preset = PROFESSION_SYNONYMS[target_pref]
            self.target_titles = [t.lower() for t in preset["titles"]]
            self.target_keywords = [k.lower() for k in preset["keywords"]]
        else:
            # Dynamic generation for custom profession
            clean_custom = target_pref.lower()
            words = extract_keywords(clean_custom)
            self.target_titles = [clean_custom]
            # Add variations with developer/engineer/manager if not present
            variations = [f"{w} specialist" for w in words] + [f"{w} consultant" for w in words]
            self.target_titles.extend(variations)
            self.target_keywords = words

    def calculate_relevance(
        self,
        title: str,
        description: Optional[str] = None,
        requirements: Optional[str] = None,
        department: Optional[str] = None
    ) -> int:
        """
        Calculates a job relevance score from 0 to 100 based on weighted criteria.
        - Title match: max 50 points
        - Description & skills match: max 25 points
        - Requirements match: max 15 points
        - Department match: max 10 points
        """
        if not title:
            return 0

        title_lower = title.lower().strip()
        desc_lower = (description or "").lower()
        req_lower = (requirements or "").lower()
        dept_lower = (department or "").lower()

        if getattr(self, "is_all_professions", False):
            return 95

        # Immediate filter for completely irrelevant physical/unrelated jobs
        for bad_term in IRRELEVANT_JOB_TERMS:
            if re.search(r"\b" + re.escape(bad_term) + r"\b", title_lower):
                return 5  # Heavily penalize

        score = 0

        # Strip common seniority prefixes for core title matching
        core_title = re.sub(r"\b(senior|sr|junior|jr|lead|principal|staff|associate|entry level|intern|internship)\b", "", title_lower).strip()

        # 1. Title Match (up to 50 pts)
        title_matched = False
        for syn in self.target_titles:
            if syn == title_lower or syn == core_title:
                score += 50  # Exact match
                title_matched = True
                break
            elif syn in title_lower or syn in core_title or core_title in syn:
                score += 45  # Strong substring match
                title_matched = True
                break

        title_words = set(extract_keywords(title_lower))
        matched_title_kws = sum(1 for kw in self.target_keywords if kw in title_words)

        if not title_matched:
            if matched_title_kws > 0:
                score += min(50, matched_title_kws * 18)
        elif matched_title_kws >= 2 and score < 50:
            score = 50

        # 2. Description Match (up to 30 pts)
        if desc_lower:
            desc_kw_hits = sum(1 for kw in self.target_keywords if re.search(r"\b" + re.escape(kw) + r"\b", desc_lower))
            score += min(30, desc_kw_hits * 8)

        # 3. Requirements Match (up to 15 pts)
        if req_lower:
            req_kw_hits = sum(1 for kw in self.target_keywords if re.search(r"\b" + re.escape(kw) + r"\b", req_lower))
            score += min(15, req_kw_hits * 5)

        # 4. Department / Context Match (up to 10 pts)
        if dept_lower:
            if any(kw in dept_lower for kw in self.target_keywords) or any(t in dept_lower for t in self.target_titles):
                score += 10

        # Normalize score bounds 0 - 100
        return max(0, min(100, score))

    def is_relevant(self, score: int) -> bool:
        """Determines if the score meets the relevance threshold."""
        return score >= self.threshold
