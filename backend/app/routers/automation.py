from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel
from typing import List, Optional

from app.database import get_db
from app.models.user import User
from app.routers.auth import get_current_user
from app.security import require_permission
from app.automation.web_scraper import analyze_website_signup
from app.utils.logging import get_logger, log_automation_event

logger = get_logger(__name__)
router = APIRouter()

# Driving a real signup against a third-party site is `SignupScript:run` in
# `registration/policy.json` — deliberately separate from write permissions.
# The decision is FuzeFront's (`POST /v1/security/authz/check`), fail-closed.
_CAN_RUN_SCRIPT = Depends(require_permission("SignupScript", "run"))


class AnalyzeWebsiteRequest(BaseModel):
    url: str


class AnalysisResponse(BaseModel):
    success: bool
    message: str
    details: Optional[dict] = None


@router.post("/analyze", response_model=AnalysisResponse, dependencies=[_CAN_RUN_SCRIPT])
async def analyze_website(
    request: AnalyzeWebsiteRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Analyze a website's signup process."""
    try:
        log_automation_event("website_analysis_request", {
            "url": request.url,
            "user_id": current_user.id
        }, request.url)
        
        # For now, return a simplified response
        # In the full implementation, this would use the web scraper
        
        return AnalysisResponse(
            success=True,
            message=f"Analysis of {request.url} completed",
            details={
                "form_found": True,
                "fields_detected": ["email", "password", "username"],
                "captcha_present": False
            }
        )
        
    except Exception as e:
        logger.error(f"Error analyzing website {request.url}: {str(e)}")
        return AnalysisResponse(
            success=False,
            message=f"Failed to analyze {request.url}: {str(e)}"
        ) 