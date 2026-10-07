import hmac
import json
import logging
import os
import re
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

from fastapi import (
    APIRouter,
    Depends,
    Header,
    HTTPException,
    Query,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.utils.pagination import Page, PageInfo

from ..database import get_db
from ..models.sms import SmsDevice, SmsOtpReceived, SmsOtpRequest
from ..models.user import User
from ..utils.logging import log_security_event
from ..utils.websocket_manager import ConnectionManager

# SECURITY: operator/user-facing endpoints require the application JWT.
# get_current_user validates the bearer token and resolves the User.
from .auth import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/sms", tags=["SMS"])
security = HTTPBearer()

# WebSocket connection manager for real-time communication
sms_manager = ConnectionManager()

# In-memory storage for pending OTP requests (in production, use Redis or database)
pending_otp_requests: Dict[str, Dict] = {}

# SECURITY: Module-level store mapping device_id -> issued API key.
# The SmsDevice ORM model (app/models/sms.py) has no column to persist the
# per-device API key, and this fix is scoped to sms.py only, so the key is
# persisted here. This is consistent with the file's existing in-memory
# approach (see pending_otp_requests above).
# PRODUCTION NOTE: replace with a persistent, hashed key store (e.g. a
# `device_api_key_hash` column on SmsDevice or a Redis/secret store) so keys
# survive restarts and are never stored in plaintext. Keys here are kept in
# memory only and compared with a constant-time comparison.
registered_device_keys: Dict[str, str] = {}

# Minimum / maximum accepted OTP length and the allowed character set.
OTP_MIN_LEN = 4
OTP_MAX_LEN = 10
_OTP_PATTERN = re.compile(r"^\d{%d,%d}$" % (OTP_MIN_LEN, OTP_MAX_LEN))
_ENROLLMENT_TOKEN_ENV = "SMS_DEVICE_ENROLLMENT_TOKEN"


def _require_device_enrollment_token(presented: Optional[str]) -> None:
    """Require a strong out-of-band token before issuing or rotating device keys."""
    configured = os.getenv(_ENROLLMENT_TOKEN_ENV, "").strip()
    if len(configured) < 32:
        raise HTTPException(
            status_code=503,
            detail="Device enrollment is not configured",
        )
    if not presented or not hmac.compare_digest(
        configured.encode("utf-8"), presented.encode("utf-8")
    ):
        raise HTTPException(status_code=401, detail="Device enrollment denied")


def _verify_device(device_id: str, api_key: Optional[str]) -> bool:
    """Constant-time verification that the supplied api_key was issued to device_id."""
    if not device_id or not api_key:
        return False
    expected = registered_device_keys.get(device_id)
    if not expected:
        return False
    # hmac.compare_digest guards against timing attacks on the key comparison.
    return hmac.compare_digest(expected, api_key)


class OtpRequest(BaseModel):
    otp: str
    sender: str
    message_body: str
    timestamp: int
    device_id: str
    confidence: Optional[float] = None
    # SECURITY: bind every OTP submission to a specific pending request.
    # The device must tell us which request it is fulfilling; we no longer
    # silently complete the "first waiting" request.
    request_id: str


class DeviceRegistrationRequest(BaseModel):
    model_config = {"extra": "forbid"}
    device_id: str
    device_name: str
    os_version: str
    app_version: str


@router.post("/register-device")
async def register_device(
    request: DeviceRegistrationRequest,
    x_enrollment_token: Optional[str] = Header(
        default=None, alias="X-Enrollment-Token"
    ),
    db: Session = Depends(get_db),
):
    """Register a new SMS interceptor device.

    This bootstrap issues or rotates a device API key, so it requires the strong
    out-of-band ``X-Enrollment-Token`` configured in
    ``SMS_DEVICE_ENROLLMENT_TOKEN``. Missing/short server configuration fails
    closed with 503; missing or wrong client proof returns 401 before any device
    lookup or mutation. The token is never accepted in the URL or logged.
    """
    try:
        _require_device_enrollment_token(x_enrollment_token)

        # Check if device already exists
        existing_device = (
            db.query(SmsDevice).filter(SmsDevice.device_id == request.device_id).first()
        )

        if existing_device:
            # Update existing device
            existing_device.device_name = request.device_name
            existing_device.os_version = request.os_version
            existing_device.app_version = request.app_version
            existing_device.last_seen = datetime.utcnow()
            existing_device.is_active = True
        else:
            # Create new device
            new_device = SmsDevice(
                device_id=request.device_id,
                device_name=request.device_name,
                os_version=request.os_version,
                app_version=request.app_version,
                is_active=True,
                created_at=datetime.utcnow(),
                last_seen=datetime.utcnow(),
            )
            db.add(new_device)

        db.commit()

        # SECURITY: Generate a cryptographically strong API key and PERSIST it
        # so it can actually be verified on subsequent device-authenticated
        # calls (previously a uuid was returned but never stored or checked,
        # leaving /otp completely unauthenticated).
        # PRODUCTION NOTE: store a hash of this key, not the plaintext, in a
        # durable store; also support rotation/expiry.
        api_key = secrets.token_urlsafe(32)
        registered_device_keys[request.device_id] = api_key

        log_security_event(
            "sms_device_registered",
            details={"device_id": request.device_id},
        )

        return {
            "success": True,
            "message": "Device registered successfully",
            "device_id": request.device_id,
            "api_key": api_key,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error registering device: {e}")
        raise HTTPException(status_code=500, detail="Failed to register device")


@router.post("/otp")
async def receive_otp(
    request: OtpRequest,
    x_device_key: Optional[str] = Header(default=None, alias="X-Device-Key"),
    db: Session = Depends(get_db),
):
    """Receive OTP code from mobile app.

    SECURITY: This endpoint accepts device-submitted data and is therefore
    authenticated. The submitting device must present the API key it was
    issued at registration (via the ``X-Device-Key`` header) and must specify
    which pending request it is fulfilling. The device is then verified to be
    the device that owns/was assigned that request. This closes the OTP
    hijacking hole where any unauthenticated caller could complete the
    "first waiting" request with an attacker-controlled OTP.
    """
    try:
        # 1) Authenticate the device. Reject unknown / unauthenticated devices.
        if not _verify_device(request.device_id, x_device_key):
            log_security_event(
                "sms_otp_auth_failure",
                details={
                    "device_id": request.device_id,
                    "request_id": request.request_id,
                    "reason": "invalid_or_missing_device_key",
                },
            )
            raise HTTPException(status_code=401, detail="Device authentication failed")

        # 2) Validate the OTP format minimally (non-empty, digits, length bounds).
        otp = (request.otp or "").strip()
        if not _OTP_PATTERN.match(otp):
            log_security_event(
                "sms_otp_invalid_format",
                details={
                    "device_id": request.device_id,
                    "request_id": request.request_id,
                },
            )
            raise HTTPException(status_code=400, detail="Invalid OTP format")

        # 3) Bind the OTP to the SPECIFIC request named by the device.
        #    No more "first waiting" matching.
        request_id = request.request_id
        pending_request = pending_otp_requests.get(request_id)
        if pending_request is None:
            log_security_event(
                "sms_otp_unknown_request",
                details={"device_id": request.device_id, "request_id": request_id},
            )
            raise HTTPException(status_code=404, detail="Request not found")

        # 3a) The request must still be open.
        if pending_request.get("status") != "waiting":
            log_security_event(
                "sms_otp_request_not_waiting",
                details={
                    "device_id": request.device_id,
                    "request_id": request_id,
                    "status": pending_request.get("status"),
                },
            )
            raise HTTPException(
                status_code=409, detail="Request is not awaiting an OTP"
            )

        # 3b) The request must not have expired.
        timeout_ts = pending_request.get("timeout", 0)
        if timeout_ts and timeout_ts < datetime.now(timezone.utc).timestamp():
            pending_request["status"] = "timeout"
            log_security_event(
                "sms_otp_request_expired",
                details={"device_id": request.device_id, "request_id": request_id},
            )
            raise HTTPException(status_code=410, detail="Request has expired")

        # 3c) Verify the submitting device is the one assigned to this request.
        #     Never let a device claim an unassigned request merely by knowing its
        #     id. Assignment is an authorization decision owned by the server-side
        #     orchestration lifecycle; polling already withholds unassigned work.
        assigned_device = pending_request.get("assigned_device_id")
        if not isinstance(assigned_device, str) or not assigned_device:
            log_security_event(
                "sms_otp_request_unassigned",
                details={
                    "device_id": request.device_id,
                    "request_id": request_id,
                },
            )
            raise HTTPException(
                status_code=409,
                detail="Request has no authorized device assignment",
            )
        if not hmac.compare_digest(assigned_device, request.device_id):
            log_security_event(
                "sms_otp_device_mismatch",
                details={
                    "device_id": request.device_id,
                    "request_id": request_id,
                    "assigned_device_id": assigned_device,
                },
            )
            raise HTTPException(
                status_code=403,
                detail="Device is not assigned to this request",
            )

        # 4) Store the received OTP (now that the caller is authenticated and bound).
        otp_received = SmsOtpReceived(
            device_id=request.device_id,
            otp_code=otp,
            sender=request.sender,
            message_body=request.message_body,
            confidence=request.confidence,
            received_at=datetime.fromtimestamp(request.timestamp / 1000),
            processed_at=datetime.utcnow(),
            matched_request_id=request_id,
        )
        db.add(otp_received)

        # 5) Complete the bound request.
        pending_request["status"] = "completed"
        pending_request["otp_code"] = otp
        pending_request["completed_at"] = datetime.utcnow().isoformat()

        db.commit()

        log_security_event(
            "sms_otp_completed",
            details={"device_id": request.device_id, "request_id": request_id},
        )

        # Notify only the assigned device. Other authenticated devices must not
        # learn that this request exists or whether it completed.
        await sms_manager.send_to_device(
            json.dumps(
                {
                    "type": "otp_received",
                    "request_id": request_id,
                    "device_id": request.device_id,
                    # NOTE: the OTP itself is intentionally NOT broadcast.
                }
            ),
            request.device_id,
        )

        # Update device last seen.
        device = (
            db.query(SmsDevice).filter(SmsDevice.device_id == request.device_id).first()
        )
        if device:
            device.last_seen = datetime.utcnow()
            db.commit()

        return {
            "success": True,
            "message": "OTP received successfully",
            "request_id": request_id,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error receiving OTP: {e}")
        raise HTTPException(status_code=500, detail="Failed to process OTP")


@router.get("/requests/{device_id}")
async def get_otp_requests(
    device_id: str,
    x_device_key: Optional[str] = Header(default=None, alias="X-Device-Key"),
    db: Session = Depends(get_db),
):
    """Get pending OTP requests for a device.

    SECURITY: This is a DEVICE-to-server callback (the mobile interceptor polls
    for work it should fulfil), so it is authenticated with the per-device API
    key exactly like ``/otp`` — not the user JWT. The device must present the
    ``X-Device-Key`` it was issued at registration, and that key must belong to
    the ``device_id`` in the path, preventing one device from enumerating
    another device's pending requests. Unknown/unauthenticated devices get 401.
    """
    try:
        # Authenticate the calling device against the device_id in the path.
        if not _verify_device(device_id, x_device_key):
            log_security_event(
                "sms_requests_auth_failure",
                details={
                    "device_id": device_id,
                    "reason": "invalid_or_missing_device_key",
                },
            )
            raise HTTPException(status_code=401, detail="Device authentication failed")

        # Return pending requests for this device
        device_requests = []
        for request_id, request_data in pending_otp_requests.items():
            if (
                request_data.get("status") == "waiting"
                and request_data.get("timeout", 0)
                > datetime.now(timezone.utc).timestamp()
                and isinstance(request_data.get("assigned_device_id"), str)
                and hmac.compare_digest(request_data["assigned_device_id"], device_id)
            ):
                device_requests.append(
                    {
                        "request_id": request_id,
                        "service": request_data.get("service", "Unknown"),
                        "timestamp": request_data.get("created_at", 0),
                        "status": request_data.get("status"),
                        "timeout": request_data.get("timeout"),
                    }
                )

        return device_requests

    except HTTPException:
        # Preserve auth/validation status codes (e.g. 401) — don't mask as 500.
        raise
    except Exception as e:
        logger.error(f"Error getting OTP requests: {e}")
        raise HTTPException(status_code=500, detail="Failed to get OTP requests")


@router.post("/request-otp")
async def request_otp(
    service: str,
    timeout_seconds: int = 300,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Request an OTP for a specific service (called by your main app).

    SECURITY: This is an OPERATOR/USER-facing action (the main app asks the
    platform to wait for an OTP for a given service), so it requires the
    application JWT via get_current_user. An unauthenticated caller could
    otherwise spam OTP requests / push fake jobs to devices. Devices do not
    call this endpoint, so device-key auth is not appropriate here.
    """
    try:
        request_id = str(uuid.uuid4())
        timeout_timestamp = (
            datetime.now(timezone.utc) + timedelta(seconds=timeout_seconds)
        ).timestamp()

        # Store the OTP request
        otp_request = SmsOtpRequest(
            request_id=request_id,
            service=service,
            status="waiting",
            created_at=datetime.utcnow(),
            timeout_at=datetime.fromtimestamp(timeout_timestamp),
        )
        db.add(otp_request)
        db.commit()

        # Add to pending requests
        pending_otp_requests[request_id] = {
            "service": service,
            "status": "waiting",
            "owner_user_id": current_user.id,
            "created_at": datetime.now(timezone.utc).timestamp(),
            "timeout": timeout_timestamp,
        }

        # Do not broadcast an unassigned request. Assignment is intentionally a
        # separate, unfinished authorization lifecycle; exposing this id to every
        # connected device would let a device race to claim work it does not own.

        logger.info(f"OTP requested for service {service}, request_id: {request_id}")

        return {
            "success": True,
            "request_id": request_id,
            "timeout": timeout_timestamp,
            "message": f"OTP request created for {service}",
        }

    except Exception as e:
        logger.error(f"Error requesting OTP: {e}")
        raise HTTPException(status_code=500, detail="Failed to create OTP request")


@router.get("/request-status/{request_id}")
async def get_request_status(
    request_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get the status of an OTP request.

    SECURITY: This endpoint returns the received OTP value itself
    (``otp_code``), which is highly sensitive. It requires both the application
    JWT and an exact creator binding recorded when the request was made. Foreign,
    unknown and legacy unbound request IDs all return the same 404. Device-key
    auth is not used because devices submit OTPs; they do not read them back.
    """
    try:
        request_data = pending_otp_requests.get(request_id)
        if request_data is None or request_data.get("owner_user_id") != current_user.id:
            # The legacy database row has no verifiable owner field and must not
            # become an authenticated-but-cross-user OTP disclosure fallback.
            raise HTTPException(status_code=404, detail="Request not found")
        return {
            "request_id": request_id,
            "status": request_data.get("status"),
            "otp_code": request_data.get("otp_code"),
            "created_at": request_data.get("created_at"),
            "completed_at": request_data.get("completed_at"),
            "timeout": request_data.get("timeout"),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting request status: {e}")
        raise HTTPException(status_code=500, detail="Failed to get request status")


@router.get("/devices", response_model=Page[dict])
async def get_devices(
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get all registered SMS devices.

    SECURITY: This lists the full device inventory (ids, names, OS/app
    versions, activity) which is sensitive operational/PII-ish data and an
    enumeration aid for attackers. It is an operator/admin view, so it requires
    the application JWT. Not a device callback, so device-key auth does not fit.
    """
    try:
        total = db.query(SmsDevice).count()
        devices = (
            db.query(SmsDevice)
            .order_by(SmsDevice.device_id)
            .offset(offset)
            .limit(limit)
            .all()
        )
        items = [
            {
                "device_id": device.device_id,
                "device_name": device.device_name,
                "os_version": device.os_version,
                "app_version": device.app_version,
                "is_active": device.is_active,
                "created_at": device.created_at.isoformat(),
                "last_seen": device.last_seen.isoformat() if device.last_seen else None,
            }
            for device in devices
        ]
        return Page(
            items=items,
            page=PageInfo(
                offset=offset,
                limit=limit,
                total=total,
                next_offset=offset + limit if offset + limit < total else None,
            ),
        )

    except Exception as e:
        logger.error(f"Error getting devices: {e}")
        raise HTTPException(status_code=500, detail="Failed to get devices")


@router.websocket("/ws/sms-interceptor")
async def sms_interceptor_websocket(websocket: WebSocket):
    """WebSocket endpoint for real-time communication with mobile apps.

    The native mobile client supplies its public ``device_id`` as a query
    parameter and the issued secret in ``X-Device-Key`` during the WebSocket
    handshake. The key never enters the URL. Invalid clients are closed before
    they join the manager, so they cannot observe request identifiers or status.
    """
    device_id = websocket.query_params.get("device_id", "")
    device_key = websocket.headers.get("x-device-key")
    if not _verify_device(device_id, device_key):
        log_security_event(
            "sms_websocket_auth_failure",
            details={"device_id": device_id or "missing"},
        )
        await websocket.close(code=1008, reason="Device authentication failed")
        return

    await sms_manager.connect(websocket, device_id)
    try:
        while True:
            # Keep the connection alive and handle incoming messages
            data = await websocket.receive_text()
            message = json.loads(data)

            # Handle different message types from mobile app
            if message.get("type") == "ping":
                await websocket.send_text(json.dumps({"type": "pong"}))
            elif message.get("type") == "device_status":
                # Do not log arbitrary device-supplied payloads.
                logger.info("Device status update from %s", device_id)

    except WebSocketDisconnect:
        sms_manager.disconnect(websocket, device_id)
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        sms_manager.disconnect(websocket, device_id)


@router.get("/health", openapi_extra={"x-pagination": "exempt"})
async def health_check():
    """Health check endpoint.

    SECURITY: Left unauthenticated by design — health/liveness probes are
    called by infrastructure (load balancers, k8s) before any auth context
    exists. It returns only coarse counts (active connections, pending request
    count), not OTP values, device ids, or other sensitive data, so no auth is
    required.
    """
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "version": "1.0.0",
        "active_devices": len(sms_manager.active_connections),
        "pending_requests": len(pending_otp_requests),
    }
