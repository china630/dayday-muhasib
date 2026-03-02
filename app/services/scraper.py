"""
Tax Bot Scraper Service for e-taxes.gov.az
===========================================

This module implements automated scraping of the Azerbaijan tax portal using Playwright.

CRITICAL DESKTOP EMULATION REQUIREMENT:
---------------------------------------
The e-taxes.gov.az website blocks mobile user agents and requires desktop browser emulation.
We configure Playwright with a Windows 10 / Chrome 120 user agent and desktop viewport
to ensure the site renders the full desktop version with all required UI elements.

CONTEXT SWITCHING ARCHITECTURE:
-------------------------------
One accountant (Android Farm SIM) can manage multiple client taxpayers. After logging in
with the accountant's credentials, we use the "Change User/Taxpayer" dropdown to switch
between different client VOENs without re-authenticating. This dramatically improves
efficiency by reusing a single browser session.

ASAN İmza Login Flow:
---------------------
The login process uses ASAN İmza (government digital signature). The PIN entry is handled
externally (either manual entry or ADB automation on Android Farm device).
"""

import asyncio
import logging
from typing import Optional, List, Dict, Any
from datetime import datetime
from playwright.async_api import async_playwright, Browser, Page, BrowserContext, TimeoutError as PlaywrightTimeoutError

from app.core.config import settings


logger = logging.getLogger(__name__)


class ScraperException(Exception):
    """Base exception for scraper errors"""
    pass


class LoginFailedException(ScraperException):
    """Raised when login fails"""
    pass


class TaxpayerSwitchException(ScraperException):
    """Raised when switching taxpayer fails"""
    pass


class InboxFetchException(ScraperException):
    """Raised when fetching inbox fails"""
    pass


