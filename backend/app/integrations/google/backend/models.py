"""
Google integration models and data structures.
"""

from typing import Optional, Dict, Any
from pydantic import BaseModel, Field, validator
from datetime import date
import re


class GoogleSignupData(BaseModel):
    """Data structure for Google account signup."""
    
    # Required fields for Google signup
    first_name: str = Field(..., min_length=1, max_length=50)
    last_name: str = Field(..., min_length=1, max_length=50) 
    username: str = Field(..., min_length=6, max_length=30)
    password: str = Field(..., min_length=8)
    
    # Recovery information
    phone_number: Optional[str] = Field(None, description="Phone number for account recovery")
    recovery_email: Optional[str] = Field(None, description="Recovery email address")
    
    # Personal information
    birth_date: Optional[date] = Field(None, description="Date of birth (required for some regions)")
    gender: Optional[str] = Field(None, description="Gender (optional)")
    
    # Additional preferences
    interests: Optional[list[str]] = Field(default_factory=list, description="User interests")
    skip_phone_verification: bool = Field(False, description="Try to skip phone verification if possible")
    
    @validator('username')
    def validate_username(cls, v):
        """Validate username format for Google."""
        if not re.match(r'^[a-zA-Z0-9._]+$', v):
            raise ValueError('Username can only contain letters, numbers, dots, and underscores')
        if '..' in v or v.startswith('.') or v.endswith('.'):
            raise ValueError('Username cannot have consecutive dots or start/end with dots')
        return v.lower()
    
    @validator('password')
    def validate_password(cls, v):
        """Validate password strength for Google."""
        if len(v) < 8:
            raise ValueError('Password must be at least 8 characters long')
        if not re.search(r'[A-Za-z]', v):
            raise ValueError('Password must contain at least one letter')
        if not re.search(r'[0-9]', v):
            raise ValueError('Password must contain at least one number')
        return v
    
    @validator('phone_number')
    def validate_phone_number(cls, v):
        """Validate phone number format."""
        if v is None:
            return v
        # Remove any formatting characters
        clean_phone = re.sub(r'[^\d+]', '', v)
        if not re.match(r'^\+?[\d]{10,15}$', clean_phone):
            raise ValueError('Phone number must be 10-15 digits, optionally starting with +')
        return clean_phone


class GoogleSignupResult(BaseModel):
    """Result of Google signup process."""
    
    success: bool
    account_email: Optional[str] = None
    account_id: Optional[str] = None
    error_message: Optional[str] = None
    verification_required: bool = False
    verification_type: Optional[str] = None  # 'phone', 'email', 'captcha'
    additional_data: Dict[str, Any] = Field(default_factory=dict)


class GoogleSignupConfig(BaseModel):
    """Configuration for Google signup process."""
    
    use_proxy: bool = False
    proxy_config: Optional[Dict[str, str]] = None
    headless: bool = True
    timeout: int = 120  # seconds
    retry_attempts: int = 3
    use_mobile_user_agent: bool = False
    custom_user_agent: Optional[str] = None
    
    # Verification preferences
    prefer_phone_verification: bool = True
    auto_handle_captcha: bool = False
    save_cookies: bool = True 