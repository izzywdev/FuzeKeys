"""
Configuration for permit.io integration.
"""

from typing import Dict, List
import os

class PermitIOConfig:
    """Configuration settings for permit.io automation."""
    
    # Base URLs
    BASE_URL = "https://app.permit.io"
    SIGNUP_URL = f"{BASE_URL}/signup"
    SIGNIN_URL = f"{BASE_URL}/signin"
    DASHBOARD_URL = f"{BASE_URL}/dashboard"
    API_KEYS_URL = f"{BASE_URL}/settings/api-keys"
    
    # Timeouts (in milliseconds)
    DEFAULT_TIMEOUT = 30000
    NAVIGATION_TIMEOUT = 60000
    ELEMENT_TIMEOUT = 10000
    
    # Viewport settings
    VIEWPORT_WIDTH = 1920
    VIEWPORT_HEIGHT = 1080
    
    # User agent
    USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    
    # Form selectors
    FORM_SELECTORS = {
        'email': [
            'input[type="email"]',
            'input[name="email"]',
            'input[placeholder*="email" i]',
            '#email',
            '[data-testid="email"]',
            '[aria-label*="email" i]'
        ],
        'password': [
            'input[type="password"]',
            'input[name="password"]',
            '#password',
            '[data-testid="password"]',
            '[aria-label*="password" i]'
        ],
        'first_name': [
            'input[name="firstName"]',
            'input[name="first_name"]',
            'input[placeholder*="first" i]',
            '#firstName',
            '#first_name',
            '[data-testid="firstName"]'
        ],
        'last_name': [
            'input[name="lastName"]',
            'input[name="last_name"]',
            'input[placeholder*="last" i]',
            '#lastName',
            '#last_name',
            '[data-testid="lastName"]'
        ],
        'company': [
            'input[name="company"]',
            'input[name="companyName"]',
            'input[placeholder*="company" i]',
            '#company',
            '#companyName',
            '[data-testid="company"]'
        ],
        'phone': [
            'input[type="tel"]',
            'input[name="phone"]',
            'input[placeholder*="phone" i]',
            '#phone',
            '[data-testid="phone"]'
        ],
        'submit': [
            'button[type="submit"]',
            'input[type="submit"]',
            'button:has-text("Sign up")',
            'button:has-text("Sign Up")',
            'button:has-text("Create Account")',
            'button:has-text("Register")',
            'button:has-text("Continue")',
            '[data-testid="submit"]',
            '.submit-button'
        ],
        'signin_submit': [
            'button[type="submit"]',
            'input[type="submit"]',
            'button:has-text("Sign in")',
            'button:has-text("Sign In")',
            'button:has-text("Login")',
            'button:has-text("Log In")',
            '[data-testid="signin"]',
            '.signin-button'
        ]
    }
    
    # Terms and conditions checkbox selectors
    TERMS_SELECTORS = [
        'input[type="checkbox"][name*="terms"]',
        'input[type="checkbox"][name*="agree"]',
        'input[type="checkbox"][id*="terms"]',
        'input[type="checkbox"][id*="agree"]',
        '[data-testid="terms-checkbox"]',
        '[data-testid="agree-checkbox"]'
    ]
    
    # Success indicators
    SUCCESS_INDICATORS = [
        "welcome",
        "dashboard",
        "verify",
        "check your email",
        "successfully registered",
        "account created",
        "sign up successful",
        "registration complete"
    ]
    
    # Error indicators
    ERROR_INDICATORS = [
        "error",
        "failed",
        "invalid",
        "incorrect",
        "already exists",
        "already registered",
        "wrong",
        "forbidden",
        "unauthorized"
    ]
    
    # API key creation selectors
    API_KEY_SELECTORS = {
        'create_button': [
            'button:has-text("Create API Key")',
            'button:has-text("New API Key")',
            'button:has-text("Generate Key")',
            '[data-testid="create-api-key"]',
            '.create-api-key'
        ],
        'key_name': [
            'input[name="name"]',
            'input[placeholder*="key name" i]',
            '#keyName',
            '[data-testid="key-name"]'
        ],
        'save_button': [
            'button:has-text("Save")',
            'button:has-text("Create")',
            'button:has-text("Generate")',
            '[data-testid="save-key"]'
        ]
    }
    
    # Screenshot settings
    SCREENSHOT_OPTIONS = {
        'full_page': True,
        'quality': 90,
        'type': 'png'
    }
    
    @classmethod
    def get_timeout(cls, operation: str = 'default') -> int:
        """Get timeout for specific operation."""
        timeouts = {
            'default': cls.DEFAULT_TIMEOUT,
            'navigation': cls.NAVIGATION_TIMEOUT,
            'element': cls.ELEMENT_TIMEOUT
        }
        return timeouts.get(operation, cls.DEFAULT_TIMEOUT)
    
    @classmethod
    def get_selectors(cls, field: str) -> List[str]:
        """Get selectors for a specific form field."""
        return cls.FORM_SELECTORS.get(field, [])
    
    @classmethod
    def is_headless_allowed(cls) -> bool:
        """Check if headless mode is allowed (for development/debugging)."""
        return os.getenv('PERMIT_IO_ALLOW_HEADLESS', 'true').lower() == 'true' 