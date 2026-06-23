from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
import os
from dotenv import load_dotenv

from app.routers import auth, identities, accounts, automation, chat, sms, infrastructure, llm_scraper, credentials, google_integration, site_integrations
# Temporarily use mock sites router
# from app.routers import sites
from app.utils.logging import setup_logging

# Load environment variables
load_dotenv()

# Setup logging
setup_logging()

# Mock sites router for testing
from fastapi import APIRouter, Query
from typing import List, Optional
from pydantic import BaseModel

# Create mock sites router
sites_router = APIRouter(prefix="/api/v1/sites", tags=["Sites Management"])

# Define tags metadata for OpenAPI documentation
tags_metadata = [
    {
        "name": "Sites Management",
        "description": "Operations for managing automation target sites",
    },
    {
        "name": "Authentication",
        "description": "User authentication and authorization",
    },
    {
        "name": "Identities",
        "description": "Digital identity management",
    },
    {
        "name": "Accounts",
        "description": "Account creation and management",
    },
    {
        "name": "Automation",
        "description": "Automation script execution",
    },
    {
        "name": "Chat",
        "description": "AI chat interface",
    },
    {
        "name": "SMS",
        "description": "SMS and mobile integration",
    },
    {
        "name": "Infrastructure",
        "description": "Infrastructure management",
    },
    {
        "name": "LLM Scraper",
        "description": "AI-powered scraper generation",
    },
    {
        "name": "Credentials",
        "description": "Secure credential management",
    },
    {
        "name": "Google Integration",
        "description": "Google services integration",
    },
    {
        "name": "Site Integrations",
        "description": "Website integration management",
    },
    {
        "name": "Demo",
        "description": "Demo endpoints for testing",
    },
]

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

@sites_router.get("/categories")
async def list_categories():
    """Get list of all categories."""
    return MOCK_CATEGORIES

@sites_router.get("/stats/overview")
async def get_sites_overview():
    """Get overview statistics of sites."""
    return MOCK_STATS

@sites_router.get("/", response_model=List[SiteResponse])
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

@sites_router.get("/{site_id}", response_model=SiteResponse)
async def get_site(site_id: int):
    """Get specific site by ID."""
    for site in MOCK_SITES:
        if site["id"] == site_id:
            return site
    
    from fastapi import HTTPException
    raise HTTPException(status_code=404, detail="Site not found")

