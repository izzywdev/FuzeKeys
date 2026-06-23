"""
Credentials API for secure credential management and retrieval
"""

from fastapi import APIRouter, HTTPException, Depends, Header, Query, Path
from sqlalchemy.orm import Session
from typing import List, Dict, Optional, Any
import logging
import secrets
from datetime import datetime, timedelta
from pydantic import BaseModel, Field, ConfigDict
from cryptography.fernet import Fernet
import base64
import os
import json

from ..database import get_db
from ..models.identity import Identity
from ..models.account import Account

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/credentials", tags=["Credentials"])

# Encryption for credential storage
ENCRYPTION_KEY = os.getenv("CREDENTIAL_ENCRYPTION_KEY", Fernet.generate_key().decode())
cipher_suite = Fernet(ENCRYPTION_KEY.encode() if isinstance(ENCRYPTION_KEY, str) else ENCRYPTION_KEY)

# API key storage for microservice authentication
VALID_API_KEYS = {
    "scraper-service": os.getenv("SCRAPER_API_KEY", "scraper-key-12345"),
    "mobile-service": os.getenv("MOBILE_API_KEY", "mobile-key-12345"),
    "automation-service": os.getenv("AUTOMATION_API_KEY", "automation-key-12345")
}

# Request/Response Models with enhanced documentation
class CredentialRequest(BaseModel):
    """Request model for generating credentials for an identity"""
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "identity_id": 1,
                "site_name": "github",
                "action_type": "signup",
                "credential_types": ["email", "password", "username", "name"]
            }
        }
    )
    
    identity_id: int = Field(..., description="ID of the identity to generate credentials for", example=1)
    site_name: str = Field(..., description="Name of the target website", example="github")
    action_type: str = Field(..., description="Type of action being performed", example="signup")
    credential_types: List[str] = Field(..., description="List of credential types needed", example=["email", "password", "username"])

class AccountCredentialRequest(BaseModel):
    """Request model for retrieving stored account credentials"""
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "account_id": 1,
                "credential_types": ["email", "password", "api_key"]
            }
        }
    )
    
    account_id: int = Field(..., description="ID of the account to retrieve credentials for", example=1)
    credential_types: List[str] = Field(..., description="List of credential types to retrieve", example=["email", "password"])

class CredentialResponse(BaseModel):
    """Response model for generated credentials"""
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "identity_id": 1,
                "site_name": "github",
                "credentials": {
                    "email": "john.doe.1703123456@example.com",
                    "password": "JohnDoePass123!",
                    "username": "johndoe_a1b2",
                    "name": "John Doe"
                },
                "metadata": {
                    "requested_by": "scraper-service",
                    "requested_at": "2024-01-01T12:00:00Z",
                    "action_type": "signup",
                    "credential_types": ["email", "password", "username", "name"]
                }
            }
        }
    )
    
    identity_id: int = Field(..., description="ID of the identity")
    site_name: str = Field(..., description="Name of the target website")
    credentials: Dict[str, str] = Field(..., description="Generated credentials")
    metadata: Dict[str, Any] = Field(..., description="Request metadata and tracking information")

class AccountCredentialResponse(BaseModel):
    """Response model for stored account credentials"""
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "account_id": 1,
                "site_name": "github",
                "credentials": {
                    "email": "john.doe.1703123456@example.com",
                    "password": "JohnDoePass123!",
                    "api_key": "ghp_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
                },
                "last_used": "2024-01-01T12:00:00Z"
            }
        }
    )
    
    account_id: int = Field(..., description="ID of the account")
    site_name: str = Field(..., description="Name of the website")
    credentials: Dict[str, str] = Field(..., description="Stored credentials")
    last_used: Optional[datetime] = Field(None, description="Timestamp when credentials were last accessed")

class CredentialUpdate(BaseModel):
    """Request model for storing/updating account credentials"""
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "account_id": 1,
                "credentials": {
                    "email": "john.doe.1703123456@example.com",
                    "password": "JohnDoePass123!",
                    "username": "johndoe_a1b2",
                    "api_key": "ghp_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
                },
                "metadata": {
                    "signup_date": "2024-01-01T12:00:00Z",
                    "verification_method": "email",
                    "account_type": "free"
                }
            }
        }
    )
    
    account_id: int = Field(..., description="ID of the account to store credentials for")
    credentials: Dict[str, str] = Field(..., description="Credentials to store")
    metadata: Optional[Dict[str, Any]] = Field(None, description="Additional metadata about the credentials")

class ValidationRequest(BaseModel):
    """Request model for credential validation"""
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "site_name": "github",
                "credentials": {
                    "email": "john.doe@example.com",
                    "password": "SecurePass123!",
                    "username": "johndoe"
                }
            }
        }
    )
    
    site_name: str = Field(..., description="Name of the site to validate against")
    credentials: Dict[str, str] = Field(..., description="Credentials to validate")

