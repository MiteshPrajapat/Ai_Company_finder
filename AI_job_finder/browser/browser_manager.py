"""
Browser lifecycle and automation manager using Selenium WebDriver.
Ensures stable navigation, safe timeouts, and clean resource cleanup.
"""

import time
import threading
from typing import Optional
from selenium import webdriver
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.common.exceptions import TimeoutException, WebDriverException
from config.settings import settings
from utils.logger import get_logger

logger = get_logger("browser_manager")


class BrowserManager:
    """Manages browser creation, navigation, and cleanup."""

    def __init__(self, headless: Optional[bool] = None, timeout: Optional[int] = None):
        cfg = settings.get_config()
        self.headless = headless if headless is not None else cfg.headless
        self.timeout = timeout or cfg.page_timeout
        self.driver: Optional[webdriver.Chrome] = None
        self._lock = threading.Lock()

    def get_driver(self) -> webdriver.Chrome:
        """Initializes or returns active WebDriver instance."""
        with self._lock:
            if self.driver is None:
                self.driver = self._create_driver()
            return self.driver

    def _create_driver(self) -> webdriver.Chrome:
        """Configures and starts a new Chrome WebDriver."""
        logger.info(f"Initializing Chrome WebDriver (headless={self.headless})...")
        options = ChromeOptions()
        if self.headless:
            options.add_argument("--headless=new")

        # Standard stability flags
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-gpu")
        options.add_argument("--window-size=1920,1080")
        options.add_argument("--disable-notifications")
        options.add_argument("--disable-popup-blocking")
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_argument(f"--user-agent={settings.get_config().user_agent}")

        # Reduce logging noise from Chrome
        options.add_experimental_option("excludeSwitches", ["enable-automation", "enable-logging"])
        options.add_experimental_option("useAutomationExtension", False)

        try:
            driver = webdriver.Chrome(options=options)
            driver.set_page_load_timeout(self.timeout)
            driver.set_script_timeout(self.timeout)
            logger.info("Chrome WebDriver initialized successfully.")
            return driver
        except Exception as e:
            logger.error(f"Failed to launch Chrome WebDriver: {e}", exc_info=True)
            raise

    def navigate(self, url: str, wait_seconds: float = 1.5) -> Optional[str]:
        """
        Safely navigates to a URL with timeout protection.
        Returns the HTML content of the page or None if failed.
        """
        driver = self.get_driver()
        try:
            logger.debug(f"Navigating to: {url}")
            driver.get(url)
            if wait_seconds > 0:
                time.sleep(wait_seconds)
            return driver.page_source
        except TimeoutException:
            logger.warning(f"Timeout while loading URL: {url}")
            try:
                # Still try to grab whatever content loaded
                return driver.page_source
            except Exception:
                return None
        except WebDriverException as e:
            logger.warning(f"WebDriver navigation error for {url}: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error loading {url}: {e}")
            return None

    def execute_script(self, script: str, *args):
        """Executes JavaScript inside the active page."""
        try:
            driver = self.get_driver()
            return driver.execute_script(script, *args)
        except Exception as e:
            logger.warning(f"Script execution error: {e}")
            return None

    def get_current_url(self) -> Optional[str]:
        """Returns the current browser URL."""
        try:
            if self.driver:
                return self.driver.current_url
        except Exception:
            pass
        return None

    def take_screenshot(self, filepath: str) -> bool:
        """Saves a screenshot of the current page."""
        try:
            if self.driver:
                return self.driver.save_screenshot(filepath)
        except Exception as e:
            logger.warning(f"Screenshot failed: {e}")
        return False

    def close(self):
        """Safely closes the browser instance and releases resources."""
        with self._lock:
            if self.driver:
                try:
                    logger.info("Closing Chrome WebDriver...")
                    self.driver.quit()
                except Exception as e:
                    logger.warning(f"Error during browser quit: {e}")
                finally:
                    self.driver = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
