"""
Email monitoring service for capturing verification emails
"""

import os
import re
import logging
import asyncio
import imaplib
import email
import time
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass
from datetime import datetime, timedelta
from email.header import decode_header
from email.mime.text import MIMEText
import smtplib

logger = logging.getLogger(__name__)

@dataclass
class EmailCredentials:
    email: str
    password: str
    imap_server: str
    imap_port: int = 993
    smtp_server: Optional[str] = None
    smtp_port: int = 587

@dataclass
class EmailMatch:
    message_id: str
    sender: str
    subject: str
    content: str
    received_at: datetime
    verification_codes: List[str]
    links: List[str]

class EmailMonitor:
    """Monitor email accounts for verification emails"""
    
    def __init__(self, credentials: EmailCredentials):
        self.credentials = credentials
        self.imap_client = None
        self.is_monitoring = False
        self.monitors: Dict[str, Dict[str, Any]] = {}
    
    async def connect(self) -> bool:
        """Connect to email server"""
        try:
            self.imap_client = imaplib.IMAP4_SSL(
                self.credentials.imap_server,
                self.credentials.imap_port
            )
            
            self.imap_client.login(
                self.credentials.email,
                self.credentials.password
            )
            
            logger.info(f"Connected to email server for {self.credentials.email}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to connect to email server: {e}")
            return False
    
    def disconnect(self):
        """Disconnect from email server"""
        if self.imap_client:
            try:
                self.imap_client.close()
                self.imap_client.logout()
            except:
                pass
            self.imap_client = None
    
    async def setup_monitoring(
        self,
        monitor_id: str,
        sender_patterns: List[str],
        subject_patterns: List[str],
        timeout_seconds: int = 300
    ) -> bool:
        """Setup monitoring for specific email patterns"""
        
        if not self.imap_client:
            if not await self.connect():
                return False
        
        self.monitors[monitor_id] = {
            "sender_patterns": sender_patterns,
            "subject_patterns": subject_patterns,
            "timeout_at": datetime.utcnow() + timedelta(seconds=timeout_seconds),
            "found_emails": [],
            "status": "monitoring",
            "created_at": datetime.utcnow()
        }
        
        logger.info(f"Setup email monitoring {monitor_id} for patterns: {sender_patterns}")
        
        # Start monitoring if not already running
        if not self.is_monitoring:
            asyncio.create_task(self._monitoring_loop())
        
        return True
    
    async def get_monitoring_result(self, monitor_id: str) -> Optional[Dict[str, Any]]:
        """Get monitoring results"""
        if monitor_id not in self.monitors:
            return None
        
        monitor = self.monitors[monitor_id]
        
        # Check timeout
        if datetime.utcnow() > monitor["timeout_at"]:
            monitor["status"] = "timeout"
        
        return {
            "monitor_id": monitor_id,
            "status": monitor["status"],
            "found_emails": monitor["found_emails"],
            "created_at": monitor["created_at"].isoformat(),
            "timeout_at": monitor["timeout_at"].isoformat()
        }
    
    async def _monitoring_loop(self):
        """Main monitoring loop"""
        self.is_monitoring = True
        
        try:
            while self.monitors:
                await self._check_for_new_emails()
                await asyncio.sleep(5)  # Check every 5 seconds
                
                # Remove expired monitors
                expired = [
                    mid for mid, monitor in self.monitors.items()
                    if datetime.utcnow() > monitor["timeout_at"]
                ]
                
                for mid in expired:
                    self.monitors[mid]["status"] = "timeout"
                    # Keep for a bit longer for result retrieval
                    
        except Exception as e:
            logger.error(f"Email monitoring loop error: {e}")
        finally:
            self.is_monitoring = False
    
    async def _check_for_new_emails(self):
        """Check for new emails matching patterns"""
        if not self.imap_client:
            return
        
        try:
            # Select inbox
            self.imap_client.select("INBOX")
            
            # Search for recent emails (last 10 minutes)
            since_time = (datetime.utcnow() - timedelta(minutes=10)).strftime("%d-%b-%Y")
            status, messages = self.imap_client.search(None, f'SINCE "{since_time}"')
            
            if status != "OK":
                return
            
            message_ids = messages[0].split()
            
            # Process recent messages
            for msg_id in message_ids[-20:]:  # Check last 20 messages
                await self._process_email(msg_id)
                
        except Exception as e:
            logger.error(f"Error checking emails: {e}")
    
    async def _process_email(self, msg_id: bytes):
        """Process a single email"""
        try:
            status, msg_data = self.imap_client.fetch(msg_id, "(RFC822)")
            
            if status != "OK":
                return
            
            email_message = email.message_from_bytes(msg_data[0][1])
            
            # Extract email details
            sender = self._decode_header(email_message.get("From", ""))
            subject = self._decode_header(email_message.get("Subject", ""))
            date_str = email_message.get("Date", "")
            message_id = email_message.get("Message-ID", str(msg_id))
            
            # Get email content
            content = self._extract_email_content(email_message)
            
            # Parse date
            try:
                received_at = email.utils.parsedate_to_datetime(date_str)
            except:
                received_at = datetime.utcnow()
            
            # Extract verification codes and links
            verification_codes = self._extract_verification_codes(content)
            links = self._extract_links(content)
            
            email_match = EmailMatch(
                message_id=message_id,
                sender=sender,
                subject=subject,
                content=content,
                received_at=received_at,
                verification_codes=verification_codes,
                links=links
            )
            
            # Check against monitors
            await self._check_email_against_monitors(email_match)
            
        except Exception as e:
            logger.error(f"Error processing email: {e}")
    
    def _decode_header(self, header: str) -> str:
        """Decode email header"""
        try:
            decoded = decode_header(header)
            result = ""
            for text, encoding in decoded:
                if isinstance(text, bytes):
                    result += text.decode(encoding or 'utf-8')
                else:
                    result += text
            return result
        except:
            return header
    
    def _extract_email_content(self, email_message) -> str:
        """Extract text content from email"""
        content = ""
        
        if email_message.is_multipart():
            for part in email_message.walk():
                content_type = part.get_content_type()
                
                if content_type == "text/plain":
                    try:
                        payload = part.get_payload(decode=True)
                        if payload:
                            content += payload.decode('utf-8', errors='ignore')
                    except:
                        pass
        else:
            try:
                payload = email_message.get_payload(decode=True)
                if payload:
                    content = payload.decode('utf-8', errors='ignore')
            except:
                pass
        
        return content
    
    def _extract_verification_codes(self, content: str) -> List[str]:
        """Extract verification codes from email content"""
        codes = []
        
        # Common verification code patterns
        patterns = [
            r'\b\d{6}\b',                    # 6-digit codes
            r'\b\d{4}\b',                    # 4-digit codes
            r'\b\d{8}\b',                    # 8-digit codes
            r'code[\s:]+(\d{4,8})',          # "code: 123456"
            r'verification[\s:]+(\d{4,8})',  # "verification: 123456"
            r'confirm[\s:]+(\d{4,8})',       # "confirm: 123456"
        ]
        
        for pattern in patterns:
            matches = re.findall(pattern, content, re.IGNORECASE)
            codes.extend(matches)
        
        # Remove duplicates and filter reasonable lengths
        unique_codes = list(set(codes))
        return [code for code in unique_codes if 4 <= len(code) <= 8]
    
    def _extract_links(self, content: str) -> List[str]:
        """Extract links from email content"""
        # URL pattern
        url_pattern = r'https?://[^\s<>"\']+|www\.[^\s<>"\']+\.[a-zA-Z]{2,}'
        
        links = re.findall(url_pattern, content)
        return list(set(links))
    
    async def _check_email_against_monitors(self, email_match: EmailMatch):
        """Check email against all active monitors"""
        
        for monitor_id, monitor in self.monitors.items():
            if monitor["status"] != "monitoring":
                continue
            
            # Check sender patterns
            sender_match = any(
                re.search(pattern, email_match.sender, re.IGNORECASE)
                for pattern in monitor["sender_patterns"]
            )
            
            # Check subject patterns
            subject_match = any(
                re.search(pattern, email_match.subject, re.IGNORECASE)
                for pattern in monitor["subject_patterns"]
            )
            
            if sender_match or subject_match:
                monitor["found_emails"].append({
                    "message_id": email_match.message_id,
                    "sender": email_match.sender,
                    "subject": email_match.subject,
                    "content": email_match.content[:1000],  # Truncate content
                    "received_at": email_match.received_at.isoformat(),
                    "verification_codes": email_match.verification_codes,
                    "links": email_match.links
                })
                
                monitor["status"] = "found"
                
                logger.info(f"Email match found for monitor {monitor_id}: {email_match.subject}")