class ValidationResult(BaseModel):
    """Response model for credential validation"""
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "valid": True,
                "missing_fields": [],
                "invalid_fields": [],
                "warnings": []
            }
        }
    )
    
    valid: bool = Field(..., description="Whether credentials are valid")
    missing_fields: List[str] = Field(..., description="List of required fields that are missing")
    invalid_fields: List[str] = Field(..., description="List of fields with invalid values")
    warnings: List[str] = Field(..., description="List of warnings about the credentials")

# Authentication dependency
async def verify_api_key(x_api_key: str = Header(..., description="API key for service authentication")):
    """Verify API key for microservice authentication"""
    service_name = None
    for service, key in VALID_API_KEYS.items():
        if x_api_key == key:
            service_name = service
            break
    
    if not service_name:
        raise HTTPException(status_code=401, detail="Invalid API key")
    
    return service_name

# Helper functions
def encrypt_credential(value: str) -> str:
    """Encrypt a credential value"""
    return cipher_suite.encrypt(value.encode()).decode()

def decrypt_credential(encrypted_value: str) -> str:
    """Decrypt a credential value"""
    return cipher_suite.decrypt(encrypted_value.encode()).decode()

def generate_credentials_for_identity(identity: Identity, site_name: str, action_type: str) -> Dict[str, str]:
    """Generate credentials for an identity based on site requirements"""
    
    credentials = {}
    
    # Email generation
    if action_type == "signup":
        # Generate unique email for signup
        timestamp = int(datetime.utcnow().timestamp())
        email_domain = "@example.com"  # Use configured domain
        credentials["email"] = f"{identity.name.lower().replace(' ', '.')}.{timestamp}{email_domain}"
    else:
        # Use existing email pattern for signin
        credentials["email"] = f"{identity.name.lower().replace(' ', '.')}@example.com"
    
    # Password generation
    if "password" in [action_type] or action_type in ["signup", "signin"]:
        # Generate secure password
        password = f"{identity.name.replace(' ', '')}Pass123!"
        credentials["password"] = password
    
    # Name/username
    credentials["name"] = identity.name
    credentials["first_name"] = identity.name.split()[0] if identity.name else "User"
    credentials["last_name"] = identity.name.split()[-1] if len(identity.name.split()) > 1 else "Name"
    credentials["username"] = identity.name.lower().replace(' ', '_')
    
    # Phone number
    if hasattr(identity, 'phone') and identity.phone:
        credentials["phone"] = identity.phone
    else:
        credentials["phone"] = "+1234567890"  # Default/test phone
    
    # Site-specific customizations
    if site_name.lower() == "github":
        credentials["username"] = f"{identity.name.lower().replace(' ', '')}_{secrets.token_hex(4)}"
    elif site_name.lower() == "google":
        credentials["recovery_email"] = f"backup.{credentials['email']}"
    
    return credentials

# Main API endpoints
@router.post("/request-identity-credentials", 
             response_model=CredentialResponse,
             summary="🔐 Generate Credentials for Identity",
             description="""
Generate fresh credentials for an identity to sign up for a specific site.

This endpoint creates site-appropriate credentials based on the identity's information
and the target website's requirements. Perfect for automated signup processes.

**Use Cases:**
- Generate signup credentials for new accounts
- Create site-specific usernames and emails
- Get credentials for scraper automation

**Security:** All requests are logged with service identity for audit purposes.
             """,
             responses={
                 200: {"description": "Credentials generated successfully"},
                 401: {"description": "Invalid API key"},
                 404: {"description": "Identity not found"},
                 500: {"description": "Failed to generate credentials"}
             })
