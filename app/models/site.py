"""
Site model for storing information about sites we want to automate.

This model tracks sites, their automation difficulty, anti-bot measures,
and our implementation status.
"""

from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime, JSON, Enum
from sqlalchemy.sql import func
from enum import Enum as PyEnum
from app.database import Base

class DifficultyLevel(PyEnum):
    """Difficulty levels for automation."""
    EASY = "easy"           # Simple forms, no anti-bot measures
    MEDIUM = "medium"       # Some protection, manageable
    HARD = "hard"           # Strong protection, requires advanced techniques
    EXTREME = "extreme"     # Nearly impossible, heavy protection

class ImplementationStatus(PyEnum):
    """Implementation status for each functionality."""
    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress" 
    COMPLETED = "completed"
    FAILED = "failed"
    BLOCKED = "blocked"     # Blocked by technical limitations

class AutomationMethod(PyEnum):
    """Available automation methods."""
    API = "api"                    # Official API integration
    SCRAPING = "scraping"          # Web scraping automation
    MANUAL = "manual"              # Manual process only
    HYBRID = "hybrid"              # Combination of API and scraping

class AutomationFramework(PyEnum):
    """Automation frameworks/technologies."""
    SELENIUM = "selenium"          # Selenium WebDriver
    PLAYWRIGHT = "playwright"     # Microsoft Playwright
    REQUESTS = "requests"          # Simple HTTP requests
    PUPPETEER = "puppeteer"        # Puppeteer (if needed)
    API_ONLY = "api_only"          # Pure API calls

