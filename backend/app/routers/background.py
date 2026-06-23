from fastapi import APIRouter, HTTPException, BackgroundTasks, Depends
from typing import Dict, List, Optional, Any
from pydantic import BaseModel, Field
from datetime import datetime
import logging

from ..services.background_service import get_background_manager, BackgroundServiceManager
from ..services.email_service import EmailConfig, create_email_config
from ..database import get_db
from sqlalchemy.ext.asyncio import AsyncSession

# SECURITY: every state-changing / data-exposing endpoint in this router must
# require an authenticated user. get_current_user (async JWT dependency) raises
# 401 for missing/invalid bearer tokens. User is the ORM model used by auth.
from app.routers.auth import get_current_user
from app.models.user import User

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
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user)
):
    """Add an email account for verification monitoring (authenticated)."""
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

        # SECURITY: associate this config with the authenticated user's id rather
        # than trusting any user-supplied identifier. We attach the owner id so the
        # in-memory store can never be keyed/looked-up by an attacker-controlled
        # email/identifier. setattr is used because EmailConfig is a frozen-ish
        # dataclass owned by another module (we don't edit that file here).
        try:
            setattr(email_config, "owner_user_id", current_user.id)
        except Exception:
            pass

        # Add to background manager
        manager.add_email_config(email_config)

        # SECURITY/PII: never log the email address, password, or IMAP/SMTP creds.
        # Log only the authenticated user id and a count of configured accounts.
        logger.info(
            "Added email configuration for user_id=%s (total accounts=%s)",
            current_user.id, len(manager.email_configs)
        )

        # PRODUCTION NOTE: EmailConfig currently holds the IMAP/SMTP password in
        # plaintext in process memory (see services/email_service.py EmailConfig).
        # This is a HIGH-severity at-rest exposure. Before production these
        # credentials MUST be encrypted at rest using the app's Fernet credential
        # encryption (app/utils/encryption.py) and decrypted only at connection
        # time. Fixing that requires changing the EmailConfig model / service and
        # is intentionally out of scope for this single-file remediation.

        return {
            "success": True,
            "message": "Email configuration added",
            "email_address": config_request.email_address
        }

    except Exception as e:
        # SECURITY: do not echo internal exception text (may contain creds/PII).
        logger.error("Error adding email config for user_id=%s", current_user.id)
        raise HTTPException(status_code=500, detail="Failed to add email configuration")

@router.get("/email-configs", summary="List configured email accounts")
async def list_email_configs(
    current_user: User = Depends(get_current_user)
):
    """List configured email accounts for the authenticated user (no passwords)."""
    try:
        manager = await get_background_manager()

        configs = []
        for config in manager.email_configs:
            # Only expose configs owned by the authenticated user when ownership
            # is tracked; legacy entries without an owner are not exposed.
            if getattr(config, "owner_user_id", None) != current_user.id:
                continue
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
        logger.error("Error listing email configs for user_id=%s", current_user.id)
        raise HTTPException(status_code=500, detail="Failed to list email configurations")

@router.post("/automation-job", summary="Create automation job", response_model=Dict[str, str])
async def create_automation_job(
    job_request: AutomationJobRequest,
    current_user: User = Depends(get_current_user)
):
    """Create a new signup automation job (authenticated)."""
    try:
        manager = await get_background_manager()

        # Create automation job
        job_id = await manager.create_automation_job(
            website=job_request.website,
            identity_id=job_request.identity_id,
            email_account=job_request.email_account,
            signup_data=job_request.signup_data
        )

        # PII: email_account is a user identifier; log only the job id + user id.
        logger.info(
            "Created automation job %s for user_id=%s", job_id, current_user.id
        )

        return {
            "job_id": job_id,
            "status": "created",
            "message": f"Automation job created for {job_request.website}"
        }

    except Exception as e:
        logger.error("Error creating automation job for user_id=%s", current_user.id)
        raise HTTPException(status_code=500, detail="Failed to create automation job")