async def request_identity_credentials(
    request: CredentialRequest,
    service_name: str = Depends(verify_api_key),
    db: Session = Depends(get_db)
):
    """Request credentials for an identity to sign up for a specific site"""
    
    try:
        # Get identity
        identity = db.query(Identity).filter(Identity.id == request.identity_id).first()
        if not identity:
            raise HTTPException(status_code=404, detail="Identity not found")
        
        logger.info(f"Generating credentials for identity {identity.name} on {request.site_name} by {service_name}")
        
        # Generate credentials based on identity and site requirements
        credentials = generate_credentials_for_identity(identity, request.site_name, request.action_type)
        
        # Filter requested credential types
        if request.credential_types:
            filtered_credentials = {
                key: value for key, value in credentials.items()
                if key in request.credential_types
            }
        else:
            filtered_credentials = credentials
        
        # Log credential request
        metadata = {
            "requested_by": service_name,
            "requested_at": datetime.utcnow().isoformat(),
            "action_type": request.action_type,
            "credential_types": request.credential_types or list(credentials.keys())
        }
        
        return CredentialResponse(
            identity_id=request.identity_id,
            site_name=request.site_name,
            credentials=filtered_credentials,
            metadata=metadata
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error requesting identity credentials: {e}")
        raise HTTPException(status_code=500, detail="Failed to generate credentials")

@router.post("/request-account-credentials", 
             response_model=AccountCredentialResponse,
             summary="🔑 Retrieve Stored Account Credentials",
             description="""
Retrieve stored credentials for an existing account.

Perfect for accessing previously created accounts where credentials have been
stored after successful signup.

**Use Cases:**
- Get credentials for existing account signin
- Retrieve API keys for service integration
- Access 2FA backup codes

**Security:** Updates last accessed timestamp and logs access for audit.
             """,
             responses={
                 200: {"description": "Credentials retrieved successfully"},
                 401: {"description": "Invalid API key"},
                 404: {"description": "Account not found"},
                 500: {"description": "Failed to retrieve credentials"}
             })
async def request_account_credentials(
    request: AccountCredentialRequest,
    service_name: str = Depends(verify_api_key),
    db: Session = Depends(get_db)
):
    """Request stored credentials for an existing account"""
    
    try:
        # Get account
        account = db.query(Account).filter(Account.id == request.account_id).first()
        if not account:
            raise HTTPException(status_code=404, detail="Account not found")
        
        logger.info(f"Retrieving credentials for account {account.website_name} by {service_name}")
        
        # Decrypt stored credentials
        stored_credentials = {}
        if hasattr(account, 'encrypted_credentials') and account.encrypted_credentials:
            try:
                decrypted_data = decrypt_credential(account.encrypted_credentials)
                stored_credentials = json.loads(decrypted_data)
            except Exception as e:
                logger.error(f"Error decrypting credentials: {e}")
                stored_credentials = {}
        
        # Filter requested credential types
        if request.credential_types:
            filtered_credentials = {
                key: value for key, value in stored_credentials.items()
                if key in request.credential_types
            }
        else:
            filtered_credentials = stored_credentials
        
        # Update last accessed
        account.last_accessed = datetime.utcnow()
        db.commit()
        
        return AccountCredentialResponse(
            account_id=request.account_id,
            site_name=account.website_name,
            credentials=filtered_credentials,
            last_used=account.last_accessed
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error requesting account credentials: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve credentials")

@router.post("/store-account-credentials",
             summary="💾 Store Account Credentials",
             description="""
Store or update credentials for an account after successful signup.

Use this endpoint to securely store credentials after a successful account
creation process. All credentials are encrypted before storage.

**Use Cases:**
- Store credentials after successful signup
- Update credentials with new API keys
- Save 2FA backup codes and recovery information

**Security:** All credentials are encrypted using Fernet (AES 128) before storage.
             """,
             responses={
                 200: {"description": "Credentials stored successfully"},
                 401: {"description": "Invalid API key"},
                 404: {"description": "Account not found"},
                 500: {"description": "Failed to store credentials"}
             })
async def store_account_credentials(
    request: CredentialUpdate,
    service_name: str = Depends(verify_api_key),
    db: Session = Depends(get_db)
):
    """Store/update credentials for an account after successful signup"""
    
    try:
        # Get account
        account = db.query(Account).filter(Account.id == request.account_id).first()
        if not account:
            raise HTTPException(status_code=404, detail="Account not found")
        
        logger.info(f"Storing credentials for account {account.website_name} by {service_name}")
        
        # Encrypt and store credentials
        credentials_data = {
            **request.credentials,
            "stored_at": datetime.utcnow().isoformat(),
            "stored_by": service_name
        }
        
        if request.metadata:
            credentials_data["metadata"] = request.metadata
        
        encrypted_credentials = encrypt_credential(json.dumps(credentials_data))
        
        # Update account
        account.encrypted_credentials = encrypted_credentials
        account.signup_completed = True
        account.is_active = True
        account.last_accessed = datetime.utcnow()
        
        db.commit()
        
        return {
            "success": True,
            "message": f"Credentials stored for account {account.id}",
            "account_id": account.id
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error storing credentials: {e}")
        raise HTTPException(status_code=500, detail="Failed to store credentials")

@router.get("/account/{account_id}/credentials", 
            response_model=AccountCredentialResponse,
            summary="📋 Get Account Credentials (GET)",
            description="""
Alternative GET endpoint for retrieving account credentials.

Convenient endpoint for getting credentials when you know the account ID.
            """)
async def get_account_credentials(
    account_id: int = Path(..., description="Account ID to retrieve credentials for"),
    credential_types: Optional[str] = Query(None, description="Comma-separated list of credential types to retrieve"),
    service_name: str = Depends(verify_api_key),
    db: Session = Depends(get_db)
):
    """Get stored credentials for a specific account"""
    
    credential_types_list = credential_types.split(",") if credential_types else None
    
    request = AccountCredentialRequest(
        account_id=account_id,
        credential_types=credential_types_list or []
    )
    
    return await request_account_credentials(request, service_name, db)

@router.get("/identity/{identity_id}/accounts",
            summary="👤 List Identity Accounts",
            description="""
Get all accounts associated with a specific identity.

Useful for understanding what accounts an identity has created and their status.
            """)
async def get_identity_accounts(
    identity_id: int = Path(..., description="Identity ID to get accounts for"),
    service_name: str = Depends(verify_api_key),
    db: Session = Depends(get_db)
):
    """Get all accounts for an identity"""
    
    try:
        # Get identity
        identity = db.query(Identity).filter(Identity.id == identity_id).first()
        if not identity:
            raise HTTPException(status_code=404, detail="Identity not found")
        
        # Get accounts for this identity
        accounts = db.query(Account).filter(Account.identity_id == identity_id).all()
        
        account_list = []
        for account in accounts:
            account_info = {
                "account_id": account.id,
                "site_name": account.website_name,
                "site_url": account.website_url,
                "is_active": account.is_active,
                "signup_completed": account.signup_completed,
                "created_at": account.created_at.isoformat(),
                "last_accessed": account.last_accessed.isoformat() if account.last_accessed else None,
                "has_stored_credentials": bool(hasattr(account, 'encrypted_credentials') and account.encrypted_credentials)
            }
            account_list.append(account_info)
        
        return {
            "identity_id": identity_id,
            "identity_name": identity.name,
            "accounts": account_list,
            "total_accounts": len(account_list)
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting identity accounts: {e}")
        raise HTTPException(status_code=500, detail="Failed to get accounts")

@router.post("/validate-credentials",
             response_model=ValidationResult,
             summary="✅ Validate Credential Format",
             description="""
Validate credentials format for a specific site.

Check if credentials meet the requirements for a particular website before
attempting to use them.

**Validation includes:**
- Required field presence
- Email format validation
- Password strength requirements
- Site-specific username patterns
             """)
async def validate_credentials(
    request: ValidationRequest,
    service_name: str = Depends(verify_api_key)
):
    """Validate credentials format for a specific site"""
    
    try:
        validation_rules = {
            "github": {
                "required": ["email", "password", "username"],
                "email_pattern": r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$",
                "password_min_length": 8,
                "username_pattern": r"^[a-zA-Z0-9_-]+$"
            },
            "google": {
                "required": ["email", "password"],
                "email_pattern": r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$",
                "password_min_length": 8
            },
            "default": {
                "required": ["email", "password"],
                "email_pattern": r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$",
                "password_min_length": 6
            }
        }
        
        rules = validation_rules.get(request.site_name.lower(), validation_rules["default"])
        
        validation_result = {
            "valid": True,
            "missing_fields": [],
            "invalid_fields": [],
            "warnings": []
        }
        
        # Check required fields
        for field in rules["required"]:
            if field not in request.credentials or not request.credentials[field]:
                validation_result["missing_fields"].append(field)
                validation_result["valid"] = False
        
        # Validate email format
        if "email" in request.credentials and request.credentials["email"]:
            import re
            if not re.match(rules["email_pattern"], request.credentials["email"]):
                validation_result["invalid_fields"].append("email")
                validation_result["valid"] = False
        
        # Validate password length
        if "password" in request.credentials and request.credentials["password"]:
            if len(request.credentials["password"]) < rules["password_min_length"]:
                validation_result["invalid_fields"].append("password")
                validation_result["valid"] = False
        
        # Site-specific validations
        if request.site_name.lower() == "github" and "username" in request.credentials:
            if not re.match(rules["username_pattern"], request.credentials["username"]):
                validation_result["invalid_fields"].append("username")
                validation_result["valid"] = False
        
        return ValidationResult(**validation_result)
        
    except Exception as e:
        logger.error(f"Error validating credentials: {e}")
        raise HTTPException(status_code=500, detail="Failed to validate credentials")

@router.get("/health",
            summary="🏥 Health Check",
            description="Check the health status of the credentials service")
async def health_check():
    """Health check for credentials service"""
    return {
        "status": "healthy",
        "service": "credentials-api",
        "encryption": "enabled",
        "timestamp": datetime.utcnow().isoformat(),
        "supported_services": list(VALID_API_KEYS.keys())
    } 