import hashlib
import hmac
import json
import logging
import os
import re
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

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
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

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
# New endpoints must use the platform's versioned API namespace. Keep the
# legacy router above only for the existing mobile-client surface while it is
# migrated under the separately tracked API-version debt.
assignment_router = APIRouter(prefix="/api/v1/sms", tags=["SMS"])
security = HTTPBearer()

# WebSocket connection manager for real-time communication
sms_manager = ConnectionManager()

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


def _device_key_digest(api_key: str) -> str:
    """Return the fixed-length one-way digest retained for device authentication."""
    return hashlib.sha256(api_key.encode("utf-8")).hexdigest()


async def _verify_device(
    db: AsyncSession, device_id: str, api_key: Optional[str]
) -> bool:
    """Verify one active device against its durable one-way key digest."""
    if not device_id or not api_key:
        return False
    result = await db.execute(
        select(SmsDevice).where(
            SmsDevice.device_id == device_id,
            SmsDevice.is_active.is_(True),
        )
    )
    device = result.scalar_one_or_none()
    expected_digest = device.device_key_hash if device else None
    if not isinstance(expected_digest, str) or len(expected_digest) != 64:
        return False
    return hmac.compare_digest(expected_digest, _device_key_digest(api_key))


def _utc(value: datetime) -> datetime:
    """Normalize database datetimes for safe UTC comparisons."""
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


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
    db: AsyncSession = Depends(get_db),
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

        existing_device = (
            await db.execute(
                select(SmsDevice).where(SmsDevice.device_id == request.device_id)
            )
        ).scalar_one_or_none()
        api_key = secrets.token_urlsafe(32)
        key_hash = _device_key_digest(api_key)
        rotated_at = datetime.now(timezone.utc)

        if existing_device:
            existing_device.device_name = request.device_name
            existing_device.os_version = request.os_version
            existing_device.app_version = request.app_version
            existing_device.last_seen = rotated_at
            existing_device.is_active = True
            existing_device.device_key_hash = key_hash
            existing_device.key_rotated_at = rotated_at
        else:
            new_device = SmsDevice(
                device_id=request.device_id,
                device_name=request.device_name,
                os_version=request.os_version,
                app_version=request.app_version,
                is_active=True,
                device_key_hash=key_hash,
                key_rotated_at=rotated_at,
                created_at=rotated_at,
                last_seen=rotated_at,
            )
            db.add(new_device)

        # Device metadata and the rotated digest commit atomically. The plaintext
        # key is returned once and is never retained by the service.
        await db.commit()

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
    db: AsyncSession = Depends(get_db),
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
        if not await _verify_device(db, request.device_id, x_device_key):
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
        pending_request = (
            await db.execute(
                select(SmsOtpRequest)
                .where(SmsOtpRequest.request_id == request_id)
                .with_for_update()
            )
        ).scalar_one_or_none()
        if pending_request is None:
            log_security_event(
                "sms_otp_unknown_request",
                details={"device_id": request.device_id, "request_id": request_id},
            )
            raise HTTPException(status_code=404, detail="Request not found")

        # 3a) The request must still be open.
        if pending_request.status != "waiting":
            log_security_event(
                "sms_otp_request_not_waiting",
                details={
                    "device_id": request.device_id,
                    "request_id": request_id,
                    "status": pending_request.status,
                },
            )
            raise HTTPException(
                status_code=409, detail="Request is not awaiting an OTP"
            )

        # 3b) The request must not have expired.
        if _utc(pending_request.timeout_at) < datetime.now(timezone.utc):
            pending_request.status = "timeout"
            await db.commit()
            log_security_event(
                "sms_otp_request_expired",
                details={"device_id": request.device_id, "request_id": request_id},
            )
            raise HTTPException(status_code=410, detail="Request has expired")

        # 3c) Verify the submitting device is the one assigned to this request.
        #     Never let a device claim an unassigned request merely by knowing its
        #     id. Assignment is an authorization decision owned by the server-side
        #     orchestration lifecycle; polling already withholds unassigned work.
        assigned_device = pending_request.assigned_device_id
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
            received_at=datetime.fromtimestamp(
                request.timestamp / 1000, tz=timezone.utc
            ),
            processed_at=datetime.now(timezone.utc),
            matched_request_id=request_id,
        )
        db.add(otp_received)

        # 5) Complete the bound request.
        pending_request.status = "completed"
        pending_request.otp_code = otp
        pending_request.completed_at = datetime.now(timezone.utc)
        pending_request.device_id = request.device_id

        device = (
            await db.execute(
                select(SmsDevice).where(SmsDevice.device_id == request.device_id)
            )
        ).scalar_one_or_none()
        if device:
            device.last_seen = datetime.now(timezone.utc)
        await db.commit()

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
    db: AsyncSession = Depends(get_db),
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
        if not await _verify_device(db, device_id, x_device_key):
            log_security_event(
                "sms_requests_auth_failure",
                details={
                    "device_id": device_id,
                    "reason": "invalid_or_missing_device_key",
                },
            )
            raise HTTPException(status_code=401, detail="Device authentication failed")

        rows = (
            await db.execute(
                select(SmsOtpRequest)
                .where(
                    SmsOtpRequest.assigned_device_id == device_id,
                    SmsOtpRequest.status == "waiting",
                    SmsOtpRequest.timeout_at > datetime.now(timezone.utc),
                )
                .order_by(SmsOtpRequest.created_at, SmsOtpRequest.request_id)
            )
        ).scalars()
        return [
            {
                "request_id": row.request_id,
                "service": row.service,
                "timestamp": _utc(row.created_at).timestamp(),
                "status": row.status,
                "timeout": _utc(row.timeout_at).timestamp(),
            }
            for row in rows
        ]

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
    db: AsyncSession = Depends(get_db),
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
        now = datetime.now(timezone.utc)
        timeout_at = now + timedelta(seconds=timeout_seconds)

        # Store the OTP request
        otp_request = SmsOtpRequest(
            request_id=request_id,
            service=service,
            status="waiting",
            owner_user_id=current_user.id,
            created_at=now,
            timeout_at=timeout_at,
        )
        db.add(otp_request)
        await db.commit()

        # Do not broadcast an unassigned request. Assignment is intentionally a
        # separate, unfinished authorization lifecycle; exposing this id to every
        # connected device would let a device race to claim work it does not own.

        logger.info(f"OTP requested for service {service}, request_id: {request_id}")

        return {
            "success": True,
            "request_id": request_id,
            "timeout": timeout_at.timestamp(),
            "message": f"OTP request created for {service}",
        }

    except Exception as e:
        logger.error(f"Error requesting OTP: {e}")
        raise HTTPException(status_code=500, detail="Failed to create OTP request")