class Site(Base):
    """
    Model for storing site information and automation status.
    """
    __tablename__ = "sites"

    id = Column(Integer, primary_key=True, index=True)
    
    # Basic site information
    name = Column(String(100), nullable=False, index=True)
    display_name = Column(String(150), nullable=False)
    url = Column(String(500), nullable=False)
    logo_url = Column(String(500), nullable=True)
    category = Column(String(50), nullable=False, index=True)  # cloud, social, dev-tools, etc.
    description = Column(Text, nullable=True)
    
    # Difficulty levels for each process
    signup_difficulty = Column(Enum(DifficultyLevel), default=DifficultyLevel.MEDIUM)
    signin_difficulty = Column(Enum(DifficultyLevel), default=DifficultyLevel.EASY)
    apikey_difficulty = Column(Enum(DifficultyLevel), default=DifficultyLevel.MEDIUM)
    
    # Method availability tracking (JSON arrays)
    signup_methods = Column(JSON, default=list)  # ["api", "scraping", "manual"]
    signin_methods = Column(JSON, default=list)  # ["api", "scraping", "manual"] 
    apikey_methods = Column(JSON, default=list)  # ["api", "scraping", "manual"]
    
    # Preferred method order (what to try first)
    signup_preferred_method = Column(Enum(AutomationMethod), default=AutomationMethod.API)
    signin_preferred_method = Column(Enum(AutomationMethod), default=AutomationMethod.API)
    apikey_preferred_method = Column(Enum(AutomationMethod), default=AutomationMethod.API)
    
    # Automation technology requirements
    automation_framework = Column(Enum(AutomationFramework), default=AutomationFramework.SELENIUM)
    requires_javascript = Column(Boolean, default=True)
    requires_browser_automation = Column(Boolean, default=True)
    requires_proxy = Column(Boolean, default=False)
    requires_user_agent_rotation = Column(Boolean, default=False)
    
    # API method details
    api_signup_endpoint = Column(String(500), nullable=True)
    api_signin_endpoint = Column(String(500), nullable=True)
    api_key_endpoint = Column(String(500), nullable=True)
    api_authentication_method = Column(String(50), nullable=True)  # "oauth", "api_key", "basic_auth"
    api_base_url = Column(String(500), nullable=True)
    
    # Anti-bot and verification requirements
    requires_email_verification = Column(Boolean, default=True)
    requires_phone_verification = Column(Boolean, default=False)
    requires_sms_verification = Column(Boolean, default=False)
    requires_authenticator = Column(Boolean, default=False)
    has_captcha = Column(Boolean, default=False)
    captcha_type = Column(String(50), nullable=True)  # recaptcha, hcaptcha, custom
    
    # Anti-scraping measures (JSON array of techniques)
    anti_bot_techniques = Column(JSON, default=list)
    # Examples: ["cloudflare", "rate_limiting", "js_challenge", "device_fingerprinting"]
    
    # Implementation status
    signup_status = Column(Enum(ImplementationStatus), default=ImplementationStatus.NOT_STARTED)
    signin_status = Column(Enum(ImplementationStatus), default=ImplementationStatus.NOT_STARTED)
    apikey_status = Column(Enum(ImplementationStatus), default=ImplementationStatus.NOT_STARTED)
    
    # Additional metadata
    priority = Column(Integer, default=50)  # 1-100, higher = more important
    estimated_hours = Column(Integer, nullable=True)  # Development time estimate
    notes = Column(Text, nullable=True)
    
    # API information (legacy - kept for compatibility)
    has_official_api = Column(Boolean, default=False)
    api_documentation_url = Column(String(500), nullable=True)
    api_rate_limits = Column(String(200), nullable=True)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    last_tested = Column(DateTime(timezone=True), nullable=True)
    
    def __repr__(self):
        return f"<Site(name='{self.name}', category='{self.category}', signup_difficulty='{self.signup_difficulty.value}')>"

    @property
    def overall_difficulty(self):
        """Calculate overall difficulty based on individual process difficulties."""
        difficulties = [
            self.signup_difficulty,
            self.signin_difficulty, 
            self.apikey_difficulty
        ]
        
        # Count difficulty levels
        difficulty_scores = {
            DifficultyLevel.EASY: 1,
            DifficultyLevel.MEDIUM: 2,
            DifficultyLevel.HARD: 3,
            DifficultyLevel.EXTREME: 4
        }
        
        avg_score = sum(difficulty_scores[d] for d in difficulties) / len(difficulties)
        
        if avg_score <= 1.5:
            return DifficultyLevel.EASY
        elif avg_score <= 2.5:
            return DifficultyLevel.MEDIUM
        elif avg_score <= 3.5:
            return DifficultyLevel.HARD
        else:
            return DifficultyLevel.EXTREME

    @property
    def implementation_progress(self):
        """Calculate implementation progress percentage."""
        statuses = [self.signup_status, self.signin_status, self.apikey_status]
        completed = sum(1 for status in statuses if status == ImplementationStatus.COMPLETED)
        return (completed / len(statuses)) * 100

    def get_available_methods(self, operation: str):
        """Get available methods for a specific operation."""
        method_map = {
            'signup': self.signup_methods or [],
            'signin': self.signin_methods or [],
            'apikey': self.apikey_methods or []
        }
        return method_map.get(operation, [])

    def get_preferred_method(self, operation: str):
        """Get preferred method for a specific operation."""
        method_map = {
            'signup': self.signup_preferred_method,
            'signin': self.signin_preferred_method,
            'apikey': self.apikey_preferred_method
        }
        return method_map.get(operation)

    def has_method(self, operation: str, method: str):
        """Check if a specific method is available for an operation."""
        available_methods = self.get_available_methods(operation)
        return method in available_methods

    def to_dict(self):
        """Convert to dictionary for API responses."""
        return {
            "id": self.id,
            "name": self.name,
            "display_name": self.display_name,
            "url": self.url,
            "logo_url": self.logo_url,
            "category": self.category,
            "description": self.description,
            "signup_difficulty": self.signup_difficulty.value,
            "signin_difficulty": self.signin_difficulty.value,
            "apikey_difficulty": self.apikey_difficulty.value,
            "overall_difficulty": self.overall_difficulty.value,
            
            # Method availability
            "signup_methods": self.signup_methods or [],
            "signin_methods": self.signin_methods or [],
            "apikey_methods": self.apikey_methods or [],
            "signup_preferred_method": self.signup_preferred_method.value if self.signup_preferred_method else None,
            "signin_preferred_method": self.signin_preferred_method.value if self.signin_preferred_method else None,
            "apikey_preferred_method": self.apikey_preferred_method.value if self.apikey_preferred_method else None,
            
            # Automation technology
            "automation_framework": self.automation_framework.value if self.automation_framework else None,
            "requires_javascript": self.requires_javascript,
            "requires_browser_automation": self.requires_browser_automation,
            "requires_proxy": self.requires_proxy,
            "requires_user_agent_rotation": self.requires_user_agent_rotation,
            
            # API details
            "api_signup_endpoint": self.api_signup_endpoint,
            "api_signin_endpoint": self.api_signin_endpoint,
            "api_key_endpoint": self.api_key_endpoint,
            "api_authentication_method": self.api_authentication_method,
            "api_base_url": self.api_base_url,
            
            # Legacy and other fields
            "requires_email_verification": self.requires_email_verification,
            "requires_phone_verification": self.requires_phone_verification,
            "requires_sms_verification": self.requires_sms_verification,
            "requires_authenticator": self.requires_authenticator,
            "has_captcha": self.has_captcha,
            "captcha_type": self.captcha_type,
            "anti_bot_techniques": self.anti_bot_techniques,
            "signup_status": self.signup_status.value,
            "signin_status": self.signin_status.value,
            "apikey_status": self.apikey_status.value,
            "implementation_progress": self.implementation_progress,
            "priority": self.priority,
            "estimated_hours": self.estimated_hours,
            "has_official_api": self.has_official_api,
            "api_documentation_url": self.api_documentation_url,
            "api_rate_limits": self.api_rate_limits,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "last_tested": self.last_tested.isoformat() if self.last_tested else None,
            "notes": self.notes
        } 