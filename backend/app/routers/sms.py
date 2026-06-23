from fastapi import APIRouter, HTTPException, Depends, WebSocket, WebSocketDisconnect
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from typing import List, Dict, Optional
from pydantic import BaseModel
import logging
import json
from datetime import datetime, timedelta
import uuid

from ..database import get_db
from ..models.sms import SmsDevice, SmsOtpRequest, SmsOtpReceived
from ..utils.websocket_manager import ConnectionManager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/sms", tags=["SMS"])
security = HTTPBearer()

# WebSocket connection manager for real-time communication
sms_manager = ConnectionManager()

# In-memory storage for pending OTP requests (in production, use Redis or database)
pending_otp_requests: Dict[str, Dict] = {}

class OtpRequest(BaseModel):
    otp: str
    sender: str
    message_body: str
    timestamp: int
    device_id: str
    confidence: Optional[float] = None

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
        
        # Generate API key (in production, use proper JWT or API key generation)
        api_key = str(uuid.uuid4())
        
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
async def receive_otp(request: OtpRequest, db: Session = Depends(get_db)):
    """Receive OTP code from mobile app"""
    try:
        logger.info(f"Received OTP {request.otp} from device {request.device_id}")
        
        # Store the received OTP
        otp_received = SmsOtpReceived(
            device_id=request.device_id,
            otp_code=request.otp,
            sender=request.sender,
            message_body=request.message_body,
            confidence=request.confidence,
            received_at=datetime.fromtimestamp(request.timestamp / 1000),
            processed_at=datetime.utcnow()
        )
        db.add(otp_received)
        
        # Check if this OTP matches any pending requests
        matching_request = None
        for request_id, pending_request in pending_otp_requests.items():
            if pending_request.get("status") == "waiting":
                # Simple matching logic - you can make this more sophisticated
                matching_request = pending_request
                matching_request["status"] = "completed"
                matching_request["otp_code"] = request.otp
                matching_request["completed_at"] = datetime.utcnow().isoformat()
                break
        
        db.commit()
        
        # Notify any waiting WebSocket connections
        if matching_request:
            await sms_manager.broadcast(json.dumps({
                "type": "otp_received",
                "request_id": request_id,
                "otp": request.otp,
                "device_id": request.device_id
            }))
        
        # Update device last seen
        device = db.query(SmsDevice).filter(SmsDevice.device_id == request.device_id).first()
        if device:
            device.last_seen = datetime.utcnow()
            db.commit()
        
        return {
            "success": True,
            "message": "OTP received successfully",
            "request_id": request_id if matching_request else None
        }
        
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