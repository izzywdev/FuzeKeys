import asyncio
import imaplib
import email
import re
import ssl
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import smtplib
from dataclasses import dataclass
import logging
from urllib.parse import urlparse
import aiohttp

logger = logging.getLogger(__name__)

@dataclass
class EmailConfig:
    """Email account configuration for monitoring"""
    email_address: str
    password: str
    imap_server: str
    imap_port: int = 993
    smtp_server: str = ""
    smtp_port: int = 587
    use_ssl: bool = True

@dataclass
class VerificationEmail:
    """Represents a verification email"""
    sender: str
    subject: str
    body: str
    verification_link: Optional[str] = None
    verification_code: Optional[str] = None
    received_date: Optional[datetime] = None
    website: Optional[str] = None

class EmailVerificationService:
    """Service for monitoring and processing verification emails"""
    
    def __init__(self, email_configs: List[EmailConfig]):
        self.email_configs = email_configs
        self.running = False
        self.check_interval = 30  # seconds
        
    async def start_monitoring(self):
        """Start monitoring email accounts for verification emails"""
        self.running = True
        logger.info("Starting email verification monitoring...")
        
        while self.running:
            try:
                for config in self.email_configs:
                    await self._check_email_account(config)
                await asyncio.sleep(self.check_interval)
            except Exception as e:
                logger.error(f"Error in email monitoring: {e}")
                await asyncio.sleep(self.check_interval)
    
    def stop_monitoring(self):
        """Stop monitoring email accounts"""
        self.running = False
        logger.info("Stopped email verification monitoring")
    
    async def _check_email_account(self, config: EmailConfig):
        """Check a single email account for verification emails"""
        try:
            # Connect to IMAP server
            if config.use_ssl:
                mail = imaplib.IMAP4_SSL(config.imap_server, config.imap_port)
            else:
                mail = imaplib.IMAP4(config.imap_server, config.imap_port)
            
            mail.login(config.email_address, config.password)
            mail.select('inbox')
            
            # Search for recent unread emails
            since_date = (datetime.now() - timedelta(hours=1)).strftime("%d-%b-%Y")
            result, message_ids = mail.search(None, f'(UNSEEN SINCE "{since_date}")')
            
            if result == 'OK' and message_ids[0]:
                for message_id in message_ids[0].split():
                    verification_email = await self._process_email(mail, message_id, config)
                    if verification_email:
                        await self._handle_verification_email(verification_email, config)
            
            mail.logout()
            
        except Exception as e:
            logger.error(f"Error checking email account {config.email_address}: {e}")
    
    async def _process_email(self, mail, message_id: bytes, config: EmailConfig) -> Optional[VerificationEmail]:
        """Process a single email and extract verification information"""
        try:
            result, msg_data = mail.fetch(message_id, '(RFC822)')
            if result != 'OK':
                return None
            
            email_body = msg_data[0][1]
            email_message = email.message_from_bytes(email_body)
            
            sender = email_message['From']
            subject = email_message['Subject']
            date_str = email_message['Date']
            
            # Extract email body
            body = ""
            if email_message.is_multipart():
                for part in email_message.walk():
                    if part.get_content_type() == "text/plain":
                        body += part.get_payload(decode=True).decode('utf-8', errors='ignore')
                    elif part.get_content_type() == "text/html":
                        body += part.get_payload(decode=True).decode('utf-8', errors='ignore')
            else:
                body = email_message.get_payload(decode=True).decode('utf-8', errors='ignore')
            
            # Check if this looks like a verification email
            if self._is_verification_email(sender, subject, body):
                verification_email = VerificationEmail(
                    sender=sender,
                    subject=subject,
                    body=body,
                    received_date=datetime.now()
                )
                
                # Extract verification link and code
                verification_email.verification_link = self._extract_verification_link(body)
                verification_email.verification_code = self._extract_verification_code(body)
                verification_email.website = self._identify_website(sender, subject, body)
                
                return verification_email
                
        except Exception as e:
            logger.error(f"Error processing email: {e}")
        
        return None
    
    def _is_verification_email(self, sender: str, subject: str, body: str) -> bool:
        """Check if an email is likely a verification email"""
        verification_keywords = [
            'verify', 'verification', 'confirm', 'activation', 'validate',
            'account', 'email', 'click', 'link', 'code', 'complete'
        ]
        
        text_to_check = f"{sender} {subject} {body}".lower()
        
        # Must contain at least 2 verification keywords
        keyword_count = sum(1 for keyword in verification_keywords if keyword in text_to_check)
        
        # Common verification email patterns
        verification_patterns = [
            r'verify your email',
            r'confirm your account',
            r'activate your account',
            r'complete your registration',
            r'verification code',
            r'click.*verify',
            r'click.*confirm'
        ]
        
        pattern_match = any(re.search(pattern, text_to_check, re.IGNORECASE) for pattern in verification_patterns)
        
        return keyword_count >= 2 or pattern_match
    
    def _extract_verification_link(self, body: str) -> Optional[str]:
        """Extract verification link from email body"""
        # Common verification link patterns
        link_patterns = [
            r'https?://[^\s<>"]+(?:verify|confirm|activate|validation)[^\s<>"]*',
            r'https?://[^\s<>"]+[?&](?:token|code|key)=[^\s<>"&]+',
            r'https?://[^\s<>"]+/(?:verify|confirm|activate|validation)[^\s<>"]*',
        ]
        
        for pattern in link_patterns:
            matches = re.findall(pattern, body, re.IGNORECASE)
            if matches:
                # Return the first match, cleaned up
                link = matches[0].rstrip('.,;!?)')
                return link
        
        # Fallback: look for any HTTP link
        general_links = re.findall(r'https?://[^\s<>"]+', body)
        for link in general_links:
            if any(keyword in link.lower() for keyword in ['verify', 'confirm', 'activate', 'token', 'validation']):
                return link.rstrip('.,;!?)')
        
        return None
    
    def _extract_verification_code(self, body: str) -> Optional[str]:
        """Extract verification code from email body"""
        # Common verification code patterns
        code_patterns = [
            r'verification code[:\s]+([A-Z0-9]{4,8})',
            r'confirm code[:\s]+([A-Z0-9]{4,8})',
            r'your code[:\s]+([A-Z0-9]{4,8})',
            r'code[:\s]+([A-Z0-9]{4,8})',
            r'([A-Z0-9]{6})',  # 6-digit codes
            r'([0-9]{4,8})',   # 4-8 digit codes
        ]
        
        for pattern in code_patterns:
            matches = re.findall(pattern, body, re.IGNORECASE)
            if matches:
                return matches[0]
        
        return None
    
    def _identify_website(self, sender: str, subject: str, body: str) -> Optional[str]:
        """Identify which website sent the verification email"""
        text_to_check = f"{sender} {subject} {body}".lower()
        
        # Common website identifiers
        websites = {
            'github': ['github', 'noreply@github.com'],
            'linkedin': ['linkedin', 'noreply@linkedin.com'],
            'twitter': ['twitter', 'x.com', 'noreply@twitter.com'],
            'facebook': ['facebook', 'noreply@facebook.com'],
            'google': ['google', 'gmail', 'noreply@google.com'],
            'microsoft': ['microsoft', 'outlook', 'noreply@microsoft.com'],
            'reddit': ['reddit', 'noreply@reddit.com'],
            'stackoverflow': ['stackoverflow', 'stack overflow', 'noreply@stackoverflow.com'],
            'discord': ['discord', 'noreply@discord.com'],
            'slack': ['slack', 'noreply@slack.com']
        }
        
        for website, identifiers in websites.items():
            if any(identifier in text_to_check for identifier in identifiers):
                return website
        
        # Try to extract domain from sender email
        email_match = re.search(r'@([a-zA-Z0-9.-]+\.[a-zA-Z]{2,})', sender)
        if email_match:
            domain = email_match.group(1)
            return domain.split('.')[0] if domain.split('.')[0] != 'noreply' else domain
        
        return None
    
    async def _handle_verification_email(self, verification_email: VerificationEmail, config: EmailConfig):
        """Handle a detected verification email"""
        logger.info(f"Found verification email from {verification_email.sender} for {verification_email.website}")
        
        # Store in database or trigger automation
        await self._store_verification_email(verification_email, config.email_address)
        
        # Auto-process if we have a verification link
        if verification_email.verification_link:
            await self._auto_verify_email(verification_email)
    
    async def _store_verification_email(self, verification_email: VerificationEmail, email_account: str):
        """Store verification email in database"""
        # TODO: Implement database storage
        logger.info(f"Storing verification email: {verification_email.website} - {verification_email.verification_link}")
    
    async def _auto_verify_email(self, verification_email: VerificationEmail):
        """Automatically click verification link"""
        if not verification_email.verification_link:
            return
        
        try:
            async with aiohttp.ClientSession() as session:
                # Use a realistic user agent
                headers = {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
                }
                
                async with session.get(verification_email.verification_link, headers=headers) as response:
                    if response.status == 200:
                        logger.info(f"Successfully verified email for {verification_email.website}")
                    else:
                        logger.warning(f"Verification link returned status {response.status}")
                        
        except Exception as e:
            logger.error(f"Error auto-verifying email: {e}")

