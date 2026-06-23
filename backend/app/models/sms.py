from sqlalchemy import Column, Integer, String, Boolean, DateTime, Float, Text
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime

Base = declarative_base()

class SmsDevice(Base):
    """Model for registered SMS interceptor devices"""
    __tablename__ = "sms_devices"
    
    id = Column(Integer, primary_key=True, index=True)
    device_id = Column(String(255), unique=True, index=True, nullable=False)
    device_name = Column(String(255), nullable=False)
    os_version = Column(String(100), nullable=True)
    app_version = Column(String(50), nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    last_seen = Column(DateTime, nullable=True)
    
    def __repr__(self):
        return f"<SmsDevice(device_id='{self.device_id}', name='{self.device_name}', active={self.is_active})>"

class SmsOtpRequest(Base):
    """Model for OTP requests made by the system"""
    __tablename__ = "sms_otp_requests"
    
    id = Column(Integer, primary_key=True, index=True)
    request_id = Column(String(255), unique=True, index=True, nullable=False)
    service = Column(String(255), nullable=False)  # Which service the OTP is for
    status = Column(String(50), default="waiting")  # waiting, completed, timeout, failed
    otp_code = Column(String(20), nullable=True)  # The actual OTP code when received
    created_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)
    timeout_at = Column(DateTime, nullable=False)
    device_id = Column(String(255), nullable=True)  # Which device fulfilled the request
    
    def __repr__(self):
        return f"<SmsOtpRequest(request_id='{self.request_id}', service='{self.service}', status='{self.status}')>"

class SmsOtpReceived(Base):
    """Model for OTP codes received from mobile devices"""
    __tablename__ = "sms_otp_received"
    
    id = Column(Integer, primary_key=True, index=True)
    device_id = Column(String(255), nullable=False, index=True)
    otp_code = Column(String(20), nullable=False)
    sender = Column(String(255), nullable=True)  # SMS sender number/name
    message_body = Column(Text, nullable=True)  # Full SMS message content
    confidence = Column(Float, nullable=True)  # Confidence score of OTP detection
    received_at = Column(DateTime, nullable=False)  # When SMS was received
    processed_at = Column(DateTime, default=datetime.utcnow)  # When processed by server
    matched_request_id = Column(String(255), nullable=True)  # If matched to a request
    
    def __repr__(self):
        return f"<SmsOtpReceived(device_id='{self.device_id}', otp='{self.otp_code}', confidence={self.confidence})>"

class SmsStatistics(Base):
    """Model for SMS interception statistics"""
    __tablename__ = "sms_statistics"
    
    id = Column(Integer, primary_key=True, index=True)
    device_id = Column(String(255), nullable=False, index=True)
    date = Column(DateTime, default=datetime.utcnow)
    total_sms_processed = Column(Integer, default=0)
    otps_detected = Column(Integer, default=0)
    otps_matched = Column(Integer, default=0)
    average_confidence = Column(Float, nullable=True)
    
    def __repr__(self):
        return f"<SmsStatistics(device_id='{self.device_id}', date='{self.date}', otps_detected={self.otps_detected})>" 