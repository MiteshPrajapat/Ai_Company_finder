# 🚀 Job Finder AI — Autonomous Multi-Source Job Discovery, Deduplication & AI Outreach Engine

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![PyQt6](https://img.shields.io/badge/GUI-PyQt6-green.svg)](https://pypi.org/project/PyQt6/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Database: SQLite3](https://img.shields.io/badge/Database-SQLite3%20WAL-lightgrey.svg)](https://www.sqlite.org/)
[![AI: OpenRouter / Gemini](https://img.shields.io/badge/AI-OpenRouter%20%7C%20Gemini%202.0-purple.svg)](https://openrouter.ai/)
[![Automation: Selenium](https://img.shields.io/badge/Automation-Selenium%204-red.svg)](https://www.selenium.dev/)

**Job Finder AI** is an advanced, free, and open-source desktop application built with **Python 3.11, PyQt6, Selenium, BeautifulSoup4, SQLite (WAL mode), and OpenRouter AI**.

It autonomously discovers target companies and job openings across multiple platforms in strict priority order (**Company Career Portals & ATS → Indeed → Unstop → LinkedIn → Glassdoor**), deduplicates companies and position listings using multi-signal scoring, parses candidate resumes (PDF/Text), computes AI match scores, generates tailored cold outreach emails to verified HR/Hiring Managers, and tracks applications inside a built-in CRM.

---

## 🌟 Key Features

### 1. 🔍 Multi-Source Job Aggregation (Strict Priority Order)
Aggregates job listings across 5 primary sources without stopping at the first result:
1. **Company Career Portals & Direct ATS** *(Primary / Highest Priority — Lever, Greenhouse, Workday, etc.)*
2. **Indeed** (Public search feeds & listings)
3. **Unstop** (Internships, hiring challenges, early-career opportunities)
4. **LinkedIn** (Public guest job openings search)
5. **Glassdoor** (Public company job feeds)

### 2. 🧠 Smart Zero-Cost Company Deduplication
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
* **Search Engine Fallback**: Automatically switches between Google and DuckDuckGo to prevent rate limiting or bot blocking.

### 5. 🤖 AI-Powered Match Analysis & Cold Outreach (Contact HR)
* **Resume Parsing (`pypdf` & Text)**: Upload multiple resumes (`.pdf`, `.txt`, `.md`), auto-extract text, and select a default active resume.
* **AI Match Scoring (0–100%)**: Powered by OpenRouter (supporting `google/gemini-2.0-flash-exp:free`, Claude 3.5, GPT-4o, DeepSeek, etc.).
* **Skills Breakdown**: Categorizes skills into **Required**, **Preferred**, **Matched Skills**, and **Missing Skills**.
* **Smart HR Email Selection**: Prioritizes `HR` > `Careers` > `Jobs` > `General` business emails.
* **Custom Cold Outreach Email Generation**: Generates high-converting cold outreach emails with customizable tones:
  * *Professional & Concise*
  * *Enthusiastic & Bold*
  * *Direct & Impact-Focused*
* **1-Click Webmail Integration**: Pre-fills subject line and email body directly into **Gmail**, **Outlook Web**, or the system's **Default Mail Client (mailto:)**.

### 6. 📊 Job Application CRM Pipeline
* **Application Lifecycle Tracking**: Track application states: `DRAFT`, `READY_TO_SEND`, `BROWSER_OPENED`, `SENT`, `INTERVIEW`, `REJECTED`.
* **Activity Log**: Automatically timestamps actions (e.g., *Generated cold email*, *Opened Gmail*, *Status changed to Sent*).
* **Direct Actions**: Quick clipboard copy, webmail launch, and application status updates from a dedicated **Applications** tab.

### 7. 💻 Responsive PyQt6 Desktop UI
* **Real-Time Telemetry**: Live progress bars, step-by-step checklists, active browser previews, and streaming logs.
* **Job Openings Explorer**: Searchable and sortable table with Work Mode, Relevance, and Multi-Source filters.
* **Job Details Modal**: Displays rich descriptions, requirements, extracted skills badges, and direct **"⭐ View Primary"** & **"↗ Apply on [Source]"** buttons.
* **Company Profile Modal**: Tabbed view showing company overview, social links, all grouped positions, and verified business emails.
* **Multi-Format Export**: Export datasets to CSV, Excel (`.xlsx`), or JSON.

---

## 🏗️ System Architecture

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
                └───────┬───────────────┬───────┘
                        │ (job_id)      │
                        ↓               ↓
         ┌─────────────────────┐  ┌───────────────────────────────────┐
         │ Multi `job_sources` │  │  AI Match & Cold Outreach Engine  │
         └─────────────────────┘  │  (OpenRouter / Gemini 2.0 Flash)  │
                                  └─────────────────┬─────────────────┘
                                                    │
                                                    ↓
                                  ┌───────────────────────────────────┐
                                  │   Application Tracking CRM        │
                                  │   (Gmail / Outlook / Mailto)      │
                                  └───────────────────────────────────┘
```

---

## 🗄️ Database Schema (SQLite WAL Mode)

```sql
-- 1. Centralized Companies
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

-- 2. Positions under Company
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

-- 3. Multi-Source Links per Job
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

-- 4. Extracted Business & HR Contacts
CREATE TABLE contacts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    company_id INTEGER NOT NULL,
    email TEXT NOT NULL,
    email_type TEXT DEFAULT 'General',
    source_url TEXT,
    created_at TEXT,
    FOREIGN KEY (company_id) REFERENCES companies(id) ON DELETE RESTRICT
);

-- 5. Candidate Resumes
CREATE TABLE resumes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    file_path TEXT NOT NULL,
    extracted_text TEXT NOT NULL,
    is_default BOOLEAN DEFAULT 0,
    created_at TEXT
);

-- 6. Job Applications & Outreach CRM
CREATE TABLE job_applications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id INTEGER NOT NULL,
    company_id INTEGER NOT NULL,
    resume_id INTEGER,
    hr_email TEXT NOT NULL,
    subject TEXT,
    email_body TEXT,
    match_score INTEGER DEFAULT 0,
    status TEXT DEFAULT 'DRAFT',
    activity_log TEXT,
    applied_at TEXT,
    created_at TEXT,
    updated_at TEXT,
    FOREIGN KEY (job_id) REFERENCES jobs(id) ON DELETE RESTRICT,
    FOREIGN KEY (company_id) REFERENCES companies(id) ON DELETE RESTRICT,
    FOREIGN KEY (resume_id) REFERENCES resumes(id) ON DELETE SET NULL
);
```

---

## 📁 Repository Structure

```text
AI_job_finder/
│
├── main.py                          # Application entry point (PyQt6 runner)
├── requirements.txt                 # Project dependencies
├── test_multi_source_dedup.py       # Deduplication & multi-source test suite
├── test_ai_contact_hr.py            # AI Prompt, Resume & CRM test suite
├── .env.example                     # Environment configuration template
├── README.md                        # Documentation
│
├── core/
│   ├── ai/                          # OpenRouter & AI Pipeline
│   │   ├── openrouter_client.py     # OpenRouter REST API client
│   │   ├── prompt_builders.py       # Match analysis & cold outreach prompt builder
│   │   └── resume_extractor.py      # PDF & Text resume parser
│   ├── normalizer.py                # Company & job normalizer, key generator, skills extractor
│   ├── deduplication_service.py     # Multi-signal deduplication & resolution engine
│   ├── search_manager.py            # Search coordinator (Google Maps / Location)
│   ├── enrichment_manager.py        # Single company enrichment pipeline
│   ├── job_matcher.py               # Profession synonym engine & relevance scorer
│   └── workflow_manager.py          # Master discovery pipeline
│
├── database/
│   ├── database.py                  # SQLite connection manager with WAL mode & schema migrations
│   ├── models.py                    # Dataclasses (Company, Job, JobSource, Contact, Resume, JobApplication)
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
│   ├── browser_manager.py           # Selenium WebDriver lifecycle manager
│   ├── google.py                    # Google Search automation helper
│   ├── duckduckgo.py                # DuckDuckGo fallback scraper
│   └── email_automation.py          # Webmail URL generator (Gmail, Outlook, mailto)
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
│   ├── main_window.py               # Primary desktop window & navigation tabs
│   ├── styles.py                    # Modern dark theme QSS stylesheet & status badges
│   ├── search_widget.py             # Search input form
│   ├── progress_widget.py           # Real-time progress bar & telemetry view
│   ├── results_widget.py            # Search results & open positions table
│   ├── applications_widget.py       # CRM Application pipeline table
│   ├── contact_hr_dialog.py         # AI match score, skills radar & cold email generator
│   ├── job_details.py               # Multi-source job details dialog
│   ├── company_details.py           # Company profile & grouped jobs dialog
│   ├── history_widget.py            # Past search sessions browser
│   ├── settings_widget.py           # Application settings, profile & AI config view
│   └── export_dialog.py             # CSV, Excel, JSON data exporter
│
├── data/
│   ├── job_finder.db                # SQLite database (auto-created on launch)
│   └── resumes/                     # Uploaded candidate resumes directory
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
* **Google Chrome** browser installed (Selenium automatically manages ChromeDriver)
* *(Optional)* **OpenRouter API Key** (Free tier available for Gemini 2.0 Flash at [openrouter.ai](https://openrouter.ai))

### Installation

1. **Clone the repository:**
   ```bash
   git clone https://github.com/MiteshPrajapat/Ai_Company_finder.git
   cd AI_job_finder
   ```

2. **Create and activate a virtual environment:**
   ```bash
   python -m venv venv
   # On Windows (PowerShell):
   .\venv\Scripts\Activate.ps1
   # On Windows (CMD):
   venv\Scripts\activate.bat
   # On Linux / macOS:
   source venv/bin/activate
   ```

3. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

4. **Configure environment variables (Optional):**
   ```bash
   cp .env.example .env
   ```
   *(You can also configure API keys and settings directly within the UI Settings tab!)*

5. **Launch the Application:**
   ```bash
   python main.py
   ```

---

## 🧪 Running Automated Tests

Run the comprehensive test suites to verify scrapers, deduplication, AI prompts, and database migrations:

### 1. Multi-Source Aggregation & Deduplication Tests
```bash
python test_multi_source_dedup.py
```
* Tests `JobNormalizer` (corporate suffix stripping, seniority tokens, skills extraction).
* Tests `DeduplicationService` (merging identical cross-source jobs, keeping distinct company roles).
* Tests SQLite WAL relational schema and constraints.

### 2. AI Resume Matcher & Contact HR Tests
```bash
python test_ai_contact_hr.py
```
* Tests PDF and plaintext resume parsing.
* Tests OpenRouter prompt synthesis and structured JSON parsing.
* Tests Application CRM repository CRUD operations.
* Tests Gmail and Outlook Web compose URL builders.

---

## ⚙️ Configuration Reference

You can customize runtime behavior in `.env` or in the **Settings** tab in the desktop application:

| Variable | Default | Description |
| :--- | :--- | :--- |
| `DATABASE_PATH` | `data/job_finder.db` | Path to local SQLite database |
| `BROWSER_TYPE` | `chrome` | Browser engine for Selenium (`chrome`) |
| `BROWSER_HEADLESS` | `false` | Run browser in headless mode (`true` / `false`) |
| `REQUEST_TIMEOUT` | `30` | Timeout in seconds for HTTP requests |
| `RELEVANCE_THRESHOLD` | `50` | Minimum score (0–100) for job filtering |
| `MAX_CONCURRENT_WORKERS` | `3` | Parallel scraping workers |
| `SEARCH_ENGINE_FALLBACK`| `auto` | Fallback search engine (`auto`, `google`, `duckduckgo`) |
| `OPENROUTER_API_KEY` | *Empty* | API Key for AI Match Analysis & Cold Outreach |
| `OPENROUTER_MODEL` | `google/gemini-2.0-flash-exp:free` | OpenRouter model identifier |
| `USER_FULL_NAME` | *Empty* | Candidate full name for email signing |
| `USER_EMAIL` | *Empty* | Candidate contact email |
| `USER_LINKEDIN` | *Empty* | Candidate LinkedIn profile URL |
| `USER_PORTFOLIO` | *Empty* | Candidate GitHub or portfolio URL |

---

## 🛡️ Compliance & Best Practices

* **Zero Login / CAPTCHA Bypass**: Uses only public search endpoints, feeds, and open portal data.
* **Transaction Safety**: All database writes occur inside atomic SQLite transactions (`BEGIN IMMEDIATE`).
* **Referential Integrity**: Uses SQLite foreign keys (`PRAGMA foreign_keys = ON;`) with `ON DELETE RESTRICT` on core records.
* **Data Privacy**: Resumes and candidate profile data stay 100% local on your machine. API calls to OpenRouter only send job descriptions and resume text for analysis.

---

## 📄 License

Distributed under the **MIT License**. See `LICENSE` for more information.
