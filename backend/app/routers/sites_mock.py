"""
Mock Sites router for testing frontend functionality.
This provides sample data while database connectivity issues are resolved.
"""

from fastapi import APIRouter, Query
from typing import List, Optional
from pydantic import BaseModel

router = APIRouter(prefix="/api/v1/sites", tags=["Sites Management"])

# Mock data models
class SiteResponse(BaseModel):
    id: int
    name: str
    display_name: str
    url: str
    logo_url: Optional[str]
    category: str
    description: Optional[str]
    signup_difficulty: str
    signin_difficulty: str
    apikey_difficulty: str
    overall_difficulty: str
    requires_email_verification: bool
    requires_phone_verification: bool
    requires_sms_verification: bool
    requires_authenticator: bool
    has_captcha: bool
    captcha_type: Optional[str]
    anti_bot_techniques: List[str]
    signup_status: str
    signin_status: str
    apikey_status: str
    implementation_progress: float
    priority: int
    estimated_hours: Optional[int]
    has_official_api: bool
    api_documentation_url: Optional[str]
    api_rate_limits: Optional[str]
    notes: Optional[str]
    created_at: Optional[str]
    updated_at: Optional[str]

# Mock data
MOCK_SITES = [
    {
        "id": 1,
        "name": "google",
        "display_name": "Google",
        "url": "https://google.com",
        "logo_url": "https://www.google.com/favicon.ico",
        "category": "tech-giant",
        "description": "Search engine and tech giant with complex authentication",
        "signup_difficulty": "extreme",
        "signin_difficulty": "hard",
        "apikey_difficulty": "hard",
        "overall_difficulty": "extreme",
        "requires_email_verification": True,
        "requires_phone_verification": True,
        "requires_sms_verification": False,
        "requires_authenticator": True,
        "has_captcha": True,
        "captcha_type": "recaptcha",
        "anti_bot_techniques": ["fingerprinting", "behavioral_analysis"],
        "signup_status": "in_progress",
        "signin_status": "completed",
        "apikey_status": "not_started",
        "implementation_progress": 33.3,
        "priority": 100,
        "estimated_hours": 40,
        "has_official_api": True,
        "api_documentation_url": "https://developers.google.com",
        "api_rate_limits": "Varies by service",
        "notes": "Complex authentication flow with multiple verification steps",
        "created_at": "2024-01-01T00:00:00Z",
        "updated_at": "2024-01-15T10:30:00Z"
    },
    {
        "id": 2,
        "name": "github",
        "display_name": "GitHub",
        "url": "https://github.com",
        "logo_url": "https://github.com/favicon.ico",
        "category": "developer-tools",
        "description": "Code hosting and collaboration platform",
        "signup_difficulty": "easy",
        "signin_difficulty": "easy",
        "apikey_difficulty": "easy",
        "overall_difficulty": "easy",
        "requires_email_verification": True,
        "requires_phone_verification": False,
        "requires_sms_verification": False,
        "requires_authenticator": False,
        "has_captcha": False,
        "captcha_type": None,
        "anti_bot_techniques": [],
        "signup_status": "completed",
        "signin_status": "completed",
        "apikey_status": "completed",
        "implementation_progress": 100.0,
        "priority": 85,
        "estimated_hours": 8,
        "has_official_api": True,
        "api_documentation_url": "https://docs.github.com/en/rest",
        "api_rate_limits": "5000 requests/hour",
        "notes": "Well documented API with straightforward authentication",
        "created_at": "2024-01-02T00:00:00Z",
        "updated_at": "2024-01-10T14:20:00Z"
    },
    {
        "id": 3,
        "name": "aws",
        "display_name": "Amazon Web Services",
        "url": "https://aws.amazon.com",
        "logo_url": "https://aws.amazon.com/favicon.ico",
        "category": "cloud-provider",
        "description": "Leading cloud computing platform",
        "signup_difficulty": "hard",
        "signin_difficulty": "medium",
        "apikey_difficulty": "medium",
        "overall_difficulty": "hard",
        "requires_email_verification": True,
        "requires_phone_verification": True,
        "requires_sms_verification": True,
        "requires_authenticator": False,
        "has_captcha": True,
        "captcha_type": "recaptcha",
        "anti_bot_techniques": ["device_fingerprinting"],
        "signup_status": "not_started",
        "signin_status": "not_started",
        "apikey_status": "not_started",
        "implementation_progress": 0.0,
        "priority": 95,
        "estimated_hours": 25,
        "has_official_api": True,
        "api_documentation_url": "https://docs.aws.amazon.com",
        "api_rate_limits": "Varies by service",
        "notes": "Requires credit card verification and complex setup",
        "created_at": "2024-01-03T00:00:00Z",
        "updated_at": "2024-01-03T00:00:00Z"
    },
    {
        "id": 4,
        "name": "openai",
        "display_name": "OpenAI",
        "url": "https://openai.com",
        "logo_url": "https://openai.com/favicon.ico",
        "category": "ai-ml",
        "description": "AI research and deployment company",
        "signup_difficulty": "medium",
        "signin_difficulty": "easy",
        "apikey_difficulty": "easy",
        "overall_difficulty": "medium",
        "requires_email_verification": True,
        "requires_phone_verification": True,
        "requires_sms_verification": False,
        "requires_authenticator": False,
        "has_captcha": False,
        "captcha_type": None,
        "anti_bot_techniques": [],
        "signup_status": "completed",
        "signin_status": "completed",
        "apikey_status": "in_progress",
        "implementation_progress": 66.7,
        "priority": 90,
        "estimated_hours": 12,
        "has_official_api": True,
        "api_documentation_url": "https://platform.openai.com/docs",
        "api_rate_limits": "Rate limits by tier",
        "notes": "Phone verification required for API access",
        "created_at": "2024-01-04T00:00:00Z",
        "updated_at": "2024-01-12T09:15:00Z"
    },
    {
        "id": 5,
        "name": "linkedin",
        "display_name": "LinkedIn",
        "url": "https://linkedin.com",
        "logo_url": "https://linkedin.com/favicon.ico",
        "category": "social-media",
        "description": "Professional networking platform",
        "signup_difficulty": "hard",
        "signin_difficulty": "medium",
        "apikey_difficulty": "hard",
        "overall_difficulty": "hard",
        "requires_email_verification": True,
        "requires_phone_verification": True,
        "requires_sms_verification": False,
        "requires_authenticator": False,
        "has_captcha": True,
        "captcha_type": "custom",
        "anti_bot_techniques": ["behavioral_analysis", "device_fingerprinting"],
        "signup_status": "failed",
        "signin_status": "in_progress",
        "apikey_status": "blocked",
        "implementation_progress": 16.7,
        "priority": 80,
        "estimated_hours": 30,
        "has_official_api": True,
        "api_documentation_url": "https://docs.microsoft.com/en-us/linkedin",
        "api_rate_limits": "Strict rate limiting",
        "notes": "Strong anti-bot measures, requires careful approach",
        "created_at": "2024-01-05T00:00:00Z",
        "updated_at": "2024-01-14T16:45:00Z"
    },
    {
        "id": 6,
        "name": "microsoft",
        "display_name": "Microsoft",
        "url": "https://microsoft.com",
        "logo_url": "https://microsoft.com/favicon.ico",
        "category": "tech-giant",
        "description": "Technology corporation and cloud services provider",
        "signup_difficulty": "hard",
        "signin_difficulty": "medium",
        "apikey_difficulty": "medium",
        "overall_difficulty": "hard",
        "requires_email_verification": True,
        "requires_phone_verification": True,
        "requires_sms_verification": False,
        "requires_authenticator": True,
        "has_captcha": True,
        "captcha_type": "recaptcha",
        "anti_bot_techniques": ["device_fingerprinting"],
        "signup_status": "not_started",
        "signin_status": "not_started",
        "apikey_status": "not_started",
        "implementation_progress": 0.0,
        "priority": 95,
        "estimated_hours": 35,
        "has_official_api": True,
        "api_documentation_url": "https://docs.microsoft.com",
        "api_rate_limits": "Varies by service",
        "notes": "Azure AD integration required",
        "created_at": "2024-01-06T00:00:00Z",
        "updated_at": "2024-01-06T00:00:00Z"
    }
]

