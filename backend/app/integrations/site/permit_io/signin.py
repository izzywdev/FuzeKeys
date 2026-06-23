"""
Permit.io signin automation module.

This module handles automated authentication for permit.io.
"""

import asyncio
import logging
from typing import Optional, Dict, Any
from playwright.async_api import async_playwright, Page, Browser, BrowserContext

from .models import PermitIOResult, PermitIOSessionInfo
from .config import PermitIOConfig

logger = logging.getLogger(__name__)

class SigninAutomation:
    """Handles automated signin for permit.io."""
    
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
        screenshot_path = f"permit_signin_{name}.png"
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
    
    async def submit_signin_form(self) -> bool:
        """Submit the signin form."""
        for selector in self.config.get_selectors('signin_submit'):
            try:
                submit_button = await self.page.wait_for_selector(
                    selector, 
                    timeout=self.config.get_timeout('element')
                )
                if submit_button:
                    await submit_button.click()
                    logger.info("Signin form submitted")
                    return True
            except Exception as e:
                logger.debug(f"Signin submit selector {selector} failed: {str(e)}")
                continue
        return False
    
    async def extract_session_info(self) -> Optional[PermitIOSessionInfo]:
        """Extract session information after successful login."""
        try:
            # Get cookies
            cookies = await self.context.cookies()
            cookie_dict = {cookie['name']: cookie['value'] for cookie in cookies}
            
            # Look for common session indicators
            current_url = self.page.url
            
            # Try to extract user ID from DOM or localStorage
            user_id = None
            workspace_id = None
            csrf_token = None
            
            try:
                # Try to get user info from JavaScript
                user_info = await self.page.evaluate("""
                    () => {
                        // Try various ways to get user info
                        return {
                            userId: window.userId || localStorage.getItem('userId') || null,
                            workspaceId: window.workspaceId || localStorage.getItem('workspaceId') || null,
                            csrfToken: document.querySelector('meta[name="csrf-token"]')?.content || null
                        };
                    }
                """)
                user_id = user_info.get('userId')
                workspace_id = user_info.get('workspaceId')
                csrf_token = user_info.get('csrfToken')
            except:
                logger.debug("Could not extract user info from JavaScript")
            
            # Generate session ID from available data
            session_id = cookie_dict.get('session_id') or cookie_dict.get('sessionId') or f"session_{hash(current_url)}"
            
            return PermitIOSessionInfo(
                session_id=session_id,
                user_id=user_id or "unknown",
                workspace_id=workspace_id or "unknown",
                csrf_token=csrf_token,
                cookies=cookie_dict
            )
        except Exception as e:
            logger.error(f"Failed to extract session info: {str(e)}")
            return None
    
    async def check_signin_result(self) -> PermitIOResult:
        """Check the result of the signin attempt."""
        await asyncio.sleep(3)
        await self.wait_for_page_load()
        
        page_content = await self.page.content()
        current_url = self.page.url
        
        # Take final screenshot
        final_screenshot = await self.take_screenshot("final")
        
        # Check for successful signin (usually redirected to dashboard)
        if any(indicator in current_url.lower() for indicator in ["dashboard", "app", "workspace"]):
            session_info = await self.extract_session_info()
            return PermitIOResult(
                success=True,
                message="Sign-in successful",
                data={
                    "final_url": current_url,
                    "dashboard_url": current_url,
                    "session_info": session_info.__dict__ if session_info else None
                },
                screenshots=[final_screenshot]
            )
        
        # Check for success indicators in content
        for indicator in self.config.SUCCESS_INDICATORS:
            if indicator.lower() in page_content.lower():
                session_info = await self.extract_session_info()
                return PermitIOResult(
                    success=True,
                    message="Sign-in successful",
                    data={
                        "final_url": current_url,
                        "session_info": session_info.__dict__ if session_info else None
                    },
                    screenshots=[final_screenshot]
                )
        
        # Check for error indicators
        error_messages = [
            "invalid credentials",
            "incorrect password",
            "user not found",
            "authentication failed",
            "login failed",
            "wrong password",
            "account not found"
        ]
        
        for error in error_messages:
            if error.lower() in page_content.lower():
                return PermitIOResult(
                    success=False,
                    message="Sign-in failed",
                    error=f"Authentication error: {error}",
                    data={"final_url": current_url},
                    screenshots=[final_screenshot]
                )
        
        # Check for general error indicators
        for indicator in self.config.ERROR_INDICATORS:
            if indicator.lower() in page_content.lower():
                return PermitIOResult(
                    success=False,
                    message="Sign-in failed",
                    error=f"Error detected: {indicator}",
                    data={"final_url": current_url},
                    screenshots=[final_screenshot]
                )
        
        # If URL changed from signin page, assume success
        if current_url != self.config.SIGNIN_URL and "signin" not in current_url.lower():
            session_info = await self.extract_session_info()
            return PermitIOResult(
                success=True,
                message="Sign-in completed (status unclear)",
                data={
                    "final_url": current_url,
                    "session_info": session_info.__dict__ if session_info else None
                },
                screenshots=[final_screenshot]
            )
        
        return PermitIOResult(
            success=False,
            message="Sign-in status unclear",
            error="Could not determine signin result",
            data={"final_url": current_url},
            screenshots=[final_screenshot]
        )
    
    async def authenticate(self, email: str, password: str) -> PermitIOResult:
        """
        Authenticate with permit.io.
        
        Args:
            email: User email address
            password: User password
            
        Returns:
            PermitIOResult with signin status and session details
        """
        try:
            logger.info(f"Starting permit.io signin for {email}")
            
            # Navigate to signin page
            await self.page.goto(self.config.SIGNIN_URL, wait_until="networkidle")
            await self.wait_for_page_load()
            
            # Take initial screenshot
            await self.take_screenshot("start")
            
            # Check if we're on the right page, try to find signin link if not
            if "signin" not in self.page.url.lower() and "login" not in self.page.url.lower():
                signin_selectors = [
                    'a[href*="signin"]',
                    'a[href*="login"]',
                    'button:has-text("Sign in")',
                    'button:has-text("Login")',
                    '[data-testid="signin"]'
                ]
                
                for selector in signin_selectors:
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
                email, 
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
                password, 
                'password'
            ):
                return PermitIOResult(
                    success=False,
                    message="Could not find password field",
                    error="Password field not found"
                )
            
            # Take screenshot before submission
            await self.take_screenshot("before_submit")
            
            # Submit the form
            if not await self.submit_signin_form():
                return PermitIOResult(
                    success=False,
                    message="Could not find submit button",
                    error="Submit button not found"
                )
            
            # Check the result
            return await self.check_signin_result()
            
        except Exception as e:
            logger.error(f"Signin failed with exception: {str(e)}")
            return PermitIOResult(
                success=False,
                message="Signin failed with exception",
                error=str(e)
            )

# Convenience function
async def authenticate(email: str, password: str, headless: bool = True) -> PermitIOResult:
    """
    Convenience function to authenticate with permit.io.
    
    Args:
        email: User email address
        password: User password
        headless: Whether to run browser in headless mode
        
    Returns:
        PermitIOResult with signin status and session details
    """
    async with SigninAutomation(headless=headless) as automation:
        return await automation.authenticate(email, password) 