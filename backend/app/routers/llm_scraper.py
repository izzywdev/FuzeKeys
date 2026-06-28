from fastapi import APIRouter, HTTPException, BackgroundTasks, Depends
from typing import Dict, List, Optional, Any
import logging
from pydantic import BaseModel

from ..llm_scraper_service.llm_integration.code_generator import code_generator, ScraperCode
from ..llm_scraper_service.llm_integration.prompt_templates import SiteInfo
from app.models.user import User
from app.routers.auth import get_current_user

logger = logging.getLogger(__name__)

# SECURITY (CRITICAL-2 / appsec #18): this router was public-by-default. Every
# route invoked the LLM (cost/abuse, prompt-injection) or exposed/deleted
# generated scraper source with NO auth. We now require the application JWT
# (`get_current_user`) on EVERY route in this router via a router-level
# dependency, so an unauthenticated caller gets 401 before any handler runs. The
# destructive DELETE and the LLM-invoking POSTs are therefore all gated. There is
# no public `/health` route here; if one is added later it can be exempted by
# declaring it on a separate, unauthenticated router.
router = APIRouter(
    prefix="/api/llm-scraper",
    tags=["LLM Scraper"],
    dependencies=[Depends(get_current_user)],
)

# Request/Response Models
class GenerateScraperRequest(BaseModel):
    site_name: str
    site_url: str
    action_type: str  # "signup", "signin", "apikey_creation"
    patterns: Dict[str, Any] = {}
    test_data: Dict[str, Any] = {}

class ImproveScraperRequest(BaseModel):
    site_name: str
    action_type: str
    execution_result: Dict[str, Any]

class ScraperResponse(BaseModel):
    success: bool
    scraper_id: str
    version: int
    code: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None

class ScraperListResponse(BaseModel):
    scrapers: List[Dict[str, Any]]
    total_count: int

