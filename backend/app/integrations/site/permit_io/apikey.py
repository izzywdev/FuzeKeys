"""
Permit.io API key creation automation module.

This module handles automated API key creation for permit.io accounts.
"""

import asyncio
import logging
import re
from typing import Optional, List
from playwright.async_api import async_playwright, Page, Browser, BrowserContext

from .models import PermitIOResult, PermitIOApiKey
from .config import PermitIOConfig
from .signin import SigninAutomation

logger = logging.getLogger(__name__)

class ApiKeyAutomation:
    """Handles automated API key creation for permit.io."""
    
    def __init__(self, headless: bool = True):
        self.headless = headless
        self.config = PermitIOConfig()
        self.playwright = None
        self.browser = None
        self.context = None
        self.page = None
    
    async def __aenter__(self):
        """Async context manager entry."""
        self.playwright = await async_playwright().start()
        self.browser = await self.playwright.chromium.launch(headless=self.headless)
        self.context = await self.browser.new_context(
            viewport={
                "width": self.config.VIEWPORT_WIDTH, 
                "height": self.config.VIEWPORT_HEIGHT
            },
            user_agent=self.config.USER_AGENT
        )
        self.page = await self.context.new_page()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        if self.browser:
            await self.browser.close()
        if self.playwright:
            await self.playwright.stop()
    
    async def wait_for_page_load(self) -> None:
        """Wait for page to load completely."""
        await self.page.wait_for_load_state("networkidle")
        await asyncio.sleep(2)  # Additional wait for dynamic content
    
    async def take_screenshot(self, name: str) -> str:
        """Take a screenshot for debugging."""
        screenshot_path = f"permit_apikey_{name}.png"
        await self.page.screenshot(path=screenshot_path, **self.config.SCREENSHOT_OPTIONS)
        return screenshot_path
    
    async def navigate_to_api_keys_page(self) -> bool:
        """Navigate to the API keys management page."""
        try:
            # Try direct URL first
            await self.page.goto(self.config.API_KEYS_URL, wait_until="networkidle")
            await self.wait_for_page_load()
            
            # Check if we're on the API keys page
            if "api" in self.page.url.lower() and "key" in self.page.url.lower():
                return True
            
            # Try to find navigation links
            api_nav_selectors = [
                'a[href*="api-key"]',
                'a[href*="api"]',
                'button:has-text("API Keys")',
                'button:has-text("API")',
                '[data-testid="api-keys"]',
                '.api-keys-nav',
                'nav a:has-text("API")',
                'nav a:has-text("Settings")',
                'a:has-text("Settings")'
            ]
            
            for selector in api_nav_selectors:
                try:
                    element = await self.page.wait_for_selector(selector, timeout=5000)
                    if element:
                        await element.click()
                        await self.wait_for_page_load()
                        
                        # Check if we reached API keys page
                        if "api" in self.page.url.lower():
                            return True
                        break
                except:
                    continue
            
            # If we're in settings, look for API keys section
            if "settings" in self.page.url.lower():
                api_section_selectors = [
                    'a:has-text("API Keys")',
                    'button:has-text("API Keys")',
                    '[data-testid="api-keys-tab"]',
                    '.api-keys-section'
                ]
                
                for selector in api_section_selectors:
                    try:
                        element = await self.page.wait_for_selector(selector, timeout=3000)
                        if element:
                            await element.click()
                            await self.wait_for_page_load()
                            return True
                    except:
                        continue
            
            return False
            
        except Exception as e:
            logger.error(f"Failed to navigate to API keys page: {str(e)}")
            return False
    
    async def create_api_key_form(self, key_name: str) -> Optional[str]:
        """Create an API key using the form interface."""
        try:
            # Look for create API key button
            for selector in self.config.API_KEY_SELECTORS['create_button']:
                try:
                    create_button = await self.page.wait_for_selector(selector, timeout=5000)
                    if create_button:
                        await create_button.click()
                        await self.wait_for_page_load()
                        break
                except:
                    continue
            else:
                logger.error("Could not find create API key button")
                return None
            
            # Fill in the key name
            for selector in self.config.API_KEY_SELECTORS['key_name']:
                try:
                    name_field = await self.page.wait_for_selector(selector, timeout=5000)
                    if name_field:
                        await name_field.fill(key_name)
                        logger.info(f"Filled API key name: {key_name}")
                        break
                except:
                    continue
            
            # Take screenshot before saving
            await self.take_screenshot("before_save")
            
            # Click save/create button
            for selector in self.config.API_KEY_SELECTORS['save_button']:
                try:
                    save_button = await self.page.wait_for_selector(selector, timeout=5000)
                    if save_button:
                        await save_button.click()
                        await self.wait_for_page_load()
                        break
                except:
                    continue
            else:
                logger.error("Could not find save button")
                return None
            
            # Wait for API key to be generated and displayed
            await asyncio.sleep(3)
            
            # Try to extract the API key from the page
            api_key = await self.extract_api_key_from_page()
            if api_key:
                logger.info("Successfully created API key")
                return api_key
            
            return None
            
        except Exception as e:
            logger.error(f"Failed to create API key: {str(e)}")
            return None
    
    async def extract_api_key_from_page(self) -> Optional[str]:
        """Extract the generated API key from the page."""
        try:
            # Common selectors for API key display
            api_key_selectors = [
                'input[readonly][value*="permit_"]',
                'input[value*="pk_"]',
                'code:has-text("permit_")',
                'span:has-text("permit_")',
                '[data-testid="api-key-value"]',
                '.api-key-value',
                'pre:has-text("permit_")',
                'textarea[readonly]'
            ]
            
            for selector in api_key_selectors:
                try:
                    element = await self.page.wait_for_selector(selector, timeout=3000)
                    if element:
                        # Try to get value from input/textarea
                        api_key = await element.get_attribute('value')
                        if not api_key:
                            # Try to get text content
                            api_key = await element.text_content()
                        
                        if api_key and ('permit_' in api_key or 'pk_' in api_key):
                            # Clean up the API key (remove extra whitespace, etc.)
                            api_key = api_key.strip()
                            return api_key
                except:
                    continue
            
            # Try to extract from page content using regex
            page_content = await self.page.content()
            api_key_patterns = [
                r'permit_[a-zA-Z0-9_-]+',
                r'pk_[a-zA-Z0-9_-]+',
                r'[a-zA-Z0-9]{32,}'  # Generic long string that might be an API key
            ]
            
            for pattern in api_key_patterns:
                matches = re.findall(pattern, page_content)
                if matches:
                    # Return the longest match (likely the most complete API key)
                    return max(matches, key=len)
            
            return None
            
        except Exception as e:
            logger.error(f"Failed to extract API key: {str(e)}")
            return None
    
    async def list_existing_api_keys(self) -> List[dict]:
        """List existing API keys on the page."""
        try:
            # Look for existing API keys in a table or list
            api_keys = []
            
            # Try to find API key entries
            key_selectors = [
                'tr:has(td:has-text("permit_"))',
                '.api-key-item',
                '[data-testid="api-key-row"]',
                'li:has-text("permit_")'
            ]
            
            for selector in key_selectors:
                try:
                    elements = await self.page.query_selector_all(selector)
                    for element in elements:
                        text = await element.text_content()
                        if text and ('permit_' in text or 'pk_' in text):
                            api_keys.append({
                                'text': text.strip(),
                                'element': element
                            })
                except:
                    continue
            
            return api_keys
            
        except Exception as e:
            logger.error(f"Failed to list API keys: {str(e)}")
            return []
    
    async def create_key(self, email: str, password: str, key_name: str = "FuzeKeys") -> PermitIOResult:
        """
        Create an API key for the permit.io account.
        
        Args:
            email: Account email
            password: Account password  
            key_name: Name for the API key
            
        Returns:
            PermitIOResult with API key creation status and key details
        """
        try:
            logger.info(f"Starting API key creation for {email}")
            
            # First, sign in to the account
            signin_automation = SigninAutomation(headless=self.headless)
            async with signin_automation as signin:
                signin_result = await signin.authenticate(email, password)
                
                if not signin_result.success:
                    return PermitIOResult(
                        success=False,
                        message="Failed to sign in before creating API key",
                        error=signin_result.error
                    )
                
                # Copy the signed-in session to our context
                self.context = signin.context
                self.page = signin.page
            
            # Take screenshot after signin
            await self.take_screenshot("after_signin")
            
            # Navigate to API keys page
            if not await self.navigate_to_api_keys_page():
                return PermitIOResult(
                    success=False,
                    message="Could not navigate to API keys page",
                    error="Navigation failed"
                )
            
            # Take screenshot of API keys page
            await self.take_screenshot("api_keys_page")
            
            # List existing API keys
            existing_keys = await self.list_existing_api_keys()
            logger.info(f"Found {len(existing_keys)} existing API keys")
            
            # Create new API key
            api_key_value = await self.create_api_key_form(key_name)
            
            if not api_key_value:
                return PermitIOResult(
                    success=False,
                    message="Failed to create API key",
                    error="API key creation failed or key not found"
                )
            
            # Take final screenshot
            final_screenshot = await self.take_screenshot("final")
            
            # Create API key object
            api_key = PermitIOApiKey(
                key_id=f"key_{hash(api_key_value)}",
                name=key_name,
                key_value=api_key_value,
                is_active=True
            )
            
            return PermitIOResult(
                success=True,
                message="API key created successfully",
                data={
                    "api_key": api_key.__dict__,
                    "key_value": api_key_value,
                    "key_name": key_name,
                    "existing_keys_count": len(existing_keys)
                },
                screenshots=[final_screenshot]
            )
            
        except Exception as e:
            logger.error(f"API key creation failed with exception: {str(e)}")
            return PermitIOResult(
                success=False,
                message="API key creation failed with exception",
                error=str(e)
            )

# Convenience function
async def create_key(email: str, password: str, key_name: str = "FuzeKeys", headless: bool = True) -> PermitIOResult:
    """
    Convenience function to create a permit.io API key.
    
    Args:
        email: Account email
        password: Account password
        key_name: Name for the API key
        headless: Whether to run browser in headless mode
        
    Returns:
        PermitIOResult with API key creation status and key details
    """
    async with ApiKeyAutomation(headless=headless) as automation:
        return await automation.create_key(email, password, key_name) 