# Common email provider configurations
COMMON_EMAIL_CONFIGS = {
    'gmail': {
        'imap_server': 'imap.gmail.com',
        'imap_port': 993,
        'smtp_server': 'smtp.gmail.com',
        'smtp_port': 587,
        'use_ssl': True
    },
    'outlook': {
        'imap_server': 'outlook.office365.com',
        'imap_port': 993,
        'smtp_server': 'smtp-mail.outlook.com',
        'smtp_port': 587,
        'use_ssl': True
    },
    'yahoo': {
        'imap_server': 'imap.mail.yahoo.com',
        'imap_port': 993,
        'smtp_server': 'smtp.mail.yahoo.com',
        'smtp_port': 587,
        'use_ssl': True
    }
}

def create_email_config(email_address: str, password: str, provider: str = None) -> EmailConfig:
    """Create email configuration for common providers"""
    if provider and provider.lower() in COMMON_EMAIL_CONFIGS:
        config_data = COMMON_EMAIL_CONFIGS[provider.lower()]
        return EmailConfig(
            email_address=email_address,
            password=password,
            **config_data
        )
    
    # Auto-detect provider from email domain
    domain = email_address.split('@')[1].lower()
    if 'gmail' in domain:
        provider = 'gmail'
    elif 'outlook' in domain or 'hotmail' in domain or 'live' in domain:
        provider = 'outlook'
    elif 'yahoo' in domain:
        provider = 'yahoo'
    else:
        # Default configuration
        return EmailConfig(
            email_address=email_address,
            password=password,
            imap_server=f'imap.{domain}',
            smtp_server=f'smtp.{domain}'
        )
    
    config_data = COMMON_EMAIL_CONFIGS[provider]
    return EmailConfig(
        email_address=email_address,
        password=password,
        **config_data
    ) 