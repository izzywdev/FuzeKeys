from fastapi import APIRouter, HTTPException, BackgroundTasks, Depends
from typing import Dict, List, Optional, Any
from pydantic import BaseModel, Field
from datetime import datetime
import logging

from ..services.background_service import get_background_manager, BackgroundServiceManager
from ..services.email_service import EmailConfig, create_email_config
from ..database import get_db
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/background", tags=["background"])

# Request models
class EmailConfigRequest(BaseModel):
    email_address: str = Field(..., description="Email address to monitor")
    password: str = Field(..., description="Email password or app password")
    provider: Optional[str] = Field(None, description="Email provider (gmail, outlook, yahoo)")
    imap_server: Optional[str] = Field(None, description="Custom IMAP server")
    imap_port: Optional[int] = Field(993, description="IMAP port")
    smtp_server: Optional[str] = Field(None, description="Custom SMTP server") 
    smtp_port: Optional[int] = Field(587, description="SMTP port")

class AutomationJobRequest(BaseModel):
    website: str = Field(..., description="Website to create account on")
    identity_id: int = Field(..., description="Identity to use for signup")
    email_account: str = Field(..., description="Email account for verification")
    signup_data: Dict[str, Any] = Field(..., description="Data for signup form")

class CaptchaSolveRequest(BaseModel):
    image_url: Optional[str] = Field(None, description="URL of captcha image")
    image_data: Optional[str] = Field(None, description="Base64 encoded image data")
    captcha_type: str = Field("text", description="Type of captcha (text, image, recaptcha, hcaptcha)")
    question: Optional[str] = Field(None, description="Captcha question or instruction")

# Response models
class JobStatusResponse(BaseModel):
    job_id: str
    website: str
    status: str
    created_at: Optional[str]
    completed_at: Optional[str]
    verification_required: bool
    error: Optional[str]

class ServiceStatusResponse(BaseModel):
    email_monitoring: bool
    captcha_solving: bool
    automation_jobs: int
    pending_tasks: int
    email_accounts: int

@router.post("/email-config", summary="Add email configuration for monitoring")
async def add_email_config(
    config_request: EmailConfigRequest,
    background_tasks: BackgroundTasks
):
    """Add an email account for verification monitoring"""
    try:
        manager = await get_background_manager()
        
        # Create email config
        email_config = create_email_config(
            email_address=config_request.email_address,
            password=config_request.password,
            provider=config_request.provider
        )
        
        # Override with custom settings if provided
        if config_request.imap_server:
            email_config.imap_server = config_request.imap_server
        if config_request.imap_port:
            email_config.imap_port = config_request.imap_port
        if config_request.smtp_server:
            email_config.smtp_server = config_request.smtp_server
        if config_request.smtp_port:
            email_config.smtp_port = config_request.smtp_port
        
        # Add to background manager
        manager.add_email_config(email_config)
        
        logger.info(f"Added email configuration for {config_request.email_address}")
        
        return {
            "success": True,
            "message": f"Email configuration added for {config_request.email_address}",
            "email_address": config_request.email_address
        }
        
    except Exception as e:
        logger.error(f"Error adding email config: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/email-configs", summary="List configured email accounts")
async def list_email_configs():
    """List all configured email accounts (without passwords)"""
    try:
        manager = await get_background_manager()
        
        configs = []
        for config in manager.email_configs:
            configs.append({
                "email_address": config.email_address,
                "imap_server": config.imap_server,
                "imap_port": config.imap_port,
                "provider": "gmail" if "gmail" in config.imap_server else "other"
            })
        
        return {
            "email_configs": configs,
            "total": len(configs)
        }
        
    except Exception as e:
        logger.error(f"Error listing email configs: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/automation-job", summary="Create automation job", response_model=Dict[str, str])
async def create_automation_job(job_request: AutomationJobRequest):
    """Create a new signup automation job"""
    try:
        manager = await get_background_manager()
        
        # Create automation job
        job_id = await manager.create_automation_job(
            website=job_request.website,
            identity_id=job_request.identity_id,
            email_account=job_request.email_account,
            signup_data=job_request.signup_data
        )
        
        logger.info(f"Created automation job {job_id} for {job_request.website}")
        
        return {
            "job_id": job_id,
            "status": "created",
            "message": f"Automation job created for {job_request.website}"
        }
        
    except Exception as e:
        logger.error(f"Error creating automation job: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/automation-job/{job_id}", summary="Get job status", response_model=JobStatusResponse)
async def get_job_status(job_id: str):
    """Get the status of an automation job"""
    try:
        manager = await get_background_manager()
        
        job_status = await manager.get_job_status(job_id)
        if not job_status:
            raise HTTPException(status_code=404, detail="Job not found")
        
        return JobStatusResponse(**job_status)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting job status: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/automation-jobs", summary="List all automation jobs")
