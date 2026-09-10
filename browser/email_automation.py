"""
Email Automation and Chrome dispatch service for Job Finder AI.
Supports visible Chrome launching, webmail compose URL construction (Gmail, Outlook), and system dispatch.
"""

import urllib.parse
import webbrowser
from typing import Dict, Any, Optional
from config.settings import settings
from utils.logger import get_logger

logger = get_logger("email_automation")


class EmailAutomationService:
    """Handles dispatching generated emails to Chrome webmail or system email client."""

    @staticmethod
    def create_gmail_compose_url(to_email: str, subject: str, body: str) -> str:
        """Constructs a Gmail web compose URL with prefilled recipient, subject, and body."""
        params = {
            "view": "cm",
            "fs": "1",
            "to": to_email,
            "su": subject,
            "body": body
        }
        query_string = urllib.parse.urlencode(params, quote_via=urllib.parse.quote)
        return f"https://mail.google.com/mail/?{query_string}"

    @staticmethod
    def create_outlook_compose_url(to_email: str, subject: str, body: str) -> str:
        """Constructs an Outlook web compose URL."""
        params = {
            "to": to_email,
            "subject": subject,
            "body": body
        }
        query_string = urllib.parse.urlencode(params, quote_via=urllib.parse.quote)
        return f"https://outlook.live.com/mail/0/deeplink/compose?{query_string}"

    @staticmethod
    def create_mailto_url(to_email: str, subject: str, body: str) -> str:
        """Constructs a standard mailto: URI."""
        params = {
            "subject": subject,
            "body": body
        }
        query_string = urllib.parse.urlencode(params, quote_via=urllib.parse.quote)
        return f"mailto:{to_email}?{query_string}"

    @classmethod
    def open_in_chrome_webmail(
        cls,
        to_email: str,
        subject: str,
        body: str,
        provider: str = "gmail",
        use_selenium: bool = False
    ) -> Dict[str, Any]:
        """
        Opens Chrome with prefilled email composition.
        """
        try:
            if provider.lower() == "outlook":
                compose_url = cls.create_outlook_compose_url(to_email, subject, body)
            else:
                compose_url = cls.create_gmail_compose_url(to_email, subject, body)

            logger.info(f"Opening compose URL in browser: {provider}")

            if use_selenium:
                from browser.browser_manager import BrowserManager
                # Launch non-headless browser
                bm = BrowserManager(headless=False)
                driver = bm.get_driver()
                driver.get(compose_url)
                return {"success": True, "url": compose_url, "mode": "selenium"}
            else:
                # Launch system default Chrome / browser
                opened = webbrowser.open(compose_url)
                return {"success": opened, "url": compose_url, "mode": "webbrowser"}

        except Exception as e:
            logger.error(f"Failed to open email in Chrome: {e}", exc_info=True)
            return {"success": False, "error": str(e)}