@assignment_router.post("/requests/{request_id}/assign/{device_id}")
async def assign_otp_request(
    request_id: str,
    device_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Bind one creator-owned OTP request to one active device instance."""
    otp_request = (
        await db.execute(
            select(SmsOtpRequest)
            .where(
                SmsOtpRequest.request_id == request_id,
                SmsOtpRequest.owner_user_id == current_user.id,
            )
            .with_for_update()
        )
    ).scalar_one_or_none()
    if otp_request is None:
        raise HTTPException(status_code=404, detail="Request not found")
    if otp_request.status != "waiting":
        raise HTTPException(status_code=409, detail="Request is not awaiting an OTP")
    if _utc(otp_request.timeout_at) < datetime.now(timezone.utc):
        otp_request.status = "timeout"
        await db.commit()
        raise HTTPException(status_code=410, detail="Request has expired")

    device = (
        await db.execute(
            select(SmsDevice).where(
                SmsDevice.device_id == device_id,
                SmsDevice.is_active.is_(True),
                SmsDevice.device_key_hash.is_not(None),
            )
        )
    ).scalar_one_or_none()
    if device is None:
        raise HTTPException(status_code=404, detail="Device not found")

    otp_request.assigned_device_id = device.device_id
    await db.commit()
    await sms_manager.send_to_device(
        json.dumps({"type": "otp_request_available", "request_id": request_id}),
        device.device_id,
    )
    log_security_event(
        "sms_otp_request_assigned",
        user_id=current_user.id,
        details={"request_id": request_id, "device_id": device.device_id},
    )
    return {
        "success": True,
        "request_id": request_id,
        "device_id": device.device_id,
    }


@router.get("/request-status/{request_id}")
async def get_request_status(
    request_id: str,
    db: AsyncSession = Depends(get_db),
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
        request_data = (
            await db.execute(
                select(SmsOtpRequest).where(
                    SmsOtpRequest.request_id == request_id,
                    SmsOtpRequest.owner_user_id == current_user.id,
                )
            )
        ).scalar_one_or_none()
        if request_data is None:
            raise HTTPException(status_code=404, detail="Request not found")
        return {
            "request_id": request_id,
            "status": request_data.status,
            "otp_code": request_data.otp_code,
            "created_at": _utc(request_data.created_at).timestamp(),
            "completed_at": (
                _utc(request_data.completed_at).isoformat()
                if request_data.completed_at
                else None
            ),
            "timeout": _utc(request_data.timeout_at).timestamp(),
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
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get all registered SMS devices.

    SECURITY: This lists the full device inventory (ids, names, OS/app
    versions, activity) which is sensitive operational/PII-ish data and an
    enumeration aid for attackers. It is an operator/admin view, so it requires
    the application JWT. Not a device callback, so device-key auth does not fit.
    """
    try:
        total = (
            await db.execute(select(func.count()).select_from(SmsDevice))
        ).scalar_one()
        devices = (
            await db.execute(
                select(SmsDevice)
                .order_by(SmsDevice.device_id)
                .offset(offset)
                .limit(limit)
            )
        ).scalars()
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
async def sms_interceptor_websocket(
    websocket: WebSocket,
    db: AsyncSession = Depends(get_db),
):
    """WebSocket endpoint for real-time communication with mobile apps.

    The native mobile client supplies its public ``device_id`` as a query
    parameter and the issued secret in ``X-Device-Key`` during the WebSocket
    handshake. The key never enters the URL. Invalid clients are closed before
    they join the manager, so they cannot observe request identifiers or status.
    """
    device_id = websocket.query_params.get("device_id", "")
    device_key = websocket.headers.get("x-device-key")
    if not await _verify_device(db, device_id, device_key):
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
async def health_check(db: AsyncSession = Depends(get_db)):
    """Health check endpoint.

    SECURITY: Left unauthenticated by design — health/liveness probes are
    called by infrastructure (load balancers, k8s) before any auth context
    exists. It returns only coarse counts (active connections, pending request
    count), not OTP values, device ids, or other sensitive data, so no auth is
    required.
    """
    pending_count = (
        await db.execute(
            select(func.count())
            .select_from(SmsOtpRequest)
            .where(SmsOtpRequest.status == "waiting")
        )
    ).scalar_one()
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "version": "1.0.0",
        "active_devices": len(sms_manager.active_connections),
        "pending_requests": pending_count,
    }
