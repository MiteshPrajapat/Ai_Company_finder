# 🚀 Job Finder AI — Autonomous Multi-Source Job Discovery & Deduplication Engine

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![PyQt6](https://img.shields.io/badge/GUI-PyQt6-green.svg)](https://pypi.org/project/PyQt6/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Database: SQLite3](https://img.shields.io/badge/Database-SQLite3-lightgrey.svg)](https://www.sqlite.org/)

**Job Finder AI** is a free, production-grade desktop application built with **Python 3.11, PyQt6, Selenium, BeautifulSoup4, and SQLite**. 

It autonomously discovers companies and job openings across multiple platforms in strict priority order (**Company Career Portals → Indeed → Unstop → LinkedIn → Glassdoor**), normalizes unstructured job data, deduplicates companies and open positions using multi-signal scoring, and presents verified opportunities with direct application links in a modern desktop interface.

---

## 🌟 Key Features

### 1. 🔍 Multi-Source Job Aggregation (Strict Priority Order)
Aggregates job listings across 5 primary sources without stopping at the first result:
1. **Company Career Portals & Direct ATS** *(Primary / Highest Priority)*
2. **Indeed** (Public search feeds & listings)
3. **Unstop** (Internships, hiring challenges, early-career opportunities)
4. **LinkedIn** (Public job openings search)
5. **Glassdoor** (Public company job feeds)

### 2. 🧠 Smart Company Deduplication & Centralized Database
* **100% Free / Zero Paid APIs**: Operates without Google Places API or paid identification services.
* **Deterministic `company_key`**: Computes unique matching keys combining `normalized_name` and 3-decimal rounded coordinates (`{norm_name}_{lat:.3f}_{lng:.3f}`) or verified domain.
* **Multi-Tiered Resolution**:
  * **Tier 1**: Exact Verified Domain + Normalized Name match.
  * **Tier 2**: Exact `company_key` match.
  * **Tier 3**: Geographic proximity match (within 15 km).
  * **Tier 4**: Company alias resolution.
  * **Tier 5**: New company creation.
* **Non-Destructive Merging**: Updates existing company records without overwriting valid data with nulls or empty strings.

### 3. 🎯 Position-Level Deduplication Engine
* **Multi-Signal Job Matching (0–100% score)**:
  * **Company Match**: 40%
  * **Job Title Match**: 25% (normalized tokens with level/seniority penalty)
  * **Location Match**: 15% (city/state containment & remote handling)
  * **Skills Overlap**: 10% (Jaccard similarity on extracted tech skills)
  * **Description Match**: 10% (text similarity)
* **Unified Position with Attached Sources**: Merges identical job postings across multiple platforms into a single logical job with all source links attached (`job_sources` table).
* **Position Separation**: Different roles under the same company (e.g. *Frontend Developer* vs *Backend Developer*) are preserved as distinct positions under the same `company_id`.

### 4. 🏢 Autonomous Company Enrichment Pipeline
* **Website Verification**: Live DNS, HTTP/HTTPS, SSL certificate, and redirect status checking.
* **Career Portal Discovery**: Discovers direct careers endpoints (`/careers`, `/jobs`) and crawls ATS platforms.
* **Contact & Email Extraction**: Extracts and classifies business contact emails (`HR`, `Careers`, `Jobs`, `General`, `Support`, `Sales`).
* **Social Media Profiles**: Detects public social links (LinkedIn, GitHub, Twitter/X, Instagram, YouTube, Facebook).

### 5. 💻 Responsive PyQt6 Desktop UI
* **Real-Time Telemetry**: Live progress bars, step-by-step checklists, active browser previews, and streaming logs.
* **Job Openings Explorer**: Searchable and sortable table with Work Mode, Relevance, and Multi-Source filter (`Career Portal`, `Indeed`, `Unstop`, `LinkedIn`, `Glassdoor`).
* **Job Details Modal**: Displays rich descriptions, requirements, extracted skills badges, and direct **"⭐ View Primary"** & **"↗ Apply on [Source]"** buttons.
* **Company Profile Modal**: Tabbed view showing company overview, social links, all grouped positions, and verified business emails.
* **Multi-Format Export**: Export datasets to CSV, Excel (`.xlsx`), or JSON.

---

## 🏗️ Architecture & Data Flow

```text
                  Google Maps / Location Query
                               ↓
                 Company Name, Lat, Lng, Domain
                               ↓
                 Normalizer & Candidate Key
                               ↓
                  Multi-Tier Company Resolver
                               ↓
               ┌───────────────────────────────┐
               │    Centralized `companies`    │
               └───────────────┬───────────────┘
                               │ (company_id)
                               ↓
         Job Aggregation (Career → Indeed → Unstop → LinkedIn → Glassdoor)
                               ↓
                 Position Deduplication Engine
                (Company 40% + Title 25% + Loc 15% + Skills 10% + Desc 10%)
                               ↓
               ┌───────────────────────────────┐
               │        Unified `jobs`         │
               └───────────────┬───────────────┘
                               │ (job_id)
                               ↓
               ┌───────────────────────────────┐
               │      Multi `job_sources`      │
               └───────────────────────────────┘
```

---

## 🗄️ Relational Database Schema

```sql
-- Dedicated Centralized Companies Table
CREATE TABLE companies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    company_key TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    normalized_name TEXT NOT NULL,
    latitude REAL,
    longitude REAL,
    official_domain TEXT,
    website TEXT,
    company_type TEXT,
    address TEXT,
    city TEXT,
    state TEXT,
    country TEXT,
    phone TEXT,
    email TEXT,
    maps_url TEXT,
    rating REAL,
    review_count INTEGER,
    website_status TEXT DEFAULT 'UNKNOWN',
    career_url TEXT,
    career_status TEXT DEFAULT 'PENDING',
    linkedin_url TEXT,
    enrichment_status TEXT DEFAULT 'PENDING',
    created_at TEXT,
    updated_at TEXT
);

-- Distinct Positions under Company
CREATE TABLE jobs (
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

-- Multi-Source Links per Job
CREATE TABLE job_sources (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id INTEGER NOT NULL,
    source TEXT NOT NULL,
    source_job_id TEXT,
    source_url TEXT NOT NULL,
    is_primary BOOLEAN DEFAULT 0,
    first_seen TEXT,
    last_seen TEXT,
    is_active BOOLEAN DEFAULT 1,
    FOREIGN KEY (job_id) REFERENCES jobs(id) ON DELETE RESTRICT
);
```

---

## 📁 Repository Structure

```text
AI_job_finder/
│
├── main.py                          # Application entry point
├── requirements.txt                 # Project dependencies
├── test_multi_source_dedup.py       # Automated verification test suite
├── .env.example                     # Environment configuration template
├── README.md                        # Project documentation
│
├── core/
│   ├── normalizer.py                # Company & job normalizer, key generator, skills extractor
│   ├── deduplication_service.py     # Multi-signal deduplication & resolution engine
│   ├── search_manager.py            # Google Maps search coordinator
│   ├── enrichment_manager.py        # Single company enrichment pipeline
│   ├── job_matcher.py               # Profession synonym engine & relevance scorer
│   └── workflow_manager.py          # Master workflow pipeline (Search → Multi-Source → Deduplicate)
│
├── database/
│   ├── database.py                  # SQLite connection manager with WAL mode & migrations
│   ├── models.py                    # Dataclasses (Company, Job, JobSource, Contact, NormalizedJob)
│   └── repositories.py              # Repository pattern CRUD layer
│
├── scrapers/
│   ├── adapters/                    # Multi-source modular adapters
│   │   ├── base.py                  # Base adapter interface
│   │   ├── career_portal.py         # Career portal & ATS adapter
│   │   ├── indeed.py                # Indeed public listings adapter
│   │   ├── unstop.py                # Unstop opportunities adapter
│   │   ├── linkedin.py              # LinkedIn guest jobs search adapter
│   │   └── glassdoor.py             # Glassdoor public search adapter
│   ├── google_maps.py               # Google Maps place listing & coordinates extractor
│   ├── website.py                   # Website liveness & metadata checker
│   ├── careers.py                   # Career link discovery & ATS scraper
│   ├── contacts.py                  # Business contact email scraper
│   └── social.py                    # Social media profile extractor
│
├── browser/
│   └── browser_manager.py           # Selenium WebDriver lifecycle manager
│
├── workers/
│   └── search_worker.py             # Background QThread worker for non-blocking UI
│
├── utils/
│   ├── logger.py                    # Multi-channel logging & PyQt6 signal emitter
│   ├── url_utils.py                 # URL cleaning, normalization, and domain helpers
│   ├── email_utils.py               # Email regex extraction & validation
│   └── text_utils.py                # Text sanitization & display formatting
│
├── ui/
│   ├── main_window.py               # Primary desktop window & navigation
│   ├── styles.py                    # Modern dark theme QSS stylesheet & status badges
│   ├── job_details.py               # Multi-source job details dialog
│   ├── company_details.py           # Company profile & grouped jobs dialog
│   ├── search_widget.py             # Search input form
│   ├── progress_widget.py           # Real-time progress bar & telemetry view
│   ├── results_widget.py            # Search results table
│   ├── history_widget.py            # Past search sessions browser
│   ├── export_dialog.py             # CSV, Excel, JSON data exporter
│   └── settings_widget.py           # Application settings view
│
├── data/
│   └── job_finder.db                # SQLite database (auto-created)
│
└── logs/
    ├── app.log
    ├── scraper.log
    └── errors.log
```

---

## ⚡ Getting Started

### Prerequisites
* **Python 3.11+** installed
* **Google Chrome** browser installed (Selenium uses Chrome WebDriver automatically)

### Installation

1. **Clone the repository:**
   ```bash
   git clone https://github.com/your-username/AI_job_finder.git
   cd AI_job_finder
   ```

2. **Create and activate a virtual environment:**
   ```bash
   python -m venv venv
   # On Windows:
   venv\Scripts\activate
   # On Linux / macOS:
   source venv/bin/activate
   ```

3. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

4. **Launch the Application:**
   ```bash
   python main.py
   ```

---

## 🧪 Running Automated Tests

To run the multi-source aggregation, normalization, and deduplication verification suite:

```bash
python test_multi_source_dedup.py
```

**Test Coverage Includes:**
* `JobNormalizer`: Corporate suffix stripping (`Google India Pvt Ltd` → `google`), title expansion (`Sr. SWE` → `senior software engineer`), and skills extraction.
* `DeduplicationService`: Cross-source position merging, source rank preservation, and distinct position separation under the same parent company.
* `Coordinate Proximity`: Company matching within geographical proximity bounds.
* `Adapter Layer`: Smoke tests for all 5 source adapters.

---

## 🛡️ Compliance & Best Practices

* **Zero Login / CAPTCHA Bypass**: Uses only public search endpoints, feeds, and open portal data.
* **Transaction Safety**: All database writes occur inside atomic SQLite transactions.
* **Referential Integrity**: Uses SQLite foreign keys (`PRAGMA foreign_keys = ON;`) with `ON DELETE RESTRICT`.

---

## 📄 License

Distributed under the **MIT License**. See `LICENSE` for more information.