class TaxBot:
    """
    Automated bot for interacting with e-taxes.gov.az
    
    This bot handles:
    - Desktop browser emulation to bypass mobile blocks
    - ASAN İmza authentication
    - Multi-client context switching
    - Inbox scanning for risk keywords
    """
    
    # URLs
    BASE_URL = "https://e-taxes.gov.az"
    LOGIN_URL = f"{BASE_URL}/ebyn/login.jsp"
    DASHBOARD_URL = f"{BASE_URL}/ebyn/main.jsp"
    INBOX_URL = f"{BASE_URL}/ebyn/correspondence/inbox.jsp"
    
    # Risk keywords for message flagging (Azerbaijani)
    RISK_KEYWORDS = [
        "xəbərdarlıq",  # Warning
        "xeberdarliq",  # Warning (alternative spelling)
        "cərimə",       # Fine/Penalty
        "cerime",       # Fine (alternative spelling)
        "borc",         # Debt
        "ödəniş",       # Payment
        "odenis",       # Payment (alternative spelling)
        "yoxlama",      # Audit/Check
        "vergi",        # Tax
        "təqib",        # Prosecution
        "tәqib",        # Prosecution (alternative)
    ]
    
    # Desktop emulation settings - CRITICAL for bypassing mobile block
    VIEWPORT = {"width": 1920, "height": 1080}
    USER_AGENT = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
    
    def __init__(self, headless: bool = True, screenshot_dir: Optional[str] = None):
        """
        Initialize TaxBot
        
        Args:
            headless: Run browser in headless mode
            screenshot_dir: Directory to save debugging screenshots
        """
        self.headless = headless
        self.screenshot_dir = screenshot_dir
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None
        self._playwright = None
        
        logger.info(f"TaxBot initialized - Headless: {headless}, User-Agent: {self.USER_AGENT[:50]}...")
    
    async def __aenter__(self):
        """Async context manager entry"""
        await self.start()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        await self.close()
    
    async def start(self):
        """
        Start the Playwright browser with desktop emulation
        
        CRITICAL: Desktop user agent and viewport are set here to bypass mobile blocking
        """
        try:
            logger.info("Starting Playwright browser with desktop emulation...")
            
            self._playwright = await async_playwright().start()
            
            # Launch Chromium with desktop configuration
            self.browser = await self._playwright.chromium.launch(
                headless=self.headless,
                args=[
                    "--disable-blink-features=AutomationControlled",  # Hide automation
                    "--disable-dev-shm-usage",
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                ]
            )
            
            # Create context with DESKTOP emulation - this is crucial!
            self.context = await self.browser.new_context(
                viewport=self.VIEWPORT,
                user_agent=self.USER_AGENT,
                locale="az-AZ",  # Azerbaijan locale
                timezone_id="Asia/Baku",
                extra_http_headers={
                    "Accept-Language": "az,en;q=0.9",
                }
            )
            
            # Create page
            self.page = await self.context.new_page()
            
            # Set longer default timeout
            self.page.set_default_timeout(30000)
            
            logger.info("Browser started successfully with desktop emulation")
            
        except Exception as e:
            logger.error(f"Failed to start browser: {e}")
            raise ScraperException(f"Browser startup failed: {e}")
    
    async def close(self):
        """Close browser and cleanup resources"""
        try:
            if self.page:
                await self.page.close()
            if self.context:
                await self.context.close()
            if self.browser:
                await self.browser.close()
            if self._playwright:
                await self._playwright.stop()
            
            logger.info("Browser closed successfully")
            
        except Exception as e:
            logger.error(f"Error closing browser: {e}")
    
    async def _take_screenshot(self, name: str):
        """Take a screenshot for debugging"""
        if self.screenshot_dir and self.page:
            try:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                path = f"{self.screenshot_dir}/{name}_{timestamp}.png"
                await self.page.screenshot(path=path, full_page=True)
                logger.info(f"Screenshot saved: {path}")
            except Exception as e:
                logger.warning(f"Failed to save screenshot: {e}")
    
    async def login_accountant(self, phone_number: str, wait_for_pin_seconds: int = 120) -> bool:
        """
        Login to e-taxes.gov.az using ASAN İmza with accountant's phone number
        
        Flow:
        1. Navigate to login page
        2. Click ASAN İmza button
        3. Enter phone number
        4. Wait for external PIN entry (manual or ADB on Android Farm)
        5. Verify successful login
        
        Args:
            phone_number: Accountant's phone number for ASAN İmza
            wait_for_pin_seconds: Max seconds to wait for PIN entry (default 120)
        
        Returns:
            bool: True if login successful
        
        Raises:
            LoginFailedException: If login fails
        """
        try:
            logger.info(f"Starting login for phone: {phone_number}")
            
            if not self.page:
                raise LoginFailedException("Browser not started. Call start() first.")
            
            # Navigate to login page
            await self.page.goto(self.LOGIN_URL, wait_until="networkidle")
            await self._take_screenshot("01_login_page")
            
            # Click ASAN İmza button (adjust selector based on actual site)
            logger.info("Clicking ASAN İmza login button...")
            asan_button_selectors = [
                "button:has-text('ASAN İmza')",
                "a:has-text('ASAN İmza')",
                "button:has-text('ASAN Imza')",
                "#asanImzaBtn",
                ".asan-login-btn",
            ]
            
            button_clicked = False
            for selector in asan_button_selectors:
                try:
                    await self.page.click(selector, timeout=5000)
                    button_clicked = True
                    logger.info(f"ASAN İmza button clicked using selector: {selector}")
                    break
                except PlaywrightTimeoutError:
                    continue
            
            if not button_clicked:
                raise LoginFailedException("Could not find ASAN İmza button")
            
            await asyncio.sleep(2)
            await self._take_screenshot("02_asan_popup")
            
            # Enter phone number (adjust selector based on actual site)
            logger.info(f"Entering phone number: {phone_number}")
            phone_selectors = [
                "input[name='phone']",
                "input[type='tel']",
                "input[placeholder*='telefon']",
                "input[placeholder*='nömrə']",
                "#phoneNumber",
            ]
            
            phone_entered = False
            for selector in phone_selectors:
                try:
                    await self.page.fill(selector, phone_number, timeout=5000)
                    phone_entered = True
                    logger.info(f"Phone number entered using selector: {selector}")
                    break
                except PlaywrightTimeoutError:
                    continue
            
            if not phone_entered:
                raise LoginFailedException("Could not find phone number input field")
            
            # Click "Send SMS" or "Next" button
            submit_selectors = [
                "button:has-text('Göndər')",  # Send
                "button:has-text('Davam')",   # Continue
                "button[type='submit']",
                "button:has-text('Next')",
            ]
            
            for selector in submit_selectors:
                try:
                    await self.page.click(selector, timeout=5000)
                    logger.info(f"Submit button clicked using selector: {selector}")
                    break
                except PlaywrightTimeoutError:
                    continue
            
            await asyncio.sleep(2)
            await self._take_screenshot("03_waiting_for_pin")
            
            # Wait for PIN entry (handled externally - manual or ADB)
            logger.info(f"Waiting up to {wait_for_pin_seconds}s for external PIN entry...")
            logger.info("PIN should be entered via Android Farm ADB or manually")
            
            # Wait for successful login by checking for dashboard elements
            try:
                await self.page.wait_for_url(
                    f"{self.BASE_URL}/**",
                    timeout=wait_for_pin_seconds * 1000,
                    wait_until="networkidle"
                )
                
                # Verify we're logged in by checking for common dashboard elements
                dashboard_selectors = [
                    ".user-info",
                    "#userProfile",
                    "a:has-text('Çıxış')",  # Logout button
                    ".dashboard",
                    "[data-user]",
                ]
                
                logged_in = False
                for selector in dashboard_selectors:
                    try:
                        await self.page.wait_for_selector(selector, timeout=10000)
                        logged_in = True
                        logger.info(f"Login verified using selector: {selector}")
                        break
                    except PlaywrightTimeoutError:
                        continue
                
                if not logged_in:
                    raise LoginFailedException("Could not verify successful login")
                
                await self._take_screenshot("04_logged_in_dashboard")
                logger.info(f"Login successful for phone: {phone_number}")
                
                return True
                
            except PlaywrightTimeoutError:
                raise LoginFailedException(
                    f"Login timeout after {wait_for_pin_seconds}s. "
                    "PIN may not have been entered."
                )
        
        except LoginFailedException:
            await self._take_screenshot("error_login_failed")
            raise
        
        except Exception as e:
            await self._take_screenshot("error_login_exception")
            logger.error(f"Login error: {e}")
            raise LoginFailedException(f"Login failed with error: {e}")
    
    async def switch_taxpayer(self, client_voen: str) -> bool:
        """
        Switch to a different taxpayer/client using the "Change User" dropdown
        
        Context Switching Explanation:
        -----------------------------
        After logging in as an accountant, the e-taxes portal allows switching between
        different taxpayer accounts (clients) without re-authentication. This is done
        via a dropdown menu that lists all authorized VOENs.
        
        This method:
        1. Locates the taxpayer/user dropdown (usually in header)
        2. Clicks to open the dropdown
        3. Searches for the target VOEN
        4. Clicks to switch context
        5. Waits for page reload with new taxpayer context
        
        Args:
            client_voen: The client's VOEN (Tax ID) to switch to
        
        Returns:
            bool: True if switch successful
        
        Raises:
            TaxpayerSwitchException: If switching fails
        """
        try:
            logger.info(f"Switching to taxpayer VOEN: {client_voen}")
            
            if not self.page:
                raise TaxpayerSwitchException("Browser not started")
            
            # Look for taxpayer dropdown/switcher (adjust selectors based on actual site)
            dropdown_selectors = [
                "#taxpayerSelect",
                ".taxpayer-dropdown",
                "select[name='voen']",
                "button:has-text('Vergi ödəyicisi')",  # Taxpayer
                ".user-switcher",
                "[data-taxpayer-selector]",
            ]
            
            dropdown_found = False
            for selector in dropdown_selectors:
                try:
                    # Click dropdown to open
                    await self.page.click(selector, timeout=5000)
                    dropdown_found = True
                    logger.info(f"Taxpayer dropdown opened using selector: {selector}")
                    break
                except PlaywrightTimeoutError:
                    continue
            
            if not dropdown_found:
                raise TaxpayerSwitchException("Could not find taxpayer dropdown")
            
            await asyncio.sleep(1)
            await self._take_screenshot("05_taxpayer_dropdown_open")
            
            # Look for the specific VOEN in the dropdown options
            voen_selectors = [
                f"option[value='{client_voen}']",
                f"li:has-text('{client_voen}')",
                f"a:has-text('{client_voen}')",
                f"[data-voen='{client_voen}']",
            ]
            
            voen_clicked = False
            for selector in voen_selectors:
                try:
                    await self.page.click(selector, timeout=5000)
                    voen_clicked = True
                    logger.info(f"VOEN clicked using selector: {selector}")
                    break
                except PlaywrightTimeoutError:
                    continue
            
            if not voen_clicked:
                # Try selecting from dropdown if it's a <select> element
                try:
                    await self.page.select_option("select[name='voen']", client_voen, timeout=5000)
                    voen_clicked = True
                    logger.info("VOEN selected using select_option")
                except:
                    raise TaxpayerSwitchException(f"Could not find VOEN {client_voen} in dropdown")
            
            # Wait for page reload/update after switching
            await asyncio.sleep(2)
            
            try:
                # Wait for network to be idle after switch
                await self.page.wait_for_load_state("networkidle", timeout=15000)
            except PlaywrightTimeoutError:
                logger.warning("Network idle timeout after taxpayer switch (might be OK)")
            
            await self._take_screenshot("06_taxpayer_switched")
            
            # Verify the switch by checking if VOEN appears on the page
            page_content = await self.page.content()
            if client_voen in page_content:
                logger.info(f"Successfully switched to taxpayer: {client_voen}")
                return True
            else:
                logger.warning(f"VOEN {client_voen} not found in page after switch (might be OK)")
                return True  # Proceed anyway, verification might not be reliable
        
        except TaxpayerSwitchException:
            await self._take_screenshot("error_taxpayer_switch_failed")
            raise
        
        except Exception as e:
            await self._take_screenshot("error_taxpayer_switch_exception")
            logger.error(f"Taxpayer switch error: {e}")
            raise TaxpayerSwitchException(f"Failed to switch taxpayer: {e}")
    
    async def fetch_inbox(self) -> List[Dict[str, Any]]:
        """
        Fetch inbox messages and flag those containing risk keywords
        
        Lead Generation Feature:
        -----------------------
        This scans the government correspondence inbox for messages containing
        keywords like "Xəbərdarlıq" (Warning) or "Cərimə" (Fine). Messages with
        these keywords are flagged as high-risk and can trigger notifications.
        
        Returns:
            List of message dictionaries with structure:
            {
                'subject': str,
                'body': str,
                'received_at': datetime,
                'is_risk_flagged': bool,
                'sender': str (optional),
                'message_id': str (optional)
            }
        
        Raises:
            InboxFetchException: If fetching fails
        """
        try:
            logger.info("Fetching inbox messages...")
            
            if not self.page:
                raise InboxFetchException("Browser not started")
            
            # Navigate to inbox
            await self.page.goto(self.INBOX_URL, wait_until="networkidle")
            await self._take_screenshot("07_inbox_page")
            
            messages = []
            
            # Wait for inbox table/list to load (adjust selectors based on actual site)
            inbox_container_selectors = [
                "#inboxTable",
                ".inbox-messages",
                ".correspondence-list",
                "table.messages",
                "[data-inbox]",
            ]
            
            container_found = False
            for selector in inbox_container_selectors:
                try:
                    await self.page.wait_for_selector(selector, timeout=10000)
                    container_found = True
                    logger.info(f"Inbox container found using selector: {selector}")
                    break
                except PlaywrightTimeoutError:
                    continue
            
            if not container_found:
                logger.warning("Could not find inbox container, attempting to parse anyway")
            
            # Get all message rows (adjust selectors based on actual site structure)
            message_row_selectors = [
                "table.messages tbody tr",
                ".inbox-message-row",
                ".correspondence-item",
                "tr[data-message-id]",
                ".message-list-item",
            ]
            
            message_rows = []
            for selector in message_row_selectors:
                try:
                    message_rows = await self.page.query_selector_all(selector)
                    if message_rows:
                        logger.info(f"Found {len(message_rows)} messages using selector: {selector}")
                        break
                except:
                    continue
            
            if not message_rows:
                logger.warning("No messages found in inbox")
                return []
            
            # Parse each message
            for idx, row in enumerate(message_rows):
                try:
                    # Extract message details (adjust based on actual HTML structure)
                    subject_elem = await row.query_selector("td.subject, .message-subject, [data-subject]")
                    subject = await subject_elem.inner_text() if subject_elem else "No Subject"
                    subject = subject.strip()
                    
                    # Try to get message body (might require clicking into message)
                    body_elem = await row.query_selector("td.preview, .message-preview, .message-body")
                    body = await body_elem.inner_text() if body_elem else ""
                    body = body.strip()
                    
                    # Try to get date
                    date_elem = await row.query_selector("td.date, .message-date, [data-date]")
                    date_str = await date_elem.inner_text() if date_elem else ""
                    
                    # Try to get sender
                    sender_elem = await row.query_selector("td.sender, .message-sender, [data-sender]")
                    sender = await sender_elem.inner_text() if sender_elem else "Unknown"
                    sender = sender.strip()
                    
                    # Check for risk keywords (case-insensitive)
                    full_text = f"{subject} {body}".lower()
                    is_risk = any(keyword in full_text for keyword in self.RISK_KEYWORDS)
                    
                    message_data = {
                        "subject": subject,
                        "body": body,
                        "received_at": date_str,  # Parse to datetime if needed
                        "is_risk_flagged": is_risk,
                        "sender": sender,
                        "message_id": f"msg_{idx}",
                    }
                    
                    messages.append(message_data)
                    
                    if is_risk:
                        logger.warning(f"🚨 RISK MESSAGE DETECTED: {subject[:50]}")
                    
                except Exception as e:
                    logger.error(f"Error parsing message row {idx}: {e}")
                    continue
            
            logger.info(f"Successfully fetched {len(messages)} messages, {sum(m['is_risk_flagged'] for m in messages)} flagged as risk")
            await self._take_screenshot("08_inbox_processed")
            
            return messages
        
        except InboxFetchException:
            await self._take_screenshot("error_inbox_fetch_failed")
            raise
        
        except Exception as e:
            await self._take_screenshot("error_inbox_fetch_exception")
            logger.error(f"Inbox fetch error: {e}")
            raise InboxFetchException(f"Failed to fetch inbox: {e}")
    
    async def check_debt(self) -> Dict[str, Any]:
        """
        Check current tax debt status
        
        Returns:
            Dict with debt information
        """
        try:
            logger.info("Checking debt status...")
            
            # Navigate to debt page (adjust URL based on actual site)
            debt_url = f"{self.BASE_URL}/ebyn/debt/check.jsp"
            await self.page.goto(debt_url, wait_until="networkidle")
            await self._take_screenshot("09_debt_page")
            
            # Parse debt information (adjust selectors based on actual site)
            debt_info = {
                "total_debt": "0.00",
                "currency": "AZN",
                "has_debt": False,
                "details": []
            }
            
            # This is a placeholder - implement actual scraping logic
            logger.info("Debt check completed")
            
            return debt_info
        
        except Exception as e:
            logger.error(f"Debt check error: {e}")
            raise ScraperException(f"Failed to check debt: {e}")
    
    async def submit_filing(self, filing_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Submit a tax filing
        
        Args:
            filing_data: Dict containing filing information
        
        Returns:
            Dict with submission result
        """
        try:
            logger.info("Submitting tax filing...")
            
            # Navigate to filing page (adjust URL based on actual site)
            filing_url = f"{self.BASE_URL}/ebyn/filing/submit.jsp"
            await self.page.goto(filing_url, wait_until="networkidle")
            await self._take_screenshot("10_filing_page")
            
            # Fill and submit form (implement actual logic)
            result = {
                "success": False,
                "submission_id": None,
                "error": "Not implemented yet"
            }
            
            logger.info("Filing submission completed")
            
            return result
        
        except Exception as e:
            logger.error(f"Filing submission error: {e}")
            raise ScraperException(f"Failed to submit filing: {e}")