@router.post("/generate", response_model=ScraperResponse)
async def generate_scraper(request: GenerateScraperRequest, background_tasks: BackgroundTasks):
    """Generate a new scraper for a site"""
    try:
        logger.info(f"Generating scraper for {request.site_name} {request.action_type}")
        
        # Create site info object
        site_info = SiteInfo(
            name=request.site_name,
            url=request.site_url,
            action_type=request.action_type,
            patterns=request.patterns,
            previous_attempts=[],
            test_data=request.test_data
        )
        
        # Generate scraper
        result = await code_generator.generate_initial_scraper(site_info)
        
        if not result.success:
            raise HTTPException(
                status_code=500,
                detail=f"Failed to generate scraper: {result.error_message}"
            )
        
        scraper_code = result.scraper_code
        scraper_id = f"{scraper_code.site_name}_{scraper_code.action_type}"
        
        return ScraperResponse(
            success=True,
            scraper_id=scraper_id,
            version=scraper_code.version,
            code=scraper_code.content,
            metadata=scraper_code.metadata
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error generating scraper: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/improve", response_model=ScraperResponse)
async def improve_scraper(request: ImproveScraperRequest):
    """Improve an existing scraper based on execution results"""
    try:
        logger.info(f"Improving scraper for {request.site_name} {request.action_type}")
        
        # Get latest scraper version
        latest_scraper = code_generator.get_latest_scraper(request.site_name, request.action_type)
        if not latest_scraper:
            raise HTTPException(
                status_code=404,
                detail=f"No scraper found for {request.site_name} {request.action_type}"
            )
        
        # Improve scraper
        result = await code_generator.improve_scraper(latest_scraper, request.execution_result)
        
        if not result.success:
            raise HTTPException(
                status_code=500,
                detail=f"Failed to improve scraper: {result.error_message}"
            )
        
        scraper_code = result.scraper_code
        scraper_id = f"{scraper_code.site_name}_{scraper_code.action_type}"
        
        return ScraperResponse(
            success=True,
            scraper_id=scraper_id,
            version=scraper_code.version,
            code=scraper_code.content,
            metadata=scraper_code.metadata
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error improving scraper: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/scrapers", response_model=ScraperListResponse)
async def list_scrapers():
    """List all generated scrapers"""
    try:
        stats = code_generator.get_generation_stats()
        
        scrapers = []
        for scraper_id, scraper_info in stats["scrapers"].items():
            scrapers.append({
                "scraper_id": scraper_id,
                "site_name": scraper_info["site_name"],
                "action_type": scraper_info["action_type"],
                "latest_version": scraper_info["latest_version"],
                "total_versions": scraper_info["total_versions"],
                "created_at": scraper_info["created_at"]
            })
        
        return ScraperListResponse(
            scrapers=scrapers,
            total_count=len(scrapers)
        )
        
    except Exception as e:
        logger.error(f"Error listing scrapers: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/scrapers/{site_name}/{action_type}", response_model=ScraperResponse)
async def get_scraper(site_name: str, action_type: str, version: Optional[int] = None):
    """Get a specific scraper"""
    try:
        if version is None:
            # Get latest version
            scraper_code = code_generator.get_latest_scraper(site_name, action_type)
        else:
            # Get specific version
            history = code_generator.get_scraper_history(site_name, action_type)
            scraper_code = next((s for s in history if s.version == version), None)
        
        if not scraper_code:
            raise HTTPException(
                status_code=404,
                detail=f"Scraper not found: {site_name} {action_type} v{version or 'latest'}"
            )
        
        scraper_id = f"{scraper_code.site_name}_{scraper_code.action_type}"
        
        return ScraperResponse(
            success=True,
            scraper_id=scraper_id,
            version=scraper_code.version,
            code=scraper_code.content,
            metadata=scraper_code.metadata
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting scraper: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/scrapers/{site_name}/{action_type}/history")
async def get_scraper_history(site_name: str, action_type: str):
    """Get the full history of a scraper"""
    try:
        history = code_generator.get_scraper_history(site_name, action_type)
        
        if not history:
            raise HTTPException(
                status_code=404,
                detail=f"No scraper history found for {site_name} {action_type}"
            )
        
        history_data = []
        for scraper in history:
            history_data.append({
                "version": scraper.version,
                "created_at": scraper.created_at.isoformat(),
                "parent_version": scraper.parent_version,
                "metadata": scraper.metadata
            })
        
        return {
            "site_name": site_name,
            "action_type": action_type,
            "total_versions": len(history),
            "history": history_data
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting scraper history: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/scrapers/{site_name}/{action_type}")
async def delete_scraper(site_name: str, action_type: str):
    """Delete a scraper and all its versions"""
    try:
        scraper_id = f"{site_name}_{action_type}"
        
        if scraper_id not in code_generator.generation_history:
            raise HTTPException(
                status_code=404,
                detail=f"Scraper not found: {site_name} {action_type}"
            )
        
        # Remove from memory
        del code_generator.generation_history[scraper_id]
        
        # TODO: Remove files from disk
        
        return {"message": f"Scraper {scraper_id} deleted successfully"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting scraper: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/stats")
async def get_generation_stats():
    """Get statistics about scraper generation"""
    try:
        stats = code_generator.get_generation_stats()
        return stats
        
    except Exception as e:
        logger.error(f"Error getting stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/debug")
async def debug_scraper(
    site_name: str,
    action_type: str,
    error: str,
    context: Dict[str, Any]
):
    """Debug a specific scraper issue"""
    try:
        # Get latest scraper version
        latest_scraper = code_generator.get_latest_scraper(site_name, action_type)
        if not latest_scraper:
            raise HTTPException(
                status_code=404,
                detail=f"No scraper found for {site_name} {action_type}"
            )
        
        # Debug scraper
        result = await code_generator.debug_scraper(latest_scraper, error, context)
        
        if not result.success:
            raise HTTPException(
                status_code=500,
                detail=f"Failed to debug scraper: {result.error_message}"
            )
        
        scraper_code = result.scraper_code
        scraper_id = f"{scraper_code.site_name}_{scraper_code.action_type}"
        
        return ScraperResponse(
            success=True,
            scraper_id=scraper_id,
            version=scraper_code.version,
            code=scraper_code.content,
            metadata=scraper_code.metadata
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error debugging scraper: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# Startup event to load existing scrapers
@router.on_event("startup")
async def load_existing_scrapers():
    """Load existing scrapers on startup"""
    try:
        await code_generator.load_existing_scrapers()
        logger.info("Loaded existing scrapers on startup")
    except Exception as e:
        logger.error(f"Error loading existing scrapers: {e}") 