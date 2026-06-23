from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks
from sqlalchemy.orm import Session
from typing import List, Dict, Optional, Any
import logging
import json
import uuid
from datetime import datetime, timedelta
from pydantic import BaseModel

from ..database import get_db
from ..utils.websocket_manager import ConnectionManager
from ..models.sms import SmsDevice, SmsOtpRequest, SmsOtpReceived

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
async def request_sms_verification(request: SmsVerificationRequest, db: Session = Depends(get_db)):
    """Request SMS verification from mobile device for scraper use"""
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
async def get_sms_verification(request_id: str):
    """Get SMS verification code for scraper"""
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
async def complete_sms_verification(request_id: str, code: str, device_id: str):
    """Called by mobile device to complete SMS verification"""
    try:
        if request_id not in verification_requests:
            raise HTTPException(status_code=404, detail="Verification request not found")
        
        verification_requests[request_id].update({
            "status": "completed",
            "code": code,
            "device_id": device_id,
            "completed_at": datetime.utcnow()
        })
        
        logger.info(f"SMS verification completed for request {request_id} with code {code}")
        
        return {"status": "success", "message": "Verification completed"}
        
    except Exception as e:
        logger.error(f"Error completing SMS verification: {e}")
        raise HTTPException(status_code=500, detail="Failed to complete SMS verification")

# Email Verification APIs
@router.post("/email/setup-monitoring", response_model=Dict[str, str])
async def setup_email_monitoring(request: EmailMonitoringRequest):
    """Setup email monitoring for verification emails"""
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
async def get_email_verification(monitor_id: str):
    """Get email verification content"""
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
async def send_mobile_command(request: MobileCommandRequest):
    """Send command to mobile device for UI automation"""
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
async def get_mobile_command_result(command_id: str):
    """Get result of mobile command execution"""
    # TODO: Implement command result tracking
    # This would store results from mobile device responses
    return {
        "command_id": command_id,
        "status": "pending",
        "result": None
    }

# Helper APIs for scrapers
@router.post("/scraper/report-error")
async def report_scraper_error(scraper_id: str, error_data: Dict[str, Any]):
    """Report scraper execution error for analysis"""
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
async def report_scraper_success(scraper_id: str, success_data: Dict[str, Any]):
    """Report scraper execution success"""
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
    """WebSocket endpoint for mobile device command communication"""
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