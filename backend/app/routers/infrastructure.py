from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks, Header
from sqlalchemy.orm import Session
from typing import List, Dict, Optional, Any
import hmac
import logging
import json
import uuid
from datetime import datetime, timedelta
from pydantic import BaseModel

from ..database import get_db
from ..utils.websocket_manager import ConnectionManager
from ..models.sms import SmsDevice, SmsOtpRequest, SmsOtpReceived
from ..utils.logging import log_security_event
# SECURITY: reuse the SINGLE device-auth model defined in sms.py rather than
# inventing a second one. registered_device_keys (device_id -> issued key) is
# populated by sms.py's /register-device, and _verify_device does the
# constant-time check. Imported at module top; there is no circular import
# because sms.py does NOT import infrastructure.py (verified — sms.py only
# imports from ..database/..models/..utils), so this edge is one-directional.
from .sms import registered_device_keys, _verify_device
# Operator/user-facing endpoints require the application JWT.
from .auth import get_current_user
from ..models.user import User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/infrastructure", tags=["Infrastructure"])

# Connection managers for different communication channels
sms_manager = ConnectionManager()
mobile_manager = ConnectionManager()

# In-memory storage for verification requests (use Redis in production)
verification_requests: Dict[str, Dict] = {}
email_monitors: Dict[str, Dict] = {}

# Request/Response Models
class SmsVerificationRequest(BaseModel):
    site: str
    phone_number: str
    timeout_seconds: int = 300

class EmailMonitoringRequest(BaseModel):
    email: str
    sender_patterns: List[str]
    subject_patterns: List[str]
    timeout_seconds: int = 300

class MobileCommandRequest(BaseModel):
    command_type: str  # "click_prompt", "extract_totp", "handle_buttons"
    parameters: Dict[str, Any]
    timeout_seconds: int = 60

class VerificationResponse(BaseModel):
    request_id: str
    status: str  # "pending", "completed", "timeout", "failed"
    code: Optional[str] = None
    timestamp: Optional[datetime] = None
    error_message: Optional[str] = None

