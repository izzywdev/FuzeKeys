import hmac
import json
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    Header,
    HTTPException,
    WebSocket,
    WebSocketDisconnect,
)
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..models.sms import SmsDevice, SmsOtpReceived, SmsOtpRequest
from ..models.user import User
from ..utils.logging import log_security_event
from ..utils.websocket_manager import ConnectionManager

# Operator/user-facing endpoints require the application JWT.
from .auth import get_current_user

# SECURITY: reuse the SINGLE device-auth model defined in sms.py rather than
# inventing a second one. registered_device_keys (device_id -> issued key) is
# populated by sms.py's /register-device, and _verify_device does the
# constant-time check. Imported at module top; there is no circular import
# because sms.py does NOT import infrastructure.py (verified — sms.py only
# imports from ..database/..models/..utils), so this edge is one-directional.
from .sms import _verify_device

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/infrastructure", tags=["Infrastructure"])

# Connection managers for different communication channels
sms_manager = ConnectionManager()
mobile_manager = ConnectionManager()

# Email monitoring and mobile-command state still require durable custody.
email_monitors: Dict[str, Dict] = {}
mobile_commands: Dict[str, Dict] = {}


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
    device_id: str
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
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Request SMS verification from mobile device for scraper use.

    SECURITY: Operator/app-facing — this initiates a verification job. Requires
    the application JWT so arbitrary callers cannot push fake jobs or exhaust
    resources. The request remains withheld until a separate authorized
    assignment lifecycle binds it to one verified device.
    """
    try:
        request_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)
        db.add(
            SmsOtpRequest(
                request_id=request_id,
                service=request.site,
                target_phone_number=request.phone_number,
                status="waiting",
                owner_user_id=current_user.id,
                created_at=now,
                timeout_at=now + timedelta(seconds=request.timeout_seconds),
            )
        )
        await db.commit()

        # Do not broadcast an unassigned request. The request contains a phone
        # number and request id and must not become first-device-claims-work.

        logger.info(
            f"SMS verification requested for {request.site}, request_id: {request_id}"
        )

        return {
            "request_id": request_id,
            "status": "pending",
            "message": f"SMS verification request created for {request.site}",
        }

    except Exception as e:
        logger.error(f"Error requesting SMS verification: {e}")
        raise HTTPException(
            status_code=500, detail="Failed to request SMS verification"
        )


@router.get("/sms/get-verification/{request_id}", response_model=VerificationResponse)
async def get_sms_verification(
    request_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get SMS verification code for scraper.

    SECURITY: Returns the verification CODE itself, which is highly sensitive.
    The application JWT must identify the exact local user that created the
    request. Foreign, unknown and legacy unbound IDs all return the same 404.
    """
    try:
        request_data = (
            await db.execute(
                select(SmsOtpRequest).where(
                    SmsOtpRequest.request_id == request_id,
                    SmsOtpRequest.owner_user_id == current_user.id,
                )
            )
        ).scalar_one_or_none()
        if request_data is None:
            raise HTTPException(
                status_code=404, detail="Verification request not found"
            )

        timeout_at = request_data.timeout_at
        if timeout_at.tzinfo is None:
            timeout_at = timeout_at.replace(tzinfo=timezone.utc)
        if datetime.now(timezone.utc) > timeout_at and request_data.status == "waiting":
            request_data.status = "timeout"
            await db.commit()

        return VerificationResponse(
            request_id=request_id,
            status=(
                "pending" if request_data.status == "waiting" else request_data.status
            ),
            code=request_data.otp_code,
            timestamp=request_data.completed_at,
            error_message=None,
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
    db: AsyncSession = Depends(get_db),
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
    2) BINDING — the request must already be assigned to this device by the
       server-side authorization lifecycle. An authenticated device may not
       claim unassigned work merely by learning a request id.
    """
    try:
        # 1) Authenticate the device against the supplied device_id.
        if not await _verify_device(db, device_id, x_device_key):
            log_security_event(
                "infra_sms_complete_auth_failure",
                details={
                    "device_id": device_id,
                    "request_id": request_id,
                    "reason": "invalid_or_missing_device_key",
                },
            )
            raise HTTPException(status_code=401, detail="Device authentication failed")

        request_data = (
            await db.execute(
                select(SmsOtpRequest)
                .where(SmsOtpRequest.request_id == request_id)
                .with_for_update()
            )
        ).scalar_one_or_none()
        if request_data is None:
            log_security_event(
                "infra_sms_complete_unknown_request",
                details={"device_id": device_id, "request_id": request_id},
            )
            raise HTTPException(
                status_code=404, detail="Verification request not found"
            )

        # 2) Require an existing authorized request <-> device assignment.
        assigned_device = request_data.assigned_device_id
        if not isinstance(assigned_device, str) or not assigned_device:
            log_security_event(
                "infra_sms_complete_unassigned",
                details={"device_id": device_id, "request_id": request_id},
            )
            raise HTTPException(
                status_code=409,
                detail="Verification request has no authorized device assignment",
            )
        if not hmac.compare_digest(assigned_device, device_id):
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

        if request_data.status != "waiting":
            raise HTTPException(
                status_code=409,
                detail="Verification request is not pending",
            )

        timeout_at = request_data.timeout_at
        if isinstance(timeout_at, datetime) and timeout_at.tzinfo is None:
            timeout_at = timeout_at.replace(tzinfo=timezone.utc)
        if isinstance(timeout_at, datetime) and datetime.now(timezone.utc) > timeout_at:
            request_data.status = "timeout"
            await db.commit()
            raise HTTPException(status_code=410, detail="Verification request expired")

        normalized_code = (code or "").strip()
        if not normalized_code.isdigit() or not 4 <= len(normalized_code) <= 10:
            raise HTTPException(status_code=400, detail="Invalid verification code")

        request_data.status = "completed"
        request_data.otp_code = normalized_code
        request_data.device_id = device_id
        request_data.completed_at = datetime.now(timezone.utc)
        await db.commit()

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
        raise HTTPException(
            status_code=500, detail="Failed to complete SMS verification"
        )


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
            "owner_user_id": current_user.id,
            "email": request.email,
            "sender_patterns": request.sender_patterns,
            "subject_patterns": request.subject_patterns,
            "status": "monitoring",
            "created_at": datetime.now(timezone.utc),
            "timeout_at": datetime.now(timezone.utc)
            + timedelta(seconds=request.timeout_seconds),
            "found_emails": [],
        }

        # Start background email monitoring
        # TODO: Implement actual email monitoring service

        logger.info(
            f"Email monitoring setup for {request.email}, monitor_id: {monitor_id}"
        )

        return {
            "monitor_id": monitor_id,
            "status": "monitoring",
            "message": f"Email monitoring started for {request.email}",
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
    sensitive. The application JWT must identify the exact local user that
    created the monitor. Foreign, unknown and legacy unbound IDs all return the
    same 404.
    """
    try:
        monitor_data = email_monitors.get(monitor_id)
        if monitor_data is None or monitor_data.get("owner_user_id") != current_user.id:
            raise HTTPException(status_code=404, detail="Email monitor not found")

        # Check if timeout exceeded
        timeout_at = monitor_data["timeout_at"]
        if timeout_at.tzinfo is None:
            timeout_at = timeout_at.replace(tzinfo=timezone.utc)
        if datetime.now(timezone.utc) > timeout_at:
            monitor_data["status"] = "timeout"

        return {
            "monitor_id": monitor_id,
            "status": monitor_data["status"],
            "found_emails": monitor_data["found_emails"],
            "timestamp": monitor_data.get("last_check"),
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

    SECURITY: Operator/app-facing — this dispatches automation commands to one
    explicitly selected, authenticated WebSocket device. Requires the
    application JWT so an unauthenticated caller cannot drive devices / inject
    commands. The command is bound to its creator for result retrieval. Device
    ownership/tenant policy remains a separate platform authorization gap.
    """
    try:
        command_id = str(uuid.uuid4())

        if not mobile_manager.is_device_connected(request.device_id):
            raise HTTPException(status_code=409, detail="Target device unavailable")

        command_data = {
            "command_id": command_id,
            "type": request.command_type,
            "parameters": request.parameters,
            "timeout": request.timeout_seconds,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }

        # Retain the owner binding server-side; never send it to the device.
        mobile_commands[command_id] = {
            "owner_user_id": current_user.id,
            "device_id": request.device_id,
            "status": "pending",
            "created_at": command_data["created_at"],
        }

        sent = await mobile_manager.send_to_device(
            json.dumps({"type": "automation_command", **command_data}),
            request.device_id,
        )
        if not sent:
            mobile_commands.pop(command_id, None)
            raise HTTPException(status_code=409, detail="Target device unavailable")

        logger.info(
            f"Mobile command sent: {request.command_type}, command_id: {command_id}"
        )

        return {
            "command_id": command_id,
            "status": "sent",
            "message": f"Command {request.command_type} sent to mobile device",
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error sending mobile command: {e}")
        raise HTTPException(status_code=500, detail="Failed to send mobile command")


@router.get("/mobile/get-command-result/{command_id}")
async def get_mobile_command_result(
    command_id: str,
    current_user: User = Depends(get_current_user),
):
    """Get result of mobile command execution.

    SECURITY: Operator/app-facing and owner-bound. Results may contain sensitive
    device output, so only the authenticated user that created the command may
    retrieve them. A foreign or unknown command has the same 404 response.
    """
    command = mobile_commands.get(command_id)
    if command is None or command.get("owner_user_id") != current_user.id:
        raise HTTPException(status_code=404, detail="Command not found")
    return {
        "command_id": command_id,
        "status": command["status"],
        "result": command.get("result"),
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
            "error_data": error_data,
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
            "success_data": success_data,
        }

        logger.info(f"Scraper success reported: {scraper_id} - {success_data}")

        return {"status": "success", "message": "Success reported"}

    except Exception as e:
        logger.error(f"Error reporting scraper success: {e}")
        raise HTTPException(status_code=500, detail="Failed to report success")


# WebSocket endpoints for real-time communication
@router.websocket("/ws/mobile-commands")
async def mobile_commands_websocket(
    websocket: WebSocket,
    db: AsyncSession = Depends(get_db),
):
    """WebSocket endpoint for mobile device command communication.

    The public device id is supplied as a query parameter and its issued secret
    as ``X-Device-Key`` during the handshake. Invalid clients are closed before
    acceptance so they cannot receive commands or inject results.
    """
    device_id = websocket.query_params.get("device_id", "")
    device_key = websocket.headers.get("x-device-key")
    if not await _verify_device(db, device_id, device_key):
        log_security_event(
            "infra_mobile_websocket_auth_failure",
            details={"device_id": device_id or "missing"},
        )
        await websocket.close(code=1008, reason="Device authentication failed")
        return

    await mobile_manager.connect(websocket, device_id)
    try:
        while True:
            data = await websocket.receive_text()
            message = json.loads(data)

            # Handle responses from mobile device
            if message.get("type") == "command_result":
                command_id = message.get("command_id")
                command = mobile_commands.get(command_id)
                if (
                    not isinstance(command_id, str)
                    or command is None
                    or command.get("status") != "pending"
                    or command.get("device_id") != device_id
                ):
                    log_security_event(
                        "infra_mobile_command_result_rejected",
                        details={"device_id": device_id},
                    )
                    continue

                # Bind result data to the server-issued command and target
                # device. Do not log arbitrary device-controlled payloads.
                command["status"] = "completed"
                command["result"] = message.get("result")
                command["completed_at"] = datetime.now(timezone.utc).isoformat()
                logger.info(
                    "Mobile command result accepted for %s from %s",
                    command_id,
                    device_id,
                )

    except WebSocketDisconnect:
        mobile_manager.disconnect(websocket, device_id)
    except Exception as e:
        logger.error(f"Mobile WebSocket error: {e}")
        mobile_manager.disconnect(websocket, device_id)


# Utility functions for scrapers
class InfrastructureAPI:
    """Helper class that scrapers can import and use"""

    @staticmethod
    async def request_sms_verification(
        site: str, phone_number: str, timeout: int = 300
    ) -> str:
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
