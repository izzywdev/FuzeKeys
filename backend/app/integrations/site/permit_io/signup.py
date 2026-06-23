"""
Permit.io signup automation module.

This module handles automated account creation for permit.io.
"""

import asyncio
import logging
from typing import Optional
from playwright.async_api import async_playwright, Page, Browser, BrowserContext

from .models import PermitIOCredentials, PermitIOResult, PermitIOAccountInfo
from .config import PermitIOConfig

logger = logging.getLogger(__name__)

class SignupAutomation:
    """Handles automated signup for permit.io."""
    
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
        screenshot_path = f"permit_signup_{name}.png"
        await self.page.screenshot(path=screenshot_path, **self.config.SCREENSHOT_OPTIONS)
        return screenshot_path
    
    async def fill_form_field(self, selectors: list, value: str, field_name: str) -> bool:
        """Try to fill a form field using multiple selectors."""
        for selector in selectors:
            try:
                element = await self.page.wait_for_selector(
                    selector, 
                    timeout=self.config.get_timeout('element')
                )
                if element:
                    await element.fill(value)
                    logger.info(f"Successfully filled {field_name} field")
                    return True
            except Exception as e:
                logger.debug(f"Selector {selector} failed for {field_name}: {str(e)}")
                continue
        return False
    
    async def check_terms_checkbox(self) -> bool:
        """Check terms and conditions checkbox if present."""
        for selector in self.config.TERMS_SELECTORS:
            try:
                checkbox = await self.page.wait_for_selector(
                    selector, 
                    timeout=self.config.get_timeout('element')
                )
                if checkbox:
                    await checkbox.check()
                    logger.info("Terms checkbox checked")
                    return True
            except Exception as e:
                logger.debug(f"Terms selector {selector} failed: {str(e)}")
                continue
        return False
    
    async def submit_form(self) -> bool:
        """Submit the signup form."""
        for selector in self.config.get_selectors('submit'):
            try:
                submit_button = await self.page.wait_for_selector(
                    selector, 
                    timeout=self.config.get_timeout('element')
                )
                if submit_button:
                    await submit_button.click()
                    logger.info("Signup form submitted")
                    return True
            except Exception as e:
                logger.debug(f"Submit selector {selector} failed: {str(e)}")
                continue
        return False
    
    async def check_result(self) -> PermitIOResult:
        """Check the result of the signup attempt."""
        await asyncio.sleep(3)
        await self.wait_for_page_load()
        
        page_content = await self.page.content()
        current_url = self.page.url
        
        # Take final screenshot
        final_screenshot = await self.take_screenshot("final")
        
        # Check for success indicators
        for indicator in self.config.SUCCESS_INDICATORS:
            if indicator.lower() in page_content.lower() or indicator.lower() in current_url.lower():
                return PermitIOResult(
                    success=True,
                    message="Account created successfully",
                    data={
                        "final_url": current_url,
                        "requires_verification": "verify" in page_content.lower(),
                        "dashboard_url": self.config.DASHBOARD_URL if "dashboard" in current_url else None
                    },
                    screenshots=[final_screenshot]
                )
        
        # Check for error indicators
        for indicator in self.config.ERROR_INDICATORS:
            if indicator.lower() in page_content.lower():
                return PermitIOResult(
                    success=False,
                    message="Signup failed",
                    error=f"Error detected: {indicator}",
                    data={"final_url": current_url},
                    screenshots=[final_screenshot]
                )
        
        # If no clear indicators, assume success if URL changed appropriately
        if current_url != self.config.SIGNUP_URL and "error" not in current_url.lower():
            return PermitIOResult(
                success=True,
                message="Signup completed (status unclear)",
                data={"final_url": current_url},
                screenshots=[final_screenshot]
            )
        
        return PermitIOResult(
            success=False,
            message="Signup status unclear",
            error="Could not determine signup result",
            data={"final_url": current_url},
            screenshots=[final_screenshot]
        )
    
    async def create_account(self, credentials: PermitIOCredentials) -> PermitIOResult:
        """
        Create a new permit.io account.
        
        Args:
            credentials: User credentials for account creation
            
        Returns:
            PermitIOResult with signup status and details
        """
        try:
            logger.info(f"Starting permit.io signup for {credentials.email}")
            
            # Navigate to signup page
            await self.page.goto(self.config.SIGNUP_URL, wait_until="networkidle")
            await self.wait_for_page_load()
            
            # Take initial screenshot
            await self.take_screenshot("start")
            
            # Check if we're on the right page, try to find signup link if not
            if "signup" not in self.page.url.lower() and "register" not in self.page.url.lower():
                signup_selectors = [
                    'a[href*="signup"]',
                    'a[href*="register"]',
                    'button:has-text("Sign up")',
                    'button:has-text("Register")',
                    '[data-testid="signup"]'
                ]
                
                for selector in signup_selectors:
                    try:
                        element = await self.page.wait_for_selector(selector, timeout=5000)
                        if element:
                            await element.click()
                            await self.wait_for_page_load()
                            break
                    except:
                        continue
            
            # Fill email field
            if not await self.fill_form_field(
                self.config.get_selectors('email'), 
                credentials.email, 
                'email'
            ):
                return PermitIOResult(
                    success=False,
                    message="Could not find email field",
                    error="Email field not found"
                )
            
            # Fill password field
            if not await self.fill_form_field(
                self.config.get_selectors('password'), 
                credentials.password, 
                'password'
            ):
                return PermitIOResult(
                    success=False,
                    message="Could not find password field",
                    error="Password field not found"
                )
            
            # Fill first name
            await self.fill_form_field(
                self.config.get_selectors('first_name'), 
                credentials.first_name, 
                'first_name'
            )
            
            # Fill last name
            await self.fill_form_field(
                self.config.get_selectors('last_name'), 
                credentials.last_name, 
                'last_name'
            )
            
            # Fill company name if provided
            if credentials.company_name:
                await self.fill_form_field(
                    self.config.get_selectors('company'), 
                    credentials.company_name, 
                    'company'
                )
            
            # Fill phone if provided
            if credentials.phone:
                await self.fill_form_field(
                    self.config.get_selectors('phone'), 
                    credentials.phone, 
                    'phone'
                )
            
            # Check terms and conditions
            await self.check_terms_checkbox()
            
            # Take screenshot before submission
            await self.take_screenshot("before_submit")
            
            # Submit the form
            if not await self.submit_form():
                return PermitIOResult(
                    success=False,
                    message="Could not find submit button",
                    error="Submit button not found"
                )
            
            # Check the result
            return await self.check_result()
            
        except Exception as e:
            logger.error(f"Signup failed with exception: {str(e)}")
            return PermitIOResult(
                success=False,
                message="Signup failed with exception",
                error=str(e)
            )

# Convenience function
async def create_account(credentials: PermitIOCredentials, headless: bool = True) -> PermitIOResult:
    """
    Convenience function to create a permit.io account.
    
    Args:
        credentials: User credentials for account creation
        headless: Whether to run browser in headless mode
        
    Returns:
        PermitIOResult with signup status and details
    """
    async with SignupAutomation(headless=headless) as automation:
        return await automation.create_account(credentials) 