class EmailService:
    """Main email service managing multiple email accounts"""
    
    def __init__(self):
        self.monitors: Dict[str, EmailMonitor] = {}
        self.default_credentials = None
        self._load_email_credentials()
    
    def _load_email_credentials(self):
        """Load email credentials from environment"""
        email_addr = os.getenv("EMAIL_ADDRESS")
        email_password = os.getenv("EMAIL_PASSWORD")
        imap_server = os.getenv("IMAP_SERVER")
        imap_port = int(os.getenv("IMAP_PORT", "993"))
        smtp_server = os.getenv("SMTP_SERVER")
        smtp_port = int(os.getenv("SMTP_PORT", "587"))
        
        if email_addr and email_password and imap_server:
            self.default_credentials = EmailCredentials(
                email=email_addr,
                password=email_password,
                imap_server=imap_server,
                imap_port=imap_port,
                smtp_server=smtp_server,
                smtp_port=smtp_port
            )
            logger.info(f"Loaded default email credentials for {email_addr}")
        else:
            logger.warning("No default email credentials configured")
    
    async def setup_monitoring(
        self,
        monitor_id: str,
        email: str,
        sender_patterns: List[str],
        subject_patterns: List[str],
        timeout_seconds: int = 300,
        credentials: Optional[EmailCredentials] = None
    ) -> bool:
        """Setup email monitoring"""
        
        # Use provided credentials or default
        creds = credentials or self.default_credentials
        if not creds:
            logger.error("No email credentials available")
            return False
        
        # Create monitor for this email if not exists
        if email not in self.monitors:
            monitor_creds = EmailCredentials(
                email=email,
                password=creds.password,  # Use same password (or implement per-email creds)
                imap_server=creds.imap_server,
                imap_port=creds.imap_port,
                smtp_server=creds.smtp_server,
                smtp_port=creds.smtp_port
            )
            
            self.monitors[email] = EmailMonitor(monitor_creds)
        
        monitor = self.monitors[email]
        return await monitor.setup_monitoring(
            monitor_id, sender_patterns, subject_patterns, timeout_seconds
        )
    
    async def get_monitoring_result(self, monitor_id: str) -> Optional[Dict[str, Any]]:
        """Get monitoring results from any monitor"""
        
        for email, monitor in self.monitors.items():
            result = await monitor.get_monitoring_result(monitor_id)
            if result:
                return result
        
        return None
    
    def cleanup_monitors(self):
        """Cleanup all monitors"""
        for monitor in self.monitors.values():
            monitor.disconnect()
        self.monitors.clear()

# Common email provider configurations
EMAIL_PROVIDERS = {
    "gmail": {
        "imap_server": "imap.gmail.com",
        "imap_port": 993,
        "smtp_server": "smtp.gmail.com",
        "smtp_port": 587
    },
    "outlook": {
        "imap_server": "outlook.office365.com",
        "imap_port": 993,
        "smtp_server": "smtp-mail.outlook.com",
        "smtp_port": 587
    },
    "yahoo": {
        "imap_server": "imap.mail.yahoo.com",
        "imap_port": 993,
        "smtp_server": "smtp.mail.yahoo.com",
        "smtp_port": 587
    }
}

def get_email_credentials_for_provider(email: str, password: str, provider: str) -> EmailCredentials:
    """Get email credentials for common providers"""
    
    if provider.lower() not in EMAIL_PROVIDERS:
        raise ValueError(f"Unsupported email provider: {provider}")
    
    config = EMAIL_PROVIDERS[provider.lower()]
    
    return EmailCredentials(
        email=email,
        password=password,
        imap_server=config["imap_server"],
        imap_port=config["imap_port"],
        smtp_server=config["smtp_server"],
        smtp_port=config["smtp_port"]
    )

# Global email service instance
email_service = EmailService() 