MOCK_CATEGORIES = [
    {"name": "tech-giant", "count": 10},
    {"name": "cloud-provider", "count": 15},
    {"name": "developer-tools", "count": 25},
    {"name": "social-media", "count": 20},
    {"name": "ai-ml", "count": 12},
    {"name": "finance", "count": 18}
]

MOCK_STATS = {
    "total_sites": 199,
    "categories": MOCK_CATEGORIES,
    "implementation_progress": {
        "signup_completed": 45,
        "signin_completed": 52,
        "apikey_completed": 38,
        "total_completed": 67
    },
    "difficulty_distribution": {
        "easy": 45,
        "medium": 89,
        "hard": 52,
        "extreme": 13
    },
    "estimated_total_hours": 2847
}

@router.get("/categories")
async def list_categories():
    """Get list of all categories."""
    return MOCK_CATEGORIES

@router.get("/stats/overview")
async def get_sites_overview():
    """Get overview statistics of sites."""
    return MOCK_STATS

@router.get("/", response_model=List[SiteResponse])
async def list_sites(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    category: Optional[str] = Query(None),
    difficulty: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    priority_min: Optional[int] = Query(None, ge=1, le=100),
    search: Optional[str] = Query(None),
    sort_by: str = Query("priority", regex="^(name|priority|difficulty|progress|created_at)$"),
    sort_order: str = Query("desc", regex="^(asc|desc)$")
):
    """Get list of sites with filtering and pagination."""
    
    # Apply basic filtering for demo
    filtered_sites = MOCK_SITES.copy()
    
    if search:
        search_lower = search.lower()
        filtered_sites = [
            site for site in filtered_sites 
            if search_lower in site["name"].lower() or 
               search_lower in site["display_name"].lower() or
               search_lower in site["description"].lower()
        ]
    
    if category:
        filtered_sites = [site for site in filtered_sites if site["category"] == category]
    
    if priority_min:
        filtered_sites = [site for site in filtered_sites if site["priority"] >= priority_min]
    
    if difficulty:
        filtered_sites = [
            site for site in filtered_sites 
            if site["signup_difficulty"] == difficulty or 
               site["signin_difficulty"] == difficulty or 
               site["apikey_difficulty"] == difficulty
        ]
    
    # Apply sorting
    if sort_by == "priority":
        filtered_sites.sort(key=lambda x: x["priority"], reverse=(sort_order == "desc"))
    elif sort_by == "name":
        filtered_sites.sort(key=lambda x: x["name"], reverse=(sort_order == "desc"))
    
    # Apply pagination
    start_idx = skip
    end_idx = skip + limit
    paginated_sites = filtered_sites[start_idx:end_idx]
    
    return paginated_sites

@router.get("/{site_id}", response_model=SiteResponse)
async def get_site(site_id: int):
    """Get specific site by ID."""
    for site in MOCK_SITES:
        if site["id"] == site_id:
            return site
    
    from fastapi import HTTPException
    raise HTTPException(status_code=404, detail="Site not found") 