from fastapi import APIRouter, HTTPException, Depends, WebSocket, WebSocketDisconnect, Header
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from typing import List, Dict, Optional
from pydantic import BaseModel
import logging
import json
import re
import secrets
import hmac
from datetime import datetime, timedelta
import uuid

from ..database import get_db
from ..models.sms import SmsDevice, SmsOtpRequest, SmsOtpReceived
from ..utils.websocket_manager import ConnectionManager
from ..utils.logging import log_security_event

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
    device_id: str
    device_name: str
    os_version: str
    app_version: str

@router.post("/register-device")
async def register_device(request: DeviceRegistrationRequest, db: Session = Depends(get_db)):
    """Register a new SMS interceptor device"""
    try:
        # Check if device already exists
        existing_device = db.query(SmsDevice).filter(SmsDevice.device_id == request.device_id).first()
        
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
                last_seen=datetime.utcnow()
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
            "api_key": api_key
        }
        
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
            raise HTTPException(status_code=409, detail="Request is not awaiting an OTP")

        # 3b) The request must not have expired.
        timeout_ts = pending_request.get("timeout", 0)
        if timeout_ts and timeout_ts < datetime.utcnow().timestamp():
            pending_request["status"] = "timeout"
            log_security_event(
                "sms_otp_request_expired",
                details={"device_id": request.device_id, "request_id": request_id},
            )
            raise HTTPException(status_code=410, detail="Request has expired")

        # 3c) Verify the submitting device is the one assigned to this request.
        #     A request may be assigned to a device at creation time; if it was
        #     never assigned (legacy/unassigned), we bind it to the first
        #     authenticated device that answers and record the assignment so a
        #     different device cannot also complete it.
        assigned_device = pending_request.get("assigned_device_id")
        if assigned_device is None:
            pending_request["assigned_device_id"] = request.device_id
        elif not hmac.compare_digest(str(assigned_device), str(request.device_id)):
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

        # Notify any waiting WebSocket connections.
        await sms_manager.broadcast(json.dumps({
            "type": "otp_received",
            "request_id": request_id,
            "device_id": request.device_id,
            # NOTE: the OTP itself is intentionally NOT broadcast.
        }))

        # Update device last seen.
        device = db.query(SmsDevice).filter(SmsDevice.device_id == request.device_id).first()
        if device:
            device.last_seen = datetime.utcnow()
            db.commit()

        return {
            "success": True,
            "message": "OTP received successfully",
            "request_id": request_id
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error receiving OTP: {e}")
        raise HTTPException(status_code=500, detail="Failed to process OTP")

@router.get("/requests/{device_id}")
async def get_otp_requests(device_id: str, db: Session = Depends(get_db)):
    """Get pending OTP requests for a device"""
    try:
        # Return pending requests for this device
        device_requests = []
        for request_id, request_data in pending_otp_requests.items():
            if (request_data.get("status") == "waiting" and 
                request_data.get("timeout", 0) > datetime.utcnow().timestamp()):
                device_requests.append({
                    "request_id": request_id,
                    "service": request_data.get("service", "Unknown"),
                    "timestamp": request_data.get("created_at", 0),
                    "status": request_data.get("status"),
                    "timeout": request_data.get("timeout")
                })
        
        return device_requests
        
    except Exception as e:
        logger.error(f"Error getting OTP requests: {e}")
        raise HTTPException(status_code=500, detail="Failed to get OTP requests")

@router.post("/request-otp")
async def request_otp(service: str, timeout_seconds: int = 300, db: Session = Depends(get_db)):
    """Request an OTP for a specific service (called by your main app)"""
    try:
        request_id = str(uuid.uuid4())
        timeout_timestamp = (datetime.utcnow() + timedelta(seconds=timeout_seconds)).timestamp()
        
        # Store the OTP request
        otp_request = SmsOtpRequest(
            request_id=request_id,
            service=service,
            status="waiting",
            created_at=datetime.utcnow(),
            timeout_at=datetime.fromtimestamp(timeout_timestamp)
        )
        db.add(otp_request)
        db.commit()
        
        # Add to pending requests
        pending_otp_requests[request_id] = {
            "service": service,
            "status": "waiting",
            "created_at": datetime.utcnow().timestamp(),
            "timeout": timeout_timestamp
        }
        
        # Notify connected mobile devices
        await sms_manager.broadcast(json.dumps({
            "type": "otp_request",
            "request_id": request_id,
            "service": service,
            "timeout": timeout_timestamp
        }))
        
        logger.info(f"OTP requested for service {service}, request_id: {request_id}")
        
        return {
            "success": True,
            "request_id": request_id,
            "timeout": timeout_timestamp,
            "message": f"OTP request created for {service}"
        }
        
    except Exception as e:
        logger.error(f"Error requesting OTP: {e}")
        raise HTTPException(status_code=500, detail="Failed to create OTP request")

@router.get("/request-status/{request_id}")
async def get_request_status(request_id: str, db: Session = Depends(get_db)):
    """Get the status of an OTP request"""
    try:
        if request_id in pending_otp_requests:
            request_data = pending_otp_requests[request_id]
            return {
                "request_id": request_id,
                "status": request_data.get("status"),
                "otp_code": request_data.get("otp_code"),
                "created_at": request_data.get("created_at"),
                "completed_at": request_data.get("completed_at"),
                "timeout": request_data.get("timeout")
            }
        else:
            # Check database
            db_request = db.query(SmsOtpRequest).filter(SmsOtpRequest.request_id == request_id).first()
            if db_request:
                return {
                    "request_id": request_id,
                    "status": db_request.status,
                    "otp_code": db_request.otp_code,
                    "created_at": db_request.created_at.timestamp(),
                    "completed_at": db_request.completed_at.timestamp() if db_request.completed_at else None,
                    "timeout": db_request.timeout_at.timestamp()
                }
            else:
                raise HTTPException(status_code=404, detail="Request not found")
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting request status: {e}")
        raise HTTPException(status_code=500, detail="Failed to get request status")

@router.get("/devices")
async def get_devices(db: Session = Depends(get_db)):
    """Get all registered SMS devices"""
    try:
        devices = db.query(SmsDevice).all()
        return [
            {
                "device_id": device.device_id,
                "device_name": device.device_name,
                "os_version": device.os_version,
                "app_version": device.app_version,
                "is_active": device.is_active,
                "created_at": device.created_at.isoformat(),
                "last_seen": device.last_seen.isoformat() if device.last_seen else None
            }
            for device in devices
        ]
        
    except Exception as e:
        logger.error(f"Error getting devices: {e}")
        raise HTTPException(status_code=500, detail="Failed to get devices")

@router.websocket("/ws/sms-interceptor")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for real-time communication with mobile apps"""
    await sms_manager.connect(websocket)
    try:
        while True:
            # Keep the connection alive and handle incoming messages
            data = await websocket.receive_text()
            message = json.loads(data)
            
            # Handle different message types from mobile app
            if message.get("type") == "ping":
                await websocket.send_text(json.dumps({"type": "pong"}))
            elif message.get("type") == "device_status":
                # Handle device status updates
                logger.info(f"Device status update: {message}")
                
    except WebSocketDisconnect:
        sms_manager.disconnect(websocket)
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        sms_manager.disconnect(websocket)

@router.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "version": "1.0.0",
        "active_devices": len(sms_manager.active_connections),
        "pending_requests": len(pending_otp_requests)
    } 