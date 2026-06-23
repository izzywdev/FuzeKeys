"""
Sites router for managing automation target sites.

This router provides CRUD operations for the sites database,
including importing from CSV and managing implementation status.
"""

from fastapi import APIRouter, HTTPException, Depends, UploadFile, File, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import func, desc, asc, select
from typing import List, Optional, Dict, Any
from pydantic import BaseModel
import csv
import io
import json
import logging

from app.database import get_async_session
from app.models.site import Site, DifficultyLevel, ImplementationStatus

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/sites", tags=["Sites Management"])

# Pydantic models for API
class SiteCreate(BaseModel):
    name: str
    display_name: str
    url: str
    logo_url: Optional[str] = None
    category: str
    description: Optional[str] = None
    signup_difficulty: DifficultyLevel = DifficultyLevel.MEDIUM
    signin_difficulty: DifficultyLevel = DifficultyLevel.EASY
    apikey_difficulty: DifficultyLevel = DifficultyLevel.MEDIUM
    requires_email_verification: bool = True
    requires_phone_verification: bool = False
    requires_sms_verification: bool = False
    requires_authenticator: bool = False
    has_captcha: bool = False
    captcha_type: Optional[str] = None
    anti_bot_techniques: List[str] = []
    priority: int = 50
    estimated_hours: Optional[int] = None
    has_official_api: bool = True
    api_documentation_url: Optional[str] = None
    api_rate_limits: Optional[str] = None
    notes: Optional[str] = None

class SiteUpdate(BaseModel):
    display_name: Optional[str] = None
    url: Optional[str] = None
    logo_url: Optional[str] = None
    category: Optional[str] = None
    description: Optional[str] = None
    signup_difficulty: Optional[DifficultyLevel] = None
    signin_difficulty: Optional[DifficultyLevel] = None
    apikey_difficulty: Optional[DifficultyLevel] = None
    requires_email_verification: Optional[bool] = None
    requires_phone_verification: Optional[bool] = None
    requires_sms_verification: Optional[bool] = None
    requires_authenticator: Optional[bool] = None
    has_captcha: Optional[bool] = None
    captcha_type: Optional[str] = None
    anti_bot_techniques: Optional[List[str]] = None
    signup_status: Optional[ImplementationStatus] = None
    signin_status: Optional[ImplementationStatus] = None
    apikey_status: Optional[ImplementationStatus] = None
    priority: Optional[int] = None
    estimated_hours: Optional[int] = None
    has_official_api: Optional[bool] = None
    api_documentation_url: Optional[str] = None
    api_rate_limits: Optional[str] = None
    notes: Optional[str] = None

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

class ImportResult(BaseModel):
    success: bool
    imported_count: int
    skipped_count: int
    errors: List[str]
    message: str

# CRUD Operations
@router.get("/categories")
async def list_categories(db: AsyncSession = Depends(get_async_session)):
    """Get list of all categories."""
    # Return mock data for now to test frontend
    return [
        {"name": "tech-giant", "count": 10},
        {"name": "cloud-provider", "count": 15},
        {"name": "developer-tools", "count": 25},
        {"name": "social-media", "count": 20},
        {"name": "ai-ml", "count": 12},
        {"name": "finance", "count": 18}
    ]

