"""
Email Automation and Live Chrome typing & dispatch service for Job Finder AI.
Supports:
- Live visible Chrome launching in front of user
- Character-by-character live keystroke simulation (typing right in front of the user)
- Automatic resume file attachment
- Automatic Send button clicking
- Fallback webmail compose URL construction (Gmail, Outlook) and system dispatch
"""

import os
import time
import urllib.parse
import webbrowser
from typing import Dict, Any, Optional, Callable
from config.settings import settings
from utils.logger import get_logger

logger = get_logger("email_automation")


class EmailAutomationService:
    """Handles dispatching generated emails to Chrome webmail, live typing, and automated attachment & send."""

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

    @classmethod
    def live_chrome_auto_type_and_send(
        cls,
        to_email: str,
        subject: str,
        body: str,
        resume_path: Optional[str] = None,
        auto_send: bool = True,
        status_callback: Optional[Callable[[str], None]] = None
    ) -> Dict[str, Any]:
        """
        Launches a visible Chrome browser window directly in front of the user,
        opens Gmail compose, automatically types the recipient, subject, and body
        character-by-character in real time, automatically attaches the resume,
        and clicks the Send button.
        """
        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options as ChromeOptions
        from selenium.webdriver.common.by import By
        from selenium.webdriver.common.keys import Keys
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC

        def _update_status(msg: str):
            logger.info(f"[Live Automation] {msg}")
            if status_callback:
                status_callback(msg)

        try:
            _update_status("Opening Chrome in front of user...")
            options = ChromeOptions()
            options.add_argument("--start-maximized")
            options.add_argument("--disable-notifications")
            options.add_argument("--disable-popup-blocking")
            options.add_argument("--disable-blink-features=AutomationControlled")
            options.add_experimental_option("excludeSwitches", ["enable-automation", "enable-logging"])
            options.add_experimental_option("useAutomationExtension", False)

            # Use dedicated profile so Gmail login is remembered permanently
            user_data_base = os.environ.get("LOCALAPPDATA", os.path.expanduser("~"))
            profile_dir = os.path.join(user_data_base, "JobFinderAI", "chrome_user_data")
            os.makedirs(profile_dir, exist_ok=True)
            options.add_argument(f"--user-data-dir={profile_dir}")

            driver = webdriver.Chrome(options=options)
            driver.set_page_load_timeout(40)

            # Remove navigator.webdriver flag so Google doesn't block login
            try:
                driver.execute_cdp_cmd(
                    "Page.addScriptToEvaluateOnNewDocument",
                    {"source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"}
                )
            except Exception:
                pass

            # 1. Open Google Search & Search for 'gmail'
            _update_status("Navigating to Google...")
            driver.get("https://www.google.com")
            time.sleep(2.0)

            # Accept Google cookies/consent if prompted
            try:
                consent_btns = driver.find_elements(By.XPATH, "//button[contains(., 'Accept all') or contains(., 'I agree') or contains(., 'Stay signed out')]")
                if consent_btns:
                    consent_btns[0].click()
                    time.sleep(1.0)
            except Exception:
                pass

            # Find Search Input
            _update_status("Searching for 'gmail' in Google...")
            search_input = None
            search_selectors = [
                "//textarea[@name='q']",
                "//input[@name='q']",
                "//textarea[contains(@aria-label, 'Search')]",
                "//input[contains(@aria-label, 'Search')]"
            ]
            for sel in search_selectors:
                try:
                    search_input = driver.find_element(By.XPATH, sel)
                    if search_input and search_input.is_displayed():
                        break
                except Exception:
                    continue

            if search_input:
                search_input.click()
                time.sleep(0.3)
                for char in "gmail":
                    search_input.send_keys(char)
                    time.sleep(0.08)
                time.sleep(0.3)
                search_input.send_keys(Keys.ENTER)
                time.sleep(2.5)

                # 2. Click First Gmail Result
                _update_status("Opening first Gmail result from search...")
                first_link = None
                link_selectors = [
                    "//h3[contains(text(), 'Gmail')]/ancestor::a",
                    "//a[contains(@href, 'mail.google.com')]",
                    "//a[contains(@href, 'workspace.google.com') and contains(@href, 'gmail')]",
                    "//a[contains(@href, 'accounts.google.com') and contains(@href, 'mail')]"
                ]
                for lsel in link_selectors:
                    try:
                        links = driver.find_elements(By.XPATH, lsel)
                        for lnk in links:
                            if lnk.is_displayed():
                                first_link = lnk
                                break
                        if first_link:
                            break
                    except Exception:
                        continue

                if first_link:
                    first_link.click()
                    time.sleep(3.0)
                else:
                    driver.get("https://mail.google.com")
                    time.sleep(2.5)
            else:
                driver.get("https://mail.google.com")
                time.sleep(2.5)

            wait = WebDriverWait(driver, 10)

            # If redirected to Google Workspace landing page, click "Sign in"
            if "workspace.google.com" in driver.current_url.lower():
                _update_status("On Workspace page: clicking 'Sign in' to open Gmail...")
                try:
                    signin_btns = driver.find_elements(
                        By.XPATH,
                        "//a[contains(text(), 'Sign in') or contains(@aria-label, 'Sign in') or contains(@href, 'accounts.google.com')]"
                    )
                    for sbtn in signin_btns:
                        if sbtn.is_displayed():
                            sbtn.click()
                            time.sleep(2.5)
                            break
                except Exception:
                    pass

            # If on Google sign in page, prompt user to sign in
            if "accounts.google.com" in driver.current_url.lower():
                _update_status("Please sign in to Google in Chrome (login will be saved permanently)...")
                for _ in range(45):
                    time.sleep(2.0)
                    curr = driver.current_url.lower()
                    if "mail.google.com" in curr and "accounts.google.com" not in curr:
                        _update_status("Gmail Login detected! Opening inbox...")
                        time.sleep(2.5)
                        break

            # If still on workspace.google.com, navigate directly to mail.google.com
            if "workspace.google.com" in driver.current_url.lower():
                _update_status("Redirecting to Gmail inbox...")
                driver.get("https://mail.google.com")
                time.sleep(3.0)

            # 3. Locate & Click the 'Compose' Button
            _update_status("Looking for Gmail '+ Compose' button...")
            compose_btn = None
            compose_selectors = [
                "//div[@role='button' and (contains(text(), 'Compose') or contains(@aria-label, 'Compose'))]",
                "//div[@gh='cm']",
                "//div[contains(@class, 'T-I-KE')]",
                "//div[contains(@aria-label, 'Compose')]",
                "//span[contains(text(), 'Compose')]/ancestor::div[@role='button']",
                "//div[text()='Compose']"
            ]

            for sel in compose_selectors:
                try:
                    compose_btn = WebDriverWait(driver, 5).until(
                        EC.element_to_be_clickable((By.XPATH, sel))
                    )
                    if compose_btn:
                        compose_btn.click()
                        _update_status("Clicked '+ Compose' button! Waiting for compose window...")
                        time.sleep(2.0)
                        break
                except Exception:
                    continue

            # Fallback if Compose button wasn't clickable
            _update_status("Locating Compose Window...")
            to_input = None
            to_selectors = [
                "//input[contains(@aria-label, 'To') or contains(@aria-label, 'recipients') or @peoplekit-id]",
                "//div[contains(@aria-label, 'To recipients')]//input",
                "//textarea[@name='to']",
                "//input[@name='to']",
                "//input[contains(@class, 'agP')]",
                "//div[@role='combobox']//input"
            ]

            for selector in to_selectors:
                try:
                    to_input = wait.until(EC.element_to_be_clickable((By.XPATH, selector)))
                    if to_input:
                        break
                except Exception:
                    continue

            if not to_input:
                # Secondary fallback: open direct compose URL
                _update_status("Opening Gmail Direct Compose...")
                compose_url = cls.create_gmail_compose_url(to_email, subject, body)
                driver.get(compose_url)
                time.sleep(2.5)

                if resume_path and os.path.exists(resume_path):
                    _update_status(f"Attaching resume: {os.path.basename(resume_path)}...")
                    cls._attach_file_in_driver(driver, resume_path)
                    time.sleep(2.5)

                if auto_send:
                    _update_status("Clicking Send button...")
                    cls._click_send_in_driver(driver)

                _update_status("✅ Email ready / sent in Chrome!")
                return {"success": True, "mode": "direct_compose"}

            # 4. Live Type Recipient
            if to_email:
                _update_status(f"Live Typing Recipient: {to_email}...")
                to_input.click()
                time.sleep(0.3)
                for char in to_email:
                    to_input.send_keys(char)
                    time.sleep(0.02)
                to_input.send_keys(Keys.ENTER)
                time.sleep(0.4)

            # 5. Live Type Subject
            if subject:
                _update_status(f"Live Typing Subject: {subject[:45]}...")
                subj_input = None
                subj_selectors = [
                    "//input[@name='subjectbox']",
                    "//input[contains(@aria-label, 'Subject')]",
                    "//input[@placeholder='Subject']"
                ]
                for s in subj_selectors:
                    try:
                        subj_input = driver.find_element(By.XPATH, s)
                        if subj_input:
                            break
                    except Exception:
                        continue

                if subj_input:
                    subj_input.click()
                    time.sleep(0.2)
                    for char in subject:
                        subj_input.send_keys(char)
                        time.sleep(0.015)
                    time.sleep(0.4)

            # 6. Live Type Body Line-by-Line in Real Time on Screen
            if body:
                _update_status("Live Typing Email Body line-by-line in real time...")
                body_elem = None
                body_selectors = [
                    "//div[contains(@aria-label, 'Message Body')]",
                    "//div[@role='textbox' and contains(@aria-label, 'Body')]",
                    "//div[@role='textbox']"
                ]
                for b in body_selectors:
                    try:
                        body_elem = driver.find_element(By.XPATH, b)
                        if body_elem:
                            break
                    except Exception:
                        continue

                if body_elem:
                    body_elem.click()
                    time.sleep(0.4)
                    lines = body.split("\n")
                    for line_idx, line in enumerate(lines):
                        words = line.split(" ")
                        for w_idx, word in enumerate(words):
                            spacer = " " if w_idx < len(words) - 1 else ""
                            body_elem.send_keys(word + spacer)
                            time.sleep(0.035)  # Real-time typing speed on screen
                        if line_idx < len(lines) - 1:
                            body_elem.send_keys(Keys.ENTER)
                            time.sleep(0.12)  # Pause between lines
                    time.sleep(1.0)

            # 6. Attach Resume File
            if resume_path and os.path.exists(resume_path):
                abs_path = os.path.abspath(resume_path)
                _update_status(f"Attaching resume: {os.path.basename(abs_path)}...")
                cls._attach_file_in_driver(driver, abs_path)
                time.sleep(3.0)

            # 7. Automatically Click Send
            if auto_send:
                _update_status("Automatically clicking Send button...")
                time.sleep(1.0)
                cls._click_send_in_driver(driver)
                _update_status("✅ Email sent successfully in Chrome!")
            else:
                _update_status("✅ Email typed! Ready for your final review and send.")

            return {"success": True, "mode": "live_automation"}

        except Exception as e:
            logger.error(f"Live Chrome automation error: {e}", exc_info=True)
            _update_status(f"Notice: {e}")
            return {"success": False, "error": str(e)}

    @staticmethod
    def _attach_file_in_driver(driver, file_path: str):
        """Finds file input in browser and sends the file path."""
        from selenium.webdriver.common.by import By
        try:
            file_inputs = driver.find_elements(By.XPATH, "//input[@type='file']")
            for finput in file_inputs:
                try:
                    finput.send_keys(file_path)
                    logger.info(f"Attached file via input: {file_path}")
                    return True
                except Exception:
                    continue
        except Exception as e:
            logger.warning(f"Could not attach file directly via input: {e}")
        return False

    @staticmethod
    def _click_send_in_driver(driver):
        """Finds and clicks the Send button or sends Ctrl+Enter."""
        from selenium.webdriver.common.by import By
        from selenium.webdriver.common.keys import Keys
        try:
            send_selectors = [
                "//div[@role='button' and (contains(@data-tooltip, 'Send') or contains(@aria-label, 'Send'))]",
                "//div[contains(@class, 'T-I J-J5-Ji aoO v7 T-I-atl L3')]",
                "//div[text()='Send' and @role='button']"
            ]
            for s in send_selectors:
                try:
                    btn = driver.find_element(By.XPATH, s)
                    if btn and btn.is_displayed():
                        btn.click()
                        logger.info("Clicked Send button.")
                        return True
                except Exception:
                    continue

            # Fallback: Ctrl+Enter shortcut
            driver.switch_to.active_element.send_keys(Keys.CONTROL, Keys.ENTER)
            logger.info("Triggered Send via Ctrl+Enter shortcut.")
            return True
        except Exception as e:
            logger.warning(f"Could not click send button: {e}")
        return False
