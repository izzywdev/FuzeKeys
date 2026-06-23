"""
Google signup automation service.
"""

import asyncio
import logging
import time
from typing import Optional, Dict, Any
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.common.exceptions import TimeoutException, ElementNotInteractableException
from selenium.webdriver.common.keys import Keys
from webdriver_manager.chrome import ChromeDriverManager

from .models import GoogleSignupData, GoogleSignupResult, GoogleSignupConfig
from app.models.identity import Identity
from app.utils.encryption import decrypt_field

logger = logging.getLogger(__name__)


class GoogleSignupService:
    """Service for automating Google account signup."""
    
    def __init__(self, config: GoogleSignupConfig = None):
        self.config = config or GoogleSignupConfig()
        self.driver: Optional[webdriver.Chrome] = None
        
    def _setup_driver(self) -> webdriver.Chrome:
        """Setup Chrome driver with appropriate options."""
        chrome_options = Options()
        
        if self.config.headless:
            chrome_options.add_argument("--headless")
        
        # Standard Chrome options for automation
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-blink-features=AutomationControlled")
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        chrome_options.add_experimental_option('useAutomationExtension', False)
        
        # User agent
        if self.config.use_mobile_user_agent:
            chrome_options.add_argument("--user-agent=Mozilla/5.0 (iPhone; CPU iPhone OS 14_6 like Mac OS X) AppleWebKit/605.1.15")
        elif self.config.custom_user_agent:
            chrome_options.add_argument(f"--user-agent={self.config.custom_user_agent}")
        else:
            chrome_options.add_argument("--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36")
        
        # Proxy configuration
        if self.config.use_proxy and self.config.proxy_config:
            proxy_host = self.config.proxy_config.get('host')
            proxy_port = self.config.proxy_config.get('port')
            if proxy_host and proxy_port:
                chrome_options.add_argument(f"--proxy-server=http://{proxy_host}:{proxy_port}")
        
        # Use webdriver-manager to handle Chrome driver installation
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=chrome_options)
        driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        
        return driver
    
    def _wait_and_find_element(self, by: By, value: str, timeout: int = 10):
        """Wait for element and return it."""
        return WebDriverWait(self.driver, timeout).until(
            EC.presence_of_element_located((by, value))
        )
    
    def _wait_and_click(self, by: By, value: str, timeout: int = 10):
        """Wait for element to be clickable and click it."""
        element = WebDriverWait(self.driver, timeout).until(
            EC.element_to_be_clickable((by, value))
        )
        element.click()
        return element
    
    def _type_with_delay(self, element, text: str, delay: float = 0.1):
        """Type text with human-like delay."""
        for char in text:
            element.send_keys(char)
            time.sleep(delay)
    
    async def signup_with_identity(self, identity: Identity) -> GoogleSignupResult:
        """Create Google account using identity data."""
        try:
            # Convert identity to GoogleSignupData
            signup_data = await self._identity_to_signup_data(identity)
            return await self.signup(signup_data)
        except Exception as e:
            logger.error(f"Error during Google signup with identity {identity.id}: {str(e)}")
            return GoogleSignupResult(
                success=False,
                error_message=f"Identity conversion error: {str(e)}"
            )
    
    async def _identity_to_signup_data(self, identity: Identity) -> GoogleSignupData:
        """Convert Identity model to GoogleSignupData."""
        # Decrypt fields
        first_name = decrypt_field(identity.encrypted_first_name) if identity.encrypted_first_name else None
        last_name = decrypt_field(identity.encrypted_last_name) if identity.encrypted_last_name else None
        email = decrypt_field(identity.encrypted_email) if identity.encrypted_email else None
        phone = decrypt_field(identity.encrypted_phone) if identity.encrypted_phone else None
        dob = decrypt_field(identity.encrypted_date_of_birth) if identity.encrypted_date_of_birth else None
        
        # Validate required fields
        if not first_name or not last_name:
            raise ValueError("First name and last name are required for Google signup")
        
        # Generate username from identity pattern or email
        username = self._generate_username(first_name, last_name, email, identity.preferred_username_pattern)
        
        # Generate password based on preferences
        password = self._generate_password(identity.password_preferences or {})
        
        # Parse date of birth
        birth_date = None
        if dob:
            try:
                from datetime import datetime
                birth_date = datetime.strptime(dob, "%Y-%m-%d").date()
            except ValueError:
                logger.warning(f"Could not parse date of birth: {dob}")
        
        return GoogleSignupData(
            first_name=first_name,
            last_name=last_name,
            username=username,
            password=password,
            phone_number=phone,
            recovery_email=email,
            birth_date=birth_date
        )
    
    def _generate_username(self, first_name: str, last_name: str, email: Optional[str], pattern: Optional[str]) -> str:
        """Generate username based on pattern or default logic."""
        import random
        import string
        
        if pattern:
            # Simple pattern replacement
            username = pattern.replace("{first}", first_name.lower())
            username = username.replace("{last}", last_name.lower())
            username = username.replace("{random}", ''.join(random.choices(string.digits, k=4)))
        elif email:
            # Use email prefix if available
            username = email.split('@')[0]
        else:
            # Default pattern: firstlast + random numbers
            username = f"{first_name.lower()}{last_name.lower()}{random.randint(1000, 9999)}"
        
        # Ensure it meets Google requirements
        username = username.replace(' ', '').replace('-', '')[:30]
        return username
    
    def _generate_password(self, preferences: Dict[str, Any]) -> str:
        """Generate password based on preferences."""
        import random
        import string
        
        length = preferences.get('length', 12)
        include_symbols = preferences.get('include_symbols', True)
        
        # Ensure minimum requirements for Google
        length = max(length, 8)
        
        chars = string.ascii_letters + string.digits
        if include_symbols:
            chars += "!@#$%^&*"
        
        password = ''.join(random.choices(chars, k=length))
        
        # Ensure it has at least one letter and one number
        if not any(c.isalpha() for c in password):
            password = password[:-1] + random.choice(string.ascii_letters)
        if not any(c.isdigit() for c in password):
            password = password[:-1] + random.choice(string.digits)
        
        return password
    
    async def signup(self, data: GoogleSignupData) -> GoogleSignupResult:
        """Perform Google account signup."""
        attempts = 0
        
        while attempts < self.config.retry_attempts:
            try:
                attempts += 1
                logger.info(f"Starting Google signup attempt {attempts}")
                
                self.driver = self._setup_driver()
                
                # Navigate to Google signup page
                self.driver.get("https://accounts.google.com/signup")
                
                # Fill in first name
                first_name_field = self._wait_and_find_element(By.ID, "firstName")
                self._type_with_delay(first_name_field, data.first_name)
                
                # Fill in last name
                last_name_field = self._wait_and_find_element(By.ID, "lastName")
                self._type_with_delay(last_name_field, data.last_name)
                
                # Click Next
                self._wait_and_click(By.ID, "collectNameNext")
                time.sleep(2)
                
                # Fill in birth date and gender if required
                try:
                    if data.birth_date:
                        month_field = self._wait_and_find_element(By.ID, "month", timeout=5)
                        month_field.send_keys(str(data.birth_date.month))
                        
                        day_field = self._wait_and_find_element(By.ID, "day")
                        day_field.send_keys(str(data.birth_date.day))
                        
                        year_field = self._wait_and_find_element(By.ID, "year")
                        year_field.send_keys(str(data.birth_date.year))
                        
                        # Gender (if present)
                        if data.gender:
                            gender_field = self._wait_and_find_element(By.ID, "gender", timeout=3)
                            gender_field.send_keys(data.gender)
                    
                    # Click Next
                    self._wait_and_click(By.ID, "birthdaygenderNext")
                    time.sleep(2)
                except TimeoutException:
                    # Birth date might not be required, continue
                    pass
                
                # Try to use custom username or get suggested one
                try:
                    # Look for username input
                    username_field = self._wait_and_find_element(By.NAME, "Username", timeout=10)
                    username_field.clear()
                    self._type_with_delay(username_field, data.username)
                    
                    # Click Next
                    self._wait_and_click(By.ID, "next")
                    time.sleep(3)
                    
                    # Check if username is available
                    error_elements = self.driver.find_elements(By.CSS_SELECTOR, "[data-error-id]")
                    if error_elements:
                        # Username taken, try suggested ones
                        suggested_usernames = self.driver.find_elements(By.CSS_SELECTOR, "[data-value]")
                        if suggested_usernames:
                            suggested_usernames[0].click()
                            time.sleep(1)
                            self._wait_and_click(By.ID, "next")
                            time.sleep(2)
                        else:
                            # Generate alternative username
                            alt_username = f"{data.username}{random.randint(100, 999)}"
                            username_field.clear()
                            self._type_with_delay(username_field, alt_username)
                            self._wait_and_click(By.ID, "next")
                            time.sleep(2)
                
                except TimeoutException:
                    # Username might be auto-generated
                    pass
                
                # Set password
                password_field = self._wait_and_find_element(By.NAME, "Passwd")
                self._type_with_delay(password_field, data.password)
                
                confirm_password_field = self._wait_and_find_element(By.NAME, "ConfirmPasswd")
                self._type_with_delay(confirm_password_field, data.password)
                
                # Click Next
                self._wait_and_click(By.ID, "createpasswordNext")
                time.sleep(3)
                
                # Handle phone verification
                result = await self._handle_verification(data)
                
                if result.success:
                    # Get final account information
                    try:
                        # Try to get the email from the page
                        email_elements = self.driver.find_elements(By.CSS_SELECTOR, "[data-email]")
                        if email_elements:
                            result.account_email = email_elements[0].get_attribute("data-email")
                        else:
                            # Construct email from username
                            result.account_email = f"{data.username}@gmail.com"
                    except Exception:
                        result.account_email = f"{data.username}@gmail.com"
                
                return result
                
            except Exception as e:
                logger.error(f"Google signup attempt {attempts} failed: {str(e)}")
                if attempts >= self.config.retry_attempts:
                    return GoogleSignupResult(
                        success=False,
                        error_message=f"All {self.config.retry_attempts} attempts failed. Last error: {str(e)}"
                    )
                time.sleep(5)  # Wait before retry
            
            finally:
                if self.driver:
                    self.driver.quit()
                    self.driver = None
        
        return GoogleSignupResult(
            success=False,
            error_message="Maximum retry attempts exceeded"
        )
    
    async def _handle_verification(self, data: GoogleSignupData) -> GoogleSignupResult:
        """Handle phone/email verification step."""
        try:
            # Check for phone verification step
            phone_elements = self.driver.find_elements(By.NAME, "phoneNumber")
            if phone_elements and data.phone_number and not data.skip_phone_verification:
                phone_field = phone_elements[0]
                self._type_with_delay(phone_field, data.phone_number)
                
                # Click Next/Send
                self._wait_and_click(By.ID, "next")
                time.sleep(2)
                
                # Return with verification required
                return GoogleSignupResult(
                    success=False,
                    verification_required=True,
                    verification_type="phone",
                    error_message="Phone verification required. Please complete manually."
                )
            
            # Try to skip phone verification
            skip_buttons = self.driver.find_elements(By.XPATH, "//span[contains(text(), 'Skip')]")
            if skip_buttons:
                skip_buttons[0].click()
                time.sleep(2)
            
            # Check for recovery email
            recovery_email_elements = self.driver.find_elements(By.NAME, "recoveryEmail")
            if recovery_email_elements and data.recovery_email:
                recovery_field = recovery_email_elements[0]
                self._type_with_delay(recovery_field, data.recovery_email)
                self._wait_and_click(By.ID, "next")
                time.sleep(2)
            
            # Accept terms and conditions
            try:
                # Look for agree/accept buttons
                agree_buttons = self.driver.find_elements(By.XPATH, "//span[contains(text(), 'I agree')]")
                if not agree_buttons:
                    agree_buttons = self.driver.find_elements(By.XPATH, "//span[contains(text(), 'Create account')]")
                
                if agree_buttons:
                    agree_buttons[0].click()
                    time.sleep(5)
                    
                    # Check if account was created successfully
                    if "myaccount.google.com" in self.driver.current_url or "welcome" in self.driver.current_url.lower():
                        return GoogleSignupResult(success=True)
                    
            except Exception as e:
                logger.warning(f"Could not complete final step: {str(e)}")
            
            return GoogleSignupResult(
                success=True,
                error_message="Account created but final verification may be needed"
            )
            
        except Exception as e:
            logger.error(f"Error during verification: {str(e)}")
            return GoogleSignupResult(
                success=False,
                error_message=f"Verification error: {str(e)}"
            )
    
    def __del__(self):
        """Cleanup driver on deletion."""
        if self.driver:
            try:
                self.driver.quit()
            except Exception:
                pass 