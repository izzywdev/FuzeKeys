"""
Data models for permit.io integration.
"""

from dataclasses import dataclass
from typing import Optional, Dict, Any
from datetime import datetime

@dataclass
class PermitIOCredentials:
    """User credentials for permit.io account creation."""
    email: str
    password: str
    first_name: str
    last_name: str
    company_name: Optional[str] = None
    phone: Optional[str] = None
    job_title: Optional[str] = None

@dataclass
class PermitIOResult:
    """Result of a permit.io automation operation."""
    success: bool
    message: str
    data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    timestamp: datetime = None
    screenshots: Optional[list] = None
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.utcnow()

@dataclass
class PermitIOAccountInfo:
    """Information about a permit.io account."""
    email: str
    account_id: Optional[str] = None
    workspace_id: Optional[str] = None
    api_keys: Optional[list] = None
    subscription_plan: Optional[str] = None
    created_at: Optional[datetime] = None
    last_login: Optional[datetime] = None

@dataclass
class PermitIOApiKey:
    """Permit.io API key information."""
    key_id: str
    name: str
    key_value: str
    permissions: Optional[list] = None
    created_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    is_active: bool = True

@dataclass
class PermitIOSessionInfo:
    """Information about an active permit.io session."""
    session_id: str
    user_id: str
    workspace_id: str
    csrf_token: Optional[str] = None
    cookies: Optional[Dict[str, str]] = None
    expires_at: Optional[datetime] = None 