from fastapi import WebSocket, WebSocketDisconnect
from typing import List, Dict
import json
import logging

logger = logging.getLogger(__name__)

class ConnectionManager:
    """Manages WebSocket connections for real-time communication"""
    
    def __init__(self):
        self.active_connections: List[WebSocket] = []
        self.device_connections: Dict[str, WebSocket] = {}
    
    async def connect(self, websocket: WebSocket, device_id: str = None):
        """Accept a new WebSocket connection"""
        await websocket.accept()
        self.active_connections.append(websocket)
        
        if device_id:
            self.device_connections[device_id] = websocket
            logger.info(f"Device {device_id} connected via WebSocket")
        
        logger.info(f"New WebSocket connection. Total active: {len(self.active_connections)}")
    
    def disconnect(self, websocket: WebSocket, device_id: str = None):
        """Remove a WebSocket connection"""
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
        
        if device_id and device_id in self.device_connections:
            del self.device_connections[device_id]
            logger.info(f"Device {device_id} disconnected")
        
        logger.info(f"WebSocket disconnected. Total active: {len(self.active_connections)}")
    
    async def send_personal_message(self, message: str, websocket: WebSocket):
        """Send a message to a specific WebSocket connection"""
        try:
            await websocket.send_text(message)
        except Exception as e:
            logger.error(f"Error sending personal message: {e}")
            self.disconnect(websocket)
    
    async def send_to_device(self, message: str, device_id: str):
        """Send a message to a specific device"""
        if device_id in self.device_connections:
            websocket = self.device_connections[device_id]
            try:
                await websocket.send_text(message)
                return True
            except Exception as e:
                logger.error(f"Error sending message to device {device_id}: {e}")
                self.disconnect(websocket, device_id)
                return False
        else:
            logger.warning(f"Device {device_id} not connected")
            return False
    
    async def broadcast(self, message: str):
        """Send a message to all connected clients"""
        disconnected = []
        
        for connection in self.active_connections:
            try:
                await connection.send_text(message)
            except Exception as e:
                logger.error(f"Error broadcasting message: {e}")
                disconnected.append(connection)
        
        # Remove disconnected clients
        for connection in disconnected:
            self.disconnect(connection)
    
    async def broadcast_to_devices(self, message: str):
        """Send a message to all connected mobile devices"""
        disconnected_devices = []
        
        for device_id, websocket in self.device_connections.items():
            try:
                await websocket.send_text(message)
            except Exception as e:
                logger.error(f"Error broadcasting to device {device_id}: {e}")
                disconnected_devices.append(device_id)
        
        # Remove disconnected devices
        for device_id in disconnected_devices:
            if device_id in self.device_connections:
                self.disconnect(self.device_connections[device_id], device_id)
    
    def get_connected_devices(self) -> List[str]:
        """Get list of connected device IDs"""
        return list(self.device_connections.keys())
    
    def is_device_connected(self, device_id: str) -> bool:
        """Check if a specific device is connected"""
        return device_id in self.device_connections
    
    async def send_otp_request(self, service: str, request_id: str, timeout: float):
        """Send OTP request to all connected devices"""
        message = {
            "type": "otp_request",
            "service": service,
            "request_id": request_id,
            "timeout": timeout
        }
        await self.broadcast_to_devices(json.dumps(message))
    
    async def notify_otp_received(self, request_id: str, otp_code: str, device_id: str):
        """Notify about received OTP"""
        message = {
            "type": "otp_received",
            "request_id": request_id,
            "otp_code": otp_code,
            "device_id": device_id
        }
        await self.broadcast(json.dumps(message)) 