async def list_automation_jobs(
    status: Optional[str] = None,
    website: Optional[str] = None,
    limit: int = 50
):
    """List automation jobs with optional filtering"""
    try:
        manager = await get_background_manager()
        
        jobs = []
        for job in manager.automation_jobs.values():
            # Apply filters
            if status and job.status != status:
                continue
            if website and job.website != website:
                continue
            
            job_data = {
                "job_id": job.job_id,
                "website": job.website,
                "identity_id": job.identity_id,
                "status": job.status,
                "created_at": job.created_at.isoformat() if job.created_at else None,
                "completed_at": job.completed_at.isoformat() if job.completed_at else None,
                "verification_required": job.verification_required,
                "error": job.error
            }
            jobs.append(job_data)
        
        # Sort by creation time (newest first) and limit
        jobs.sort(key=lambda x: x["created_at"] or "", reverse=True)
        jobs = jobs[:limit]
        
        return {
            "jobs": jobs,
            "total": len(manager.automation_jobs),
            "filtered": len(jobs)
        }
        
    except Exception as e:
        logger.error(f"Error listing automation jobs: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/solve-captcha", summary="Solve captcha using AI")
async def solve_captcha(captcha_request: CaptchaSolveRequest):
    """Solve a captcha using AI vision capabilities"""
    try:
        manager = await get_background_manager()
        
        # Import here to avoid circular dependencies
        from ..services.captcha_service import CaptchaChallenge
        import base64
        
        # Prepare captcha challenge
        challenge = CaptchaChallenge(
            challenge_type=captcha_request.captcha_type,
            image_url=captcha_request.image_url,
            question=captcha_request.question
        )
        
        # Convert base64 data if provided
        if captcha_request.image_data:
            try:
                challenge.image_data = base64.b64decode(captcha_request.image_data)
            except Exception as e:
                raise HTTPException(status_code=400, detail="Invalid base64 image data")
        
        # Solve captcha
        solution = await manager.captcha_solver.solve_captcha(challenge)
        
        if not solution:
            raise HTTPException(status_code=400, detail="Could not solve captcha")
        
        return {
            "success": True,
            "solution": solution.solution,
            "confidence": solution.confidence,
            "reasoning": solution.reasoning,
            "alternative_solutions": solution.alternative_solutions
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error solving captcha: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/status", summary="Get background service status", response_model=ServiceStatusResponse)
async def get_service_status():
    """Get the current status of all background services"""
    try:
        manager = await get_background_manager()
        
        # Count pending tasks
        pending_tasks = sum(1 for task in manager.tasks.values() if task.status == 'pending')
        
        return ServiceStatusResponse(
            email_monitoring=manager.email_service is not None and manager.running,
            captcha_solving=True,  # Always available if OpenAI key is configured
            automation_jobs=len(manager.automation_jobs),
            pending_tasks=pending_tasks,
            email_accounts=len(manager.email_configs)
        )
        
    except Exception as e:
        logger.error(f"Error getting service status: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/start", summary="Start background services")
async def start_services():
    """Start all background services"""
    try:
        manager = await get_background_manager()
        await manager.start()
        
        return {
            "success": True,
            "message": "Background services started",
            "running": manager.running
        }
        
    except Exception as e:
        logger.error(f"Error starting services: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/stop", summary="Stop background services")
async def stop_services():
    """Stop all background services"""
    try:
        manager = await get_background_manager()
        await manager.stop()
        
        return {
            "success": True,
            "message": "Background services stopped",
            "running": manager.running
        }
        
    except Exception as e:
        logger.error(f"Error stopping services: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/tasks", summary="List background tasks")
async def list_tasks(
    task_type: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = 50
):
    """List background tasks with optional filtering"""
    try:
        manager = await get_background_manager()
        
        tasks = []
        for task in manager.tasks.values():
            # Apply filters
            if task_type and task.task_type != task_type:
                continue
            if status and task.status != status:
                continue
            
            task_data = {
                "task_id": task.task_id,
                "task_type": task.task_type,
                "status": task.status,
                "created_at": task.created_at.isoformat() if task.created_at else None,
                "started_at": task.started_at.isoformat() if task.started_at else None,
                "completed_at": task.completed_at.isoformat() if task.completed_at else None,
                "retry_count": task.retry_count,
                "error": task.error
            }
            tasks.append(task_data)
        
        # Sort by creation time (newest first) and limit
        tasks.sort(key=lambda x: x["created_at"] or "", reverse=True)
        tasks = tasks[:limit]
        
        return {
            "tasks": tasks,
            "total": len(manager.tasks),
            "filtered": len(tasks)
        }
        
    except Exception as e:
        logger.error(f"Error listing tasks: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/automation-job/{job_id}", summary="Cancel automation job")
async def cancel_automation_job(job_id: str):
    """Cancel a pending or running automation job"""
    try:
        manager = await get_background_manager()
        
        job = manager.automation_jobs.get(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")
        
        if job.status in ['completed', 'failed']:
            raise HTTPException(status_code=400, detail="Job already completed")
        
        # Update job status
        job.status = 'cancelled'
        job.completed_at = datetime.now()
        
        return {
            "success": True,
            "message": f"Job {job_id} cancelled",
            "job_id": job_id
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error cancelling job: {e}")
        raise HTTPException(status_code=500, detail=str(e)) 