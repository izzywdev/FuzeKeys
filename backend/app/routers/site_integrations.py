"""
Site integrations router for FuzeKeys.

This router provides API endpoints for managing automated site integrations
including signup, signin, and API key creation for various platforms.
"""

from fastapi import APIRouter, HTTPException, BackgroundTasks, Depends
from pydantic import BaseModel, EmailStr
from typing import Dict, Any, List, Optional
import logging

from app.integrations.site import get_available_sites, get_site_capabilities
from app.integrations.site.permit_io import PermitIOIntegration
from app.integrations.site.permit_io.models import PermitIOCredentials, PermitIOResult
from app.models.user import User
from app.routers.auth import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/integrations", tags=["Site Integrations"])

# Request/Response Models
class SignupRequest(BaseModel):
    site: str
    email: EmailStr
    password: str
    first_name: str
    last_name: str
    company_name: Optional[str] = None
    phone: Optional[str] = None
    job_title: Optional[str] = None
    headless: bool = True

class SigninRequest(BaseModel):
    site: str
    email: EmailStr
    password: str
    headless: bool = True

class ApiKeyRequest(BaseModel):
    site: str
    email: EmailStr
    password: str
    key_name: str = "FuzeKeys"
    headless: bool = True

class IntegrationResponse(BaseModel):
    success: bool
    message: str
    data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    site: str

# Available Sites Endpoints
@router.get("/sites", response_model=Dict[str, List[str]])
async def list_available_sites():
    """Get a list of all available site integrations."""
    try:
        sites = get_available_sites()
        return {
            "sites": sites,
            "count": len(sites)
        }
    except Exception as e:
        logger.error(f"Failed to list sites: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to retrieve available sites")

@router.get("/sites/{site_name}/capabilities")
async def get_site_capabilities_endpoint(site_name: str):
    """Get the capabilities of a specific site integration."""
    try:
        capabilities = get_site_capabilities(site_name)
        return {
            "site": site_name,
            "capabilities": capabilities
        }
    except Exception as e:
        logger.error(f"Failed to get capabilities for {site_name}: {str(e)}")
        raise HTTPException(status_code=404, detail=f"Site '{site_name}' not found")

# Site Integration Operations
@router.post("/signup", response_model=IntegrationResponse)
async def create_account(
    request: SignupRequest,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
):
    """
    Create a new account on the specified site.

    This endpoint handles automated account signup for supported sites.
    The operation runs in the background for long-running automations.

    SECURITY (HIGH-1 / appsec #18): requires auth. This drives credential-bearing
    browser automation against external sites; an unauthenticated caller must not
    be able to trigger it (abuse / resource exhaustion).
    """
    try:
        if request.site.lower() == "permit.io":
            return await handle_permit_io_signup(request)
        else:
            raise HTTPException(
                status_code=400, 
                detail=f"Site '{request.site}' is not supported for signup"
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Signup failed for {request.site}: {str(e)}")
        raise HTTPException(status_code=500, detail="Account creation failed")

@router.post("/signin", response_model=IntegrationResponse)
async def authenticate_account(
    request: SigninRequest,
    current_user: User = Depends(get_current_user),
):
    """
    Authenticate with an existing account on the specified site.

    This endpoint handles automated authentication for supported sites.

    SECURITY (HIGH-1 / appsec #18): requires auth. This accepts raw email+password
    and drives credential-bearing browser automation against external sites; an
    unauthenticated caller must not be able to trigger it (abuse / resource
    exhaustion / credential-stuffing surface).
    """
    try:
        if request.site.lower() == "permit.io":
            return await handle_permit_io_signin(request)
        else:
            raise HTTPException(
                status_code=400, 
                detail=f"Site '{request.site}' is not supported for signin"
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Signin failed for {request.site}: {str(e)}")
        raise HTTPException(status_code=500, detail="Authentication failed")

@router.post("/apikey", response_model=IntegrationResponse)
async def create_api_key(
    request: ApiKeyRequest,
    current_user: User = Depends(get_current_user),
):
    """
    Create an API key for the specified site account.

    This endpoint handles automated API key creation for supported sites.

    SECURITY (HIGH-1 / appsec #18): requires auth. This accepts raw email+password
    and drives credential-bearing browser automation against external sites; an
    unauthenticated caller must not be able to trigger it.
    """
    try:
        if request.site.lower() == "permit.io":
            return await handle_permit_io_apikey(request)
        else:
            raise HTTPException(
                status_code=400, 
                detail=f"Site '{request.site}' is not supported for API key creation"
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"API key creation failed for {request.site}: {str(e)}")
        raise HTTPException(status_code=500, detail="API key creation failed")

# Permit.io specific handlers
async def handle_permit_io_signup(request: SignupRequest) -> IntegrationResponse:
    """Handle permit.io account signup."""
    try:
        credentials = PermitIOCredentials(
            email=str(request.email),
            password=request.password,
            first_name=request.first_name,
            last_name=request.last_name,
            company_name=request.company_name,
            phone=request.phone,
            job_title=request.job_title
        )
        
        integration = PermitIOIntegration(headless=request.headless)
        result = await integration.signup_account(credentials)
        
        return IntegrationResponse(
            success=result.success,
            message=result.message,
            data=result.data,
            error=result.error,
            site="permit.io"
        )
    except Exception as e:
        logger.error(f"Permit.io signup failed: {str(e)}")
        return IntegrationResponse(
            success=False,
            message="Signup automation failed",
            error=str(e),
            site="permit.io"
        )

async def handle_permit_io_signin(request: SigninRequest) -> IntegrationResponse:
    """Handle permit.io account signin."""
    try:
        integration = PermitIOIntegration(headless=request.headless)
        result = await integration.signin_account(str(request.email), request.password)
        
        return IntegrationResponse(
            success=result.success,
            message=result.message,
            data=result.data,
            error=result.error,
            site="permit.io"
        )
    except Exception as e:
        logger.error(f"Permit.io signin failed: {str(e)}")
        return IntegrationResponse(
            success=False,
            message="Signin automation failed",
            error=str(e),
            site="permit.io"
        )

async def handle_permit_io_apikey(request: ApiKeyRequest) -> IntegrationResponse:
    """Handle permit.io API key creation."""
    try:
        integration = PermitIOIntegration(headless=request.headless)
        result = await integration.create_api_key(
            str(request.email), 
            request.password, 
            request.key_name
        )
        
        return IntegrationResponse(
            success=result.success,
            message=result.message,
            data=result.data,
            error=result.error,
            site="permit.io"
        )
    except Exception as e:
        logger.error(f"Permit.io API key creation failed: {str(e)}")
        return IntegrationResponse(
            success=False,
            message="API key creation automation failed",
            error=str(e),
            site="permit.io"
        )

# Health check for integrations
@router.get("/health")
async def integration_health_check():
    """Health check endpoint for site integrations."""
    try:
        sites = get_available_sites()
        return {
            "status": "healthy",
            "available_sites": sites,
            "timestamp": "2024-06-15T14:00:00Z"
        }
    except Exception as e:
        logger.error(f"Integration health check failed: {str(e)}")
        raise HTTPException(status_code=503, detail="Service unavailable") 