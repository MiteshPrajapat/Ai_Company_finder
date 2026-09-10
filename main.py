"""
Entry point for Job Finder AI desktop application.
"""

import sys
import os
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt
from utils.logger import setup_logger, get_logger
from database.database import Database
from ui.main_window import MainWindow

# Initialize Logger
logger = setup_logger()


def main():
    logger.info("=========================================")
    logger.info("    Starting Job Finder AI Application   ")
    logger.info("=========================================")

    # Initialize SQLite Database & Tables
    db = Database()
    db.init_schema()

    # Enable High DPI scaling
    if hasattr(Qt.ApplicationAttribute, "AA_EnableHighDpiScaling"):
        QApplication.setAttribute(Qt.ApplicationAttribute.AA_EnableHighDpiScaling, True)
    if hasattr(Qt.ApplicationAttribute, "AA_UseHighDpiPixmaps"):
        QApplication.setAttribute(Qt.ApplicationAttribute.AA_UseHighDpiPixmaps, True)

    app = QApplication(sys.argv)
    app.setApplicationName("Job Finder AI")
    app.setOrganizationName("JobFinderAI")

    window = MainWindow()
    window.show()

    logger.info("PyQt6 application loop started.")
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
