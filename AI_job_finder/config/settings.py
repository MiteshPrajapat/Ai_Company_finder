"""
Centralized settings management for Job Finder AI.
Supports .env overrides, default fallbacks, and PyQt6 QSettings persistence.
"""

import os
from pathlib import Path
from dataclasses import dataclass, asdict
from typing import Literal
from dotenv import load_dotenv
from PyQt6.QtCore import QSettings

# Load environment variables
load_dotenv()

# App directories
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)
LOGS_DIR = BASE_DIR / "logs"
LOGS_DIR.mkdir(parents=True, exist_ok=True)

DEFAULT_DB_PATH = str(DATA_DIR / "job_finder.db")


@dataclass
class AppConfig:
    app_name: str = "Job Finder AI"
    database_path: str = DEFAULT_DB_PATH
    browser_type: str = "chrome"
    headless: bool = False
    request_timeout: int = 30
    page_timeout: int = 30
    relevance_threshold: int = 50
    max_concurrent_workers: int = 3
    delay_between_requests: float = 1.5
    search_engine_fallback: str = "auto"  # 'google', 'duckduckgo', 'auto'
    user_agent: str = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )


class SettingsManager:
    """Manages application settings persistence and runtime access."""
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(SettingsManager, cls).__new__(cls)
            cls._instance._init_settings()
        return cls._instance

    def _init_settings(self):
        self.qsettings = QSettings("JobFinderAI", "JobFinderApp")
        self.config = AppConfig(
            app_name=os.getenv("APP_NAME", "Job Finder AI"),
            database_path=os.getenv("DATABASE_PATH", DEFAULT_DB_PATH),
            browser_type=self.qsettings.value("browser_type", os.getenv("BROWSER_TYPE", "chrome"), type=str),
            headless=self.qsettings.value("headless", os.getenv("BROWSER_HEADLESS", "true").lower() == "true", type=bool),
            request_timeout=self.qsettings.value("request_timeout", int(os.getenv("REQUEST_TIMEOUT", "30")), type=int),
            page_timeout=self.qsettings.value("page_timeout", int(os.getenv("PAGE_TIMEOUT", "30")), type=int),
            relevance_threshold=self.qsettings.value("relevance_threshold", int(os.getenv("RELEVANCE_THRESHOLD", "50")), type=int),
            max_concurrent_workers=self.qsettings.value("max_concurrent_workers", int(os.getenv("MAX_CONCURRENT_WORKERS", "3")), type=int),
            delay_between_requests=self.qsettings.value("delay_between_requests", float(os.getenv("DELAY_BETWEEN_REQUESTS", "1.5")), type=float),
            search_engine_fallback=self.qsettings.value("search_engine_fallback", os.getenv("SEARCH_ENGINE_FALLBACK", "auto"), type=str)
        )

    def save_settings(self, **kwargs):
        """Updates and persists runtime settings."""
        for key, value in kwargs.items():
            if hasattr(self.config, key):
                setattr(self.config, key, value)
                self.qsettings.setValue(key, value)
        self.qsettings.sync()

    def get_config(self) -> AppConfig:
        return self.config


settings = SettingsManager()