# SMS Verification APIs
@router.post("/sms/request-verification", response_model=Dict[str, str])
async def request_sms_verification(
    request: SmsVerificationRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Request SMS verification from mobile device for scraper use.

    SECURITY: Operator/app-facing — this initiates a verification job and
    broadcasts it to mobile devices. Requires the application JWT so arbitrary
    callers cannot push fake jobs to devices or exhaust resources. The
    request->device binding is established later, when a device authenticates
    and submits the code via /sms/complete-verification.
    """
    try:
        request_id = str(uuid.uuid4())
        
        # Store request details
        verification_requests[request_id] = {
            "type": "sms_verification",
            "site": request.site,
            "phone_number": request.phone_number,
            "status": "pending",
            "created_at": datetime.utcnow(),
            "timeout_at": datetime.utcnow() + timedelta(seconds=request.timeout_seconds)
        }
        
        # Send request to mobile device via WebSocket
        await sms_manager.broadcast(json.dumps({
            "type": "verification_request",
            "request_id": request_id,
            "site": request.site,
            "phone_number": request.phone_number,
            "timeout": request.timeout_seconds
        }))
        
        logger.info(f"SMS verification requested for {request.site}, request_id: {request_id}")
        
        return {
            "request_id": request_id,
            "status": "pending",
            "message": f"SMS verification request sent for {request.site}"
        }
        
    except Exception as e:
        logger.error(f"Error requesting SMS verification: {e}")
        raise HTTPException(status_code=500, detail="Failed to request SMS verification")

@router.get("/sms/get-verification/{request_id}", response_model=VerificationResponse)
async def get_sms_verification(
    request_id: str,
    current_user: User = Depends(get_current_user),
):
    """Get SMS verification code for scraper.

    SECURITY: Returns the verification CODE itself, which is highly sensitive.
    Operator/app-facing (the scraper orchestration polls for the result via the
    app), so it requires the application JWT. Previously unauthenticated, this
    let any caller read codes by enumerating request_ids.
    """
    try:
        if request_id not in verification_requests:
            raise HTTPException(status_code=404, detail="Verification request not found")
        
        request_data = verification_requests[request_id]
        
        # Check if timeout exceeded
        if datetime.utcnow() > request_data["timeout_at"]:
            request_data["status"] = "timeout"
        
        return VerificationResponse(
            request_id=request_id,
            status=request_data["status"],
            code=request_data.get("code"),
            timestamp=request_data.get("completed_at"),
            error_message=request_data.get("error_message")
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting SMS verification: {e}")
        raise HTTPException(status_code=500, detail="Failed to get SMS verification")

@router.post("/sms/complete-verification/{request_id}")
async def complete_sms_verification(
    request_id: str,
    code: str,
    device_id: str,
    x_device_key: Optional[str] = Header(default=None, alias="X-Device-Key"),
):
    """Called by mobile device to complete SMS verification.

    SECURITY: This is a DEVICE-to-server callback that submits an
    attacker-influenceable value (the verification ``code``). It is therefore
    authenticated with the SAME per-device API key model as sms.py:

    1) AUTH — the submitting device must present the ``X-Device-Key`` it was
       issued at registration, verified against ``device_id`` via the shared
       ``_verify_device``. Unknown/unauthenticated devices are rejected 401.
       This closes the hole where ANY unauthenticated caller could complete a
       verification with an attacker-controlled code.
    2) BINDING — the request is bound to a specific device. infrastructure.py
       owns its own request store (``verification_requests``), and that store
       had no device assignment at request time, so (mirroring sms.py's /otp)
       we bind on first authenticated completion: the first authenticated
       device to answer becomes the assigned device, and a DIFFERENT device
       attempting to complete the same request is rejected 403. This prevents
       a second (even authenticated) device from overwriting another device's
       in-flight verification.
    """
    try:
        # 1) Authenticate the device against the supplied device_id.
        if not _verify_device(device_id, x_device_key):
            log_security_event(
                "infra_sms_complete_auth_failure",
                details={
                    "device_id": device_id,
                    "request_id": request_id,
                    "reason": "invalid_or_missing_device_key",
                },
            )
            raise HTTPException(status_code=401, detail="Device authentication failed")

        if request_id not in verification_requests:
            log_security_event(
                "infra_sms_complete_unknown_request",
                details={"device_id": device_id, "request_id": request_id},
            )
            raise HTTPException(status_code=404, detail="Verification request not found")

        request_data = verification_requests[request_id]

        # 2) Bind request_id <-> device. Assign on first authenticated answer,
        #    reject mismatches thereafter.
        assigned_device = request_data.get("assigned_device_id")
        if assigned_device is None:
            request_data["assigned_device_id"] = device_id
        elif not hmac.compare_digest(str(assigned_device), str(device_id)):
            log_security_event(
                "infra_sms_complete_device_mismatch",
                details={
                    "device_id": device_id,
                    "request_id": request_id,
                    "assigned_device_id": assigned_device,
                },
            )
            raise HTTPException(
                status_code=403,
                detail="Device is not assigned to this request",
            )

        request_data.update({
            "status": "completed",
            "code": code,
            "device_id": device_id,
            "completed_at": datetime.utcnow()
        })

        # SECURITY: do not log the verification code itself.
        log_security_event(
            "infra_sms_complete_success",
            details={"device_id": device_id, "request_id": request_id},
        )
        logger.info(f"SMS verification completed for request {request_id}")

        return {"status": "success", "message": "Verification completed"}

    except HTTPException:
        # Preserve auth/binding status codes (401/403/404) — don't mask as 500.
        raise
    except Exception as e:
        logger.error(f"Error completing SMS verification: {e}")
        raise HTTPException(status_code=500, detail="Failed to complete SMS verification")

# Email Verification APIs
@router.post("/email/setup-monitoring", response_model=Dict[str, str])
async def setup_email_monitoring(
    request: EmailMonitoringRequest,
    current_user: User = Depends(get_current_user),
):
    """Setup email monitoring for verification emails.

    SECURITY: Operator/app-facing — it registers monitoring on an email
    address and patterns (sensitive targeting data). Requires the application
    JWT; not a device callback.
    """
    try:
        monitor_id = str(uuid.uuid4())
        
        email_monitors[monitor_id] = {
            "email": request.email,
            "sender_patterns": request.sender_patterns,
            "subject_patterns": request.subject_patterns,
            "status": "monitoring",
            "created_at": datetime.utcnow(),
            "timeout_at": datetime.utcnow() + timedelta(seconds=request.timeout_seconds),
            "found_emails": []
        }
        
        # Start background email monitoring
        # TODO: Implement actual email monitoring service
        
        logger.info(f"Email monitoring setup for {request.email}, monitor_id: {monitor_id}")
        
        return {
            "monitor_id": monitor_id,
            "status": "monitoring",
            "message": f"Email monitoring started for {request.email}"
        }
        
    except Exception as e:
        logger.error(f"Error setting up email monitoring: {e}")
        raise HTTPException(status_code=500, detail="Failed to setup email monitoring")

@router.get("/email/get-verification/{monitor_id}")
async def get_email_verification(
    monitor_id: str,
    current_user: User = Depends(get_current_user),
):
    """Get email verification content.

    SECURITY: Returns captured email content (``found_emails``), which is
    sensitive. Operator/app-facing, so it requires the application JWT.
    Previously unauthenticated, allowing enumeration of monitor_ids to read
    intercepted emails.
    """
    try:
        if monitor_id not in email_monitors:
            raise HTTPException(status_code=404, detail="Email monitor not found")
        
        monitor_data = email_monitors[monitor_id]
        
        # Check if timeout exceeded
        if datetime.utcnow() > monitor_data["timeout_at"]:
            monitor_data["status"] = "timeout"
        
        return {
            "monitor_id": monitor_id,
            "status": monitor_data["status"],
            "found_emails": monitor_data["found_emails"],
            "timestamp": monitor_data.get("last_check")
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting email verification: {e}")
        raise HTTPException(status_code=500, detail="Failed to get email verification")

# Mobile Communication APIs
@router.post("/mobile/send-command", response_model=Dict[str, str])
async def send_mobile_command(
    request: MobileCommandRequest,
    current_user: User = Depends(get_current_user),
):
    """Send command to mobile device for UI automation.

    SECURITY: Operator/app-facing — this dispatches automation commands to
    devices. Requires the application JWT so an unauthenticated caller cannot
    drive devices / inject commands.
    """
    try:
        command_id = str(uuid.uuid4())
        
        command_data = {
            "command_id": command_id,
            "type": request.command_type,
            "parameters": request.parameters,
            "timeout": request.timeout_seconds,
            "created_at": datetime.utcnow().isoformat()
        }
        
        # Send command to mobile device
        await mobile_manager.broadcast(json.dumps({
            "type": "automation_command",
            **command_data
        }))
        
        logger.info(f"Mobile command sent: {request.command_type}, command_id: {command_id}")
        
        return {
            "command_id": command_id,
            "status": "sent",
            "message": f"Command {request.command_type} sent to mobile device"
        }
        
    except Exception as e:
        logger.error(f"Error sending mobile command: {e}")
        raise HTTPException(status_code=500, detail="Failed to send mobile command")

@router.get("/mobile/get-command-result/{command_id}")
async def get_mobile_command_result(
    command_id: str,
    current_user: User = Depends(get_current_user),
):
    """Get result of mobile command execution.

    SECURITY: Operator/app-facing. Although currently a stub, it is designed to
    surface results returned by mobile devices (potentially sensitive), so it
    is gated by the application JWT now to avoid shipping an unauthenticated
    read endpoint once result tracking is implemented.
    """
    # TODO: Implement command result tracking
    # This would store results from mobile device responses
    return {
        "command_id": command_id,
        "status": "pending",
        "result": None
    }

# Helper APIs for scrapers
@router.post("/scraper/report-error")
async def report_scraper_error(
    scraper_id: str,
    error_data: Dict[str, Any],
    current_user: User = Depends(get_current_user),
):
    """Report scraper execution error for analysis.

    SECURITY: Accepts arbitrary external input (scraper_id + free-form data).
    Scrapers run under the platform/operator identity, so this requires the
    application JWT to prevent unauthenticated log/data injection and spam.
    Not a mobile-device callback, so device-key auth does not apply.
    """
    try:
        error_report = {
            "scraper_id": scraper_id,
            "timestamp": datetime.utcnow(),
            "error_data": error_data
        }
        
        # Store error for analysis (use proper database in production)
        logger.error(f"Scraper error reported: {scraper_id} - {error_data}")
        
        return {"status": "success", "message": "Error reported successfully"}
        
    except Exception as e:
        logger.error(f"Error reporting scraper error: {e}")
        raise HTTPException(status_code=500, detail="Failed to report error")

@router.post("/scraper/report-success")
async def report_scraper_success(
    scraper_id: str,
    success_data: Dict[str, Any],
    current_user: User = Depends(get_current_user),
):
    """Report scraper execution success.

    SECURITY: Accepts arbitrary external input; gated by the application JWT for
    the same reasons as /scraper/report-error (the scraper acts as the
    platform/operator). Not a device callback.
    """
    try:
        success_report = {
            "scraper_id": scraper_id,
            "timestamp": datetime.utcnow(),
            "success_data": success_data
        }
        
        logger.info(f"Scraper success reported: {scraper_id} - {success_data}")
        
        return {"status": "success", "message": "Success reported"}
        
    except Exception as e:
        logger.error(f"Error reporting scraper success: {e}")
        raise HTTPException(status_code=500, detail="Failed to report success")

# WebSocket endpoints for real-time communication
@router.websocket("/ws/mobile-commands")
async def mobile_commands_websocket(websocket):
    """WebSocket endpoint for mobile device command communication.

    SECURITY NOTE: Currently unauthenticated. RESIDUAL HARDENING (documented
    follow-up, consistent with sms.py's websocket): require the device to send
    its X-Device-Key as the first frame and verify it via _verify_device before
    joining the mobile_manager broadcast group. Left as a tracked follow-up
    because a full WS auth handshake exceeds this scoped HTTP-auth fix; flagged
    rather than silently ignored.
    """
    await mobile_manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            message = json.loads(data)
            
            # Handle responses from mobile device
            if message.get("type") == "command_result":
                logger.info(f"Mobile command result received: {message}")
                # TODO: Store command result for retrieval
            
    except Exception as e:
        logger.error(f"Mobile WebSocket error: {e}")
        mobile_manager.disconnect(websocket)

# Utility functions for scrapers
class InfrastructureAPI:
    """Helper class that scrapers can import and use"""
    
    @staticmethod
    async def request_sms_verification(site: str, phone_number: str, timeout: int = 300) -> str:
        """Request SMS verification and return request ID"""
        # This would be used by scrapers to request SMS verification
        pass
    
    @staticmethod
    async def wait_for_sms_code(request_id: str, poll_interval: int = 5) -> str:
        """Wait for SMS verification code"""
        # This would be used by scrapers to wait for and get SMS codes
        pass
    
    @staticmethod
    async def setup_email_monitoring(email: str, patterns: List[str]) -> str:
        """Setup email monitoring and return monitor ID"""
        pass
    
    @staticmethod
    async def get_verification_email(monitor_id: str) -> Dict[str, Any]:
        """Get verification email content"""
        pass
    
    @staticmethod
    async def send_mobile_command(command_type: str, parameters: Dict[str, Any]) -> str:
        """Send command to mobile device"""
        pass 