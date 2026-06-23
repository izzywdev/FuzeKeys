"""
Google integration API routes.
"""

import logging
from typing import Dict, Any
from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.identity import Identity
from app.models.account import Account
from app.models.user import User
from app.integrations.google.backend.signup import GoogleSignupService
from app.integrations.google.backend.models import GoogleSignupConfig, GoogleSignupData, GoogleSignupResult
from app.utils.encryption import encrypt_field

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/google", tags=["Google Integration"])


@router.post("/signup/{identity_id}")
async def signup_with_identity(
    identity_id: int,
    config: GoogleSignupConfig = None,
    background_tasks: BackgroundTasks = None,
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """
    Create a Google account using the specified identity.
    """
    try:
        # Get the identity
        identity = db.query(Identity).filter(Identity.id == identity_id).first()
        if not identity:
            raise HTTPException(status_code=404, detail="Identity not found")
        
        # Create signup service
        signup_service = GoogleSignupService(config or GoogleSignupConfig())
        
        # Perform signup
        result = await signup_service.signup_with_identity(identity)
        
        # If successful, create account record
        if result.success and result.account_email:
            account = Account(
                identity_id=identity_id,
                platform="google",
                email=result.account_email,
                encrypted_username=encrypt_field(result.account_email.split('@')[0]),
                encrypted_password=encrypt_field(""),  # Password stored separately for security
                status="active" if result.success else "verification_required",
                metadata={
                    "account_id": result.account_id,
                    "verification_type": result.verification_type,
                    "additional_data": result.additional_data
                }
            )
            db.add(account)
            db.commit()
            db.refresh(account)
            
            return {
                "success": True,
                "message": "Google account created successfully",
                "account_id": account.id,
                "account_email": result.account_email,
                "verification_required": result.verification_required,
                "verification_type": result.verification_type
            }
        else:
            return {
                "success": False,
                "message": result.error_message or "Failed to create Google account",
                "verification_required": result.verification_required,
                "verification_type": result.verification_type
            }
            
    except Exception as e:
        logger.error(f"Error in Google signup: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.post("/signup/manual")
async def manual_signup(
    signup_data: GoogleSignupData,
    config: GoogleSignupConfig = None,
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """
    Create a Google account with manually provided data.
    """
    try:
        # Create signup service
        signup_service = GoogleSignupService(config or GoogleSignupConfig())
        
        # Perform signup
        result = await signup_service.signup(signup_data)
        
        return {
            "success": result.success,
            "message": result.error_message if not result.success else "Google account created successfully",
            "account_email": result.account_email,
            "account_id": result.account_id,
            "verification_required": result.verification_required,
            "verification_type": result.verification_type,
            "additional_data": result.additional_data
        }
        
    except Exception as e:
        logger.error(f"Error in manual Google signup: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.get("/config/default")
async def get_default_config() -> GoogleSignupConfig:
    """
    Get the default configuration for Google signup.
    """
    return GoogleSignupConfig()


@router.post("/test/identity-conversion/{identity_id}")
async def test_identity_conversion(
    identity_id: int,
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """
    Test converting an identity to Google signup data without actually creating an account.
    """
    try:
        # Get the identity
        identity = db.query(Identity).filter(Identity.id == identity_id).first()
        if not identity:
            raise HTTPException(status_code=404, detail="Identity not found")
        
        # Create signup service
        signup_service = GoogleSignupService()
        
        # Convert identity to signup data
        signup_data = await signup_service._identity_to_signup_data(identity)
        
        return {
            "success": True,
            "message": "Identity conversion successful",
            "signup_data": {
                "first_name": signup_data.first_name,
                "last_name": signup_data.last_name,
                "username": signup_data.username,
                "has_password": bool(signup_data.password),
                "phone_number": signup_data.phone_number,
                "recovery_email": signup_data.recovery_email,
                "birth_date": str(signup_data.birth_date) if signup_data.birth_date else None,
                "gender": signup_data.gender
            }
        }
        
    except Exception as e:
        logger.error(f"Error in identity conversion test: {str(e)}")
        raise HTTPException(status_code=400, detail=f"Conversion error: {str(e)}")


@router.get("/accounts/{identity_id}")
async def get_google_accounts(
    identity_id: int,
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """
    Get all Google accounts for a specific identity.
    """
    try:
        # Get Google accounts for this identity
        accounts = db.query(Account).filter(
            Account.identity_id == identity_id,
            Account.platform == "google"
        ).all()
        
        return {
            "success": True,
            "accounts": [
                {
                    "id": account.id,
                    "email": account.email,
                    "status": account.status,
                    "created_at": account.created_at.isoformat(),
                    "metadata": account.metadata
                }
                for account in accounts
            ]
        }
        
    except Exception as e:
        logger.error(f"Error getting Google accounts: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}") 