"""
Logging configuration for Job Finder AI.
Supports file logging, console logging, and Qt Signal streaming for UI integration.
"""

import os
import sys
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Optional
from PyQt6.QtCore import QObject, pyqtSignal

# Ensure logs directory exists
LOGS_DIR = Path("logs")
LOGS_DIR.mkdir(parents=True, exist_ok=True)

APP_LOG_PATH = LOGS_DIR / "app.log"
SCRAPER_LOG_PATH = LOGS_DIR / "scraper.log"
ERRORS_LOG_PATH = LOGS_DIR / "errors.log"


class QtLogEmitter(QObject):
    """Qt signal emitter for streaming logs to UI widgets."""
    log_record = pyqtSignal(str, str, str)  # (timestamp, level, message)


qt_log_emitter = QtLogEmitter()


class QtLogHandler(logging.Handler):
    """Custom logging handler that emits records via Qt signals."""
    def __init__(self, emitter: QtLogEmitter):
        super().__init__()
        self.emitter = emitter

    def emit(self, record: logging.LogRecord):
        try:
            msg = self.format(record)
            level = record.levelname
            timestamp = self.formatter.formatTime(record, "%Y-%m-%d %H:%M:%S") if self.formatter else ""
            self.emitter.log_record.emit(timestamp, level, msg)
        except Exception:
            self.handleError(record)


_initialized = False


def setup_logger(log_level: int = logging.INFO) -> logging.Logger:
    """Configures multi-channel application logging."""
    global _initialized
    root_logger = logging.getLogger("JobFinderAI")

    if _initialized:
        return root_logger

    root_logger.setLevel(logging.DEBUG)
    root_logger.propagate = False

    formatter = logging.Formatter(
        fmt="%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    # 1. Console Handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(log_level)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    # 2. Main App Rotating File Handler (5 MB max, 3 backups)
    app_file_handler = RotatingFileHandler(
        APP_LOG_PATH, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8"
    )
    app_file_handler.setLevel(logging.DEBUG)
    app_file_handler.setFormatter(formatter)
    root_logger.addHandler(app_file_handler)

    # 3. Errors Rotating File Handler
    error_file_handler = RotatingFileHandler(
        ERRORS_LOG_PATH, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8"
    )
    error_file_handler.setLevel(logging.ERROR)
    error_file_handler.setFormatter(formatter)
    root_logger.addHandler(error_file_handler)

    # 4. Scraper Dedicated Logger
    scraper_logger = logging.getLogger("JobFinderAI.scraper")
    scraper_file_handler = RotatingFileHandler(
        SCRAPER_LOG_PATH, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8"
    )
    scraper_file_handler.setLevel(logging.DEBUG)
    scraper_file_handler.setFormatter(formatter)
    scraper_logger.addHandler(scraper_file_handler)

    # 5. Qt UI Log Handler
    qt_handler = QtLogHandler(qt_log_emitter)
    qt_handler.setLevel(logging.INFO)
    qt_handler.setFormatter(logging.Formatter("%(message)s"))
    root_logger.addHandler(qt_handler)

    _initialized = True
    root_logger.info("Job Finder AI logging initialized.")
    return root_logger


def get_logger(name: Optional[str] = None) -> logging.Logger:
    """Retrieves a named logger child of JobFinderAI."""
    if not _initialized:
        setup_logger()
    if name:
        return logging.getLogger(f"JobFinderAI.{name}")
    return logging.getLogger("JobFinderAI")