@router.get("/automation-job/{job_id}", summary="Get job status", response_model=JobStatusResponse)
async def get_job_status(
    job_id: str,
    current_user: User = Depends(get_current_user)
):
    """Get the status of an automation job (authenticated)."""
    try:
        manager = await get_background_manager()

        job_status = await manager.get_job_status(job_id)
        if not job_status:
            raise HTTPException(status_code=404, detail="Job not found")

        return JobStatusResponse(**job_status)

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error getting job status for user_id=%s", current_user.id)
        raise HTTPException(status_code=500, detail="Failed to get job status")

@router.get("/automation-jobs", summary="List all automation jobs")
async def list_automation_jobs(
    status: Optional[str] = None,
    website: Optional[str] = None,
    limit: int = 50,
    current_user: User = Depends(get_current_user)
):
    """List automation jobs with optional filtering (authenticated)."""
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
        logger.error("Error listing automation jobs for user_id=%s", current_user.id)
        raise HTTPException(status_code=500, detail="Failed to list automation jobs")

@router.post("/solve-captcha", summary="Solve captcha using AI")
async def solve_captcha(
    captcha_request: CaptchaSolveRequest,
    current_user: User = Depends(get_current_user)
):
    """Solve a captcha using AI vision capabilities (authenticated)."""
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
        logger.error("Error solving captcha for user_id=%s", current_user.id)
        raise HTTPException(status_code=500, detail="Failed to solve captcha")

@router.get("/status", summary="Get background service status", response_model=ServiceStatusResponse)
async def get_service_status(
    current_user: User = Depends(get_current_user)
):
    """Get the current status of all background services (authenticated).

    Exposes aggregate counts about email accounts/jobs that should not be
    visible to anonymous callers, so authentication is required.
    """
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
        logger.error("Error getting service status for user_id=%s", current_user.id)
        raise HTTPException(status_code=500, detail="Failed to get service status")

@router.post("/start", summary="Start background services")
async def start_services(
    current_user: User = Depends(get_current_user)
):
    """Start all background services (authenticated)."""
    try:
        manager = await get_background_manager()
        await manager.start()

        logger.info("Background services started by user_id=%s", current_user.id)

        return {
            "success": True,
            "message": "Background services started",
            "running": manager.running
        }

    except Exception as e:
        logger.error("Error starting services for user_id=%s", current_user.id)
        raise HTTPException(status_code=500, detail="Failed to start services")

@router.post("/stop", summary="Stop background services")
async def stop_services(
    current_user: User = Depends(get_current_user)
):
    """Stop all background services (authenticated)."""
    try:
        manager = await get_background_manager()
        await manager.stop()

        logger.info("Background services stopped by user_id=%s", current_user.id)

        return {
            "success": True,
            "message": "Background services stopped",
            "running": manager.running
        }

    except Exception as e:
        logger.error("Error stopping services for user_id=%s", current_user.id)
        raise HTTPException(status_code=500, detail="Failed to stop services")

@router.get("/tasks", summary="List background tasks")
async def list_tasks(
    task_type: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = 50,
    current_user: User = Depends(get_current_user)
):
    """List background tasks with optional filtering (authenticated)."""
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
        logger.error("Error listing tasks for user_id=%s", current_user.id)
        raise HTTPException(status_code=500, detail="Failed to list tasks")

@router.delete("/automation-job/{job_id}", summary="Cancel automation job")
async def cancel_automation_job(
    job_id: str,
    current_user: User = Depends(get_current_user)
):
    """Cancel a pending or running automation job (authenticated)."""
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

        logger.info("Job %s cancelled by user_id=%s", job_id, current_user.id)

        return {
            "success": True,
            "message": f"Job {job_id} cancelled",
            "job_id": job_id
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error cancelling job for user_id=%s", current_user.id)
        raise HTTPException(status_code=500, detail="Failed to cancel job")