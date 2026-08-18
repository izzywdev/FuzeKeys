"""
Permit.io Integration Package

This package provides automated account management for permit.io including:
- Account signup automation
- Authentication signin automation
- API key creation and management

Usage:
    from app.integrations.site.permit_io import signup, signin, apikey
    
    # Sign up for a new account
    result = await signup.create_account(credentials)
    
    # Sign in to existing account
    result = await signin.authenticate(email, password)
    
    # Create API key
    api_key = await apikey.create_key(account_info)
"""

import logging

# Import automation modules
from . import apikey, signin, signup
from .config import PermitIOConfig
from .models import PermitIOCredentials, PermitIOResult

logger = logging.getLogger(__name__)

__version__ = "1.0.0"
__site__ = "permit.io"

# Site capabilities
CAPABILITIES = {
    "signup": True,
    "signin": True,
    "apikey": True,
    "headless": True,
    "screenshot_debug": True,
}


class PermitIOIntegration:
    """Main integration class for permit.io automation."""

    def __init__(self, headless: bool = True):
        self.headless = headless
        self.config = PermitIOConfig()

    @staticmethod
    def _failure(operation: str, error: Exception) -> PermitIOResult:
        """Turn an automation exception into a structured failure result."""
        logger.exception("permit.io %s failed", operation)
        return PermitIOResult(
            success=False,
            message=f"permit.io {operation} failed",
            error=str(error),
        )

    async def signup_account(self, credentials: PermitIOCredentials) -> PermitIOResult:
        """Create a new permit.io account."""
        try:
            return await signup.create_account(credentials, headless=self.headless)
        except Exception as e:
            return self._failure("signup", e)

    async def signin_account(self, email: str, password: str) -> PermitIOResult:
        """Sign in to existing permit.io account."""
        try:
            return await signin.authenticate(email, password, headless=self.headless)
        except Exception as e:
            return self._failure("signin", e)

    async def create_api_key(
        self, email: str, password: str, key_name: str = "FuzeKeys"
    ) -> PermitIOResult:
        """Create an API key for the account."""
        try:
            return await apikey.create_key(
                email, password, key_name, headless=self.headless
            )
        except Exception as e:
            return self._failure("api key creation", e)