# Statistics and analytics
@router.get("/stats/overview")
async def get_sites_overview(db: AsyncSession = Depends(get_async_session)):
    """Get overview statistics of sites."""
    # Return mock data for now to test frontend
    return {
        "total_sites": 199,
        "categories": [
            {"name": "tech-giant", "count": 10},
            {"name": "cloud-provider", "count": 15},
            {"name": "developer-tools", "count": 25},
            {"name": "social-media", "count": 20},
            {"name": "ai-ml", "count": 12},
            {"name": "finance", "count": 18}
        ],
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

@router.get("/", response_model=List[SiteResponse])
async def list_sites(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    category: Optional[str] = Query(None),
    difficulty: Optional[DifficultyLevel] = Query(None),
    status: Optional[ImplementationStatus] = Query(None),
    priority_min: Optional[int] = Query(None, ge=1, le=100),
    search: Optional[str] = Query(None),
    sort_by: str = Query("priority", regex="^(name|priority|difficulty|progress|created_at)$"),
    sort_order: str = Query("desc", regex="^(asc|desc)$"),
    db: AsyncSession = Depends(get_async_session)
):
    """Get list of sites with filtering and pagination."""
    # Return mock data for now to test frontend
    mock_sites = [
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
    
    # Apply basic filtering for demo
    filtered_sites = mock_sites
    
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
    
    # Apply pagination
    start_idx = skip
    end_idx = skip + limit
    paginated_sites = filtered_sites[start_idx:end_idx]
    
    return paginated_sites

@router.get("/name/{site_name}", response_model=SiteResponse)
async def get_site_by_name(site_name: str, db: AsyncSession = Depends(get_async_session)):
    """Get specific site by name."""
    site = await db.get(Site, Site.name == site_name)
    if not site:
        raise HTTPException(status_code=404, detail="Site not found")
    
    return SiteResponse(**site.to_dict())

@router.get("/{site_id}", response_model=SiteResponse)
async def get_site(site_id: int, db: AsyncSession = Depends(get_async_session)):
    """Get specific site by ID."""
    site = await db.get(Site, Site.id == site_id)
    if not site:
        raise HTTPException(status_code=404, detail="Site not found")
    
    return SiteResponse(**site.to_dict())

@router.post("/", response_model=SiteResponse)
async def create_site(site_data: SiteCreate, db: AsyncSession = Depends(get_async_session)):
    """Create a new site."""
    try:
        # Check if site name already exists
        existing = await db.get(Site, Site.name == site_data.name)
        if existing:
            raise HTTPException(status_code=400, detail="Site with this name already exists")
        
        site = Site(**site_data.dict())
        db.add(site)
        await db.commit()
        await db.refresh(site)
        
        return SiteResponse(**site.to_dict())
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating site: {str(e)}")
        await db.rollback()
        raise HTTPException(status_code=500, detail="Failed to create site")

@router.put("/{site_id}", response_model=SiteResponse)
async def update_site(site_id: int, site_data: SiteUpdate, db: AsyncSession = Depends(get_async_session)):
    """Update an existing site."""
    try:
        site = await db.get(Site, Site.id == site_id)
        if not site:
            raise HTTPException(status_code=404, detail="Site not found")
        
        # Update only provided fields
        update_data = site_data.dict(exclude_unset=True)
        for field, value in update_data.items():
            setattr(site, field, value)
        
        await db.commit()
        await db.refresh(site)
        
        return SiteResponse(**site.to_dict())
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating site: {str(e)}")
        await db.rollback()
        raise HTTPException(status_code=500, detail="Failed to update site")

@router.delete("/{site_id}")
async def delete_site(site_id: int, db: AsyncSession = Depends(get_async_session)):
    """Delete a site."""
    try:
        site = await db.get(Site, Site.id == site_id)
        if not site:
            raise HTTPException(status_code=404, detail="Site not found")
        
        await db.delete(site)
        await db.commit()
        
        return {"message": "Site deleted successfully"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting site: {str(e)}")
        await db.rollback()
        raise HTTPException(status_code=500, detail="Failed to delete site")

# Import/Export operations
@router.post("/import", response_model=ImportResult)
async def import_sites_csv(
    file: UploadFile = File(...),
    overwrite: bool = Query(False, description="Overwrite existing sites"),
    db: AsyncSession = Depends(get_async_session)
):
    """Import sites from CSV file."""
    try:
        if not file.filename.endswith('.csv'):
            raise HTTPException(status_code=400, detail="File must be a CSV")
        
        # Read CSV content
        content = await file.read()
        csv_data = csv.DictReader(io.StringIO(content.decode('utf-8')))
        
        imported_count = 0
        skipped_count = 0
        errors = []
        
        for row_num, row in enumerate(csv_data, start=2):  # Start at 2 for header
            try:
                # Check if site exists
                existing = await db.get(Site, Site.name == row['name'])
                if existing and not overwrite:
                    skipped_count += 1
                    continue
                
                # Parse anti_bot_techniques JSON
                try:
                    anti_bot_techniques = json.loads(row.get('anti_bot_techniques', '[]'))
                except json.JSONDecodeError:
                    anti_bot_techniques = []
                
                # Create site data
                site_data = {
                    'name': row['name'],
                    'display_name': row['display_name'],
                    'url': row['url'],
                    'logo_url': row.get('logo_url'),
                    'category': row['category'],
                    'description': row.get('description'),
                    'signup_difficulty': DifficultyLevel(row.get('signup_difficulty', 'medium')),
                    'signin_difficulty': DifficultyLevel(row.get('signin_difficulty', 'easy')),
                    'apikey_difficulty': DifficultyLevel(row.get('apikey_difficulty', 'medium')),
                    'requires_email_verification': row.get('requires_email_verification', 'true').lower() == 'true',
                    'requires_phone_verification': row.get('requires_phone_verification', 'false').lower() == 'true',
                    'requires_sms_verification': row.get('requires_sms_verification', 'false').lower() == 'true',
                    'requires_authenticator': row.get('requires_authenticator', 'false').lower() == 'true',
                    'has_captcha': row.get('has_captcha', 'false').lower() == 'true',
                    'captcha_type': row.get('captcha_type') or None,
                    'anti_bot_techniques': anti_bot_techniques,
                    'signup_status': ImplementationStatus(row.get('signup_status', 'not_started')),
                    'signin_status': ImplementationStatus(row.get('signin_status', 'not_started')),
                    'apikey_status': ImplementationStatus(row.get('apikey_status', 'not_started')),
                    'priority': int(row.get('priority', 50)),
                    'estimated_hours': int(row['estimated_hours']) if row.get('estimated_hours') else None,
                    'has_official_api': row.get('has_official_api', 'true').lower() == 'true',
                    'api_documentation_url': row.get('api_documentation_url') or None,
                    'api_rate_limits': row.get('api_rate_limits') or None,
                    'notes': row.get('notes') or None
                }
                
                if existing and overwrite:
                    # Update existing site
                    for field, value in site_data.items():
                        setattr(existing, field, value)
                else:
                    # Create new site
                    site = Site(**site_data)
                    db.add(site)
                
                imported_count += 1
                
            except Exception as row_error:
                errors.append(f"Row {row_num}: {str(row_error)}")
                continue
        
        await db.commit()
        
        return ImportResult(
            success=True,
            imported_count=imported_count,
            skipped_count=skipped_count,
            errors=errors,
            message=f"Successfully imported {imported_count} sites, skipped {skipped_count}"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error importing CSV: {str(e)}")
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to import CSV: {str(e)}") 