# Create FastAPI application
app = FastAPI(
    title="FuzeKeys API",
    description="""
## 🚀 Intelligent Identity & Account Management System

**FuzeKeys** is a comprehensive platform for managing digital identities and automating account creation across multiple websites using AI-powered scraper generation and site integrations.

### 🎯 Key Features

* **🔐 Secure Credential Management**: Generate, store, and retrieve credentials for microservices
* **🤖 LLM-Driven Scraper Generation**: AI-powered automation script creation with continuous improvement
* **📱 Mobile Integration**: SMS OTP interception and mobile device communication
* **🛡️ Identity Protection**: Encrypted storage of personal information and credentials
* **⚡ Docker Isolation**: Secure scraper execution in containerized environments
* **📊 Continuous Validation**: Automated testing and quality assurance
* **🔄 Production Deployment**: Automatic deployment pipeline with rollback capabilities

### 🏗️ Architecture

```
User Identity → Credential Generation → AI Scraper Creation → Docker Execution → Production Deployment
     ↓                 ↓                      ↓                    ↓                    ↓
  Encrypted        API Security         LLM Integration      Container Isolation    Health Monitoring
```

### 🔑 API Authentication

Most endpoints require authentication. Use the appropriate API key in the `X-API-Key` header:

* **Scraper Service**: `scraper-key-12345`
* **Mobile Service**: `mobile-key-12345`  
* **Automation Service**: `automation-key-12345`

### 📱 Mobile Integration

The system integrates with Android devices for SMS OTP interception and mobile automation.

### 🤖 AI-Powered Features

* **Intelligent Scraper Generation**: LLMs analyze websites and generate automation scripts
* **Continuous Improvement**: AI iteratively improves scrapers based on success rates
* **Smart Error Handling**: AI analyzes failures and generates fixes
* **Production Optimization**: Automated performance tuning and deployment decisions

---

**Start with the Credentials API for secure credential management or the LLM Scraper API for AI-powered automation.**
    """,
    version="2.0.0",
    terms_of_service="https://fuzekeys.example.com/terms/",
    contact={
        "name": "FuzeKeys Support",
        "url": "https://fuzekeys.example.com/contact/",
        "email": "support@fuzekeys.example.com",
    },
    license_info={
        "name": "MIT",
        "url": "https://opensource.org/licenses/MIT",
    },
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_tags=tags_metadata,
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Add trusted host middleware for security
app.add_middleware(
    TrustedHostMiddleware, 
    allowed_hosts=["localhost", "127.0.0.1", "*.localhost"]
)

# Include routers
app.include_router(auth.router, prefix="/api/v1/auth", tags=["Authentication"])
app.include_router(identities.router, prefix="/api/v1/identities", tags=["Identities"])
app.include_router(accounts.router, prefix="/api/v1/accounts", tags=["Accounts"])
app.include_router(automation.router, prefix="/api/v1/automation", tags=["Automation"])
app.include_router(chat.router, prefix="/api/v1/chat", tags=["Chat"])
app.include_router(sms.router, tags=["SMS"])
app.include_router(infrastructure.router, tags=["Infrastructure"])
app.include_router(llm_scraper.router, tags=["LLM Scraper"])
app.include_router(credentials.router, tags=["Credentials"])
app.include_router(google_integration.router, tags=["Google Integration"])
app.include_router(site_integrations.router, tags=["Site Integrations"])
app.include_router(sites_router, tags=["Sites Management"])


@app.get("/", 
         summary="API Health Check",
         description="Root endpoint that returns API status and basic information",
         response_description="API status and version information")
async def root():
    """Health check endpoint."""
    return {
        "message": "FuzeKeys API is running",
        "version": "2.0.0",
        "status": "healthy",
        "features": [
            "AI-Powered Scraper Generation",
            "Secure Credential Management", 
            "Mobile Integration",
            "Docker Isolation",
            "Continuous Validation"
        ]
    }


@app.get("/health",
         summary="Detailed Health Check", 
         description="Comprehensive health check with service status details",
         response_description="Detailed health status of all services")
async def health_check():
    """Detailed health check endpoint."""
    from app.database import DATABASE_URL, check_connection
    
    # Detect database type from URL
    if "postgresql" in DATABASE_URL:
        db_type = "PostgreSQL"
    elif "sqlite" in DATABASE_URL:
        db_type = "SQLite"
    else:
        db_type = "Unknown"
    
    # Check database connection
    db_connected = await check_connection()
    db_status = f"connected ({db_type})" if db_connected else f"disconnected ({db_type})"
    
    return {
        "status": "healthy",
        "database": db_status,
        "services": {
            "automation": "available",
            "encryption": "enabled",
            "ai": "connected",
            "docker": "available",
            "mobile": "connected"
        },
        "apis": {
            "credentials": "enabled",
            "llm_scraper": "enabled", 
            "infrastructure": "enabled"
        }
    }


# Demo endpoints (kept for backward compatibility)
@app.get("/api/v1/demo/identities",
         tags=["Demo"],
         summary="Demo Identities",
         description="Sample identity data for testing and demonstration")
async def demo_identities():
    """Demo identities endpoint."""
    return [
        {
            "id": 1,
            "name": "Professional Identity",
            "description": "For business and professional accounts",
            "created_at": "2024-01-01T00:00:00"
        },
        {
            "id": 2,
            "name": "Personal Identity", 
            "description": "For personal social media accounts",
            "created_at": "2024-01-01T00:00:00"
        }
    ]


@app.get("/api/v1/demo/accounts",
         tags=["Demo"],
         summary="Demo Accounts", 
         description="Sample account data for testing and demonstration")
async def demo_accounts():
    """Demo accounts endpoint."""
    return [
        {
            "id": 1,
            "website_name": "GitHub",
            "website_url": "https://github.com",
            "is_active": True,
            "signup_completed": True,
            "created_at": "2024-01-01T00:00:00"
        },
        {
            "id": 2,
            "website_name": "LinkedIn",
            "website_url": "https://linkedin.com", 
            "is_active": True,
            "signup_completed": False,
            "created_at": "2024-01-01T00:00:00"
        }
    ]


@app.post("/api/v1/demo/chat",
          tags=["Demo"],
          summary="Demo Chat",
          description="Demo AI chat interface for testing conversational features")
async def demo_chat(message: dict):
    """Demo chat endpoint."""
    user_message = message.get("message", "")
    
    if "sign me up" in user_message.lower():
        response = "I'd be happy to help you sign up! In the full version, I would analyze the website, create automation scripts, and handle the signup process for you."
    elif "identity" in user_message.lower():
        response = "You can create multiple identities to use for different types of accounts. Each identity can have its own personal information, preferences, and use cases."
    else:
        response = "Hello! I'm the FuzeKeys assistant. I can help you manage identities and automate account creation. Try asking me to 'sign me up for a service' or about 'creating identities'."
    
    return {
        "response": response,
        "action_type": "demo",
        "suggested_actions": [
            "Learn about identities",
            "See demo automation",
            "View sample accounts"
        ]
    }


if __name__ == "__main__":
    import uvicorn
    
    uvicorn.run(
        "app.main:app",
        host=os.getenv("HOST", "localhost"),
        port=int(os.getenv("PORT", 8000)),
        reload=os.getenv("DEBUG", "False").lower() == "true",
    ) 