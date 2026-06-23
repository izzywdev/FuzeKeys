from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload
from pydantic import BaseModel
from typing import List, Optional, Dict
from datetime import datetime

from app.database import get_db
from app.models.user import User
from app.models.account import Account, AccountStage, StageType, StageStatus
from app.models.identity import Identity
from app.routers.auth import get_current_user
from app.utils.logging import get_logger
from app.utils.encryption import encrypt_field, decrypt_field

logger = get_logger(__name__)
router = APIRouter()


class StageStatusResponse(BaseModel):
    stage_type: str
    stage_name: str
    status: str
    attempts: int
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    error_message: Optional[str]


class AccountResponse(BaseModel):
    id: int
    website_name: str
    website_url: str
    identity_id: int
    identity_name: str
    is_active: bool
    signup_completed: bool
    created_at: datetime
    stages: List[StageStatusResponse]


class AccountCreate(BaseModel):
    website_name: str
    website_url: str
    identity_id: int
    website_domain: Optional[str] = None
    account_type: Optional[str] = "free"
    signup_method: Optional[str] = "automated"
    stages: Optional[List[str]] = None  # List of stage types to create


class AccountStageUpdate(BaseModel):
    status: str
    error_message: Optional[str] = None
    stage_data: Optional[Dict] = None


def get_default_stages_for_site(website_name: str) -> List[Dict]:
    """Get default stages for a website based on common patterns."""
    common_stages = [
        {"type": StageType.EMAIL_VERIFICATION, "name": "Email Verification", "description": "Verify email address"},
        {"type": StageType.PROFILE_SETUP, "name": "Profile Setup", "description": "Complete profile information"},
        {"type": StageType.TERMS_ACCEPTANCE, "name": "Terms Acceptance", "description": "Accept terms and conditions"},
        {"type": StageType.ACCOUNT_ACTIVATION, "name": "Account Activation", "description": "Activate account"}
    ]
    
    # Add site-specific stages
    site_specific = {
        "facebook": [
            {"type": StageType.PHONE_VERIFICATION, "name": "Phone Verification", "description": "Verify phone number"},
            {"type": StageType.HUMAN_VERIFICATION, "name": "Human Verification", "description": "Prove you're human"}
        ],
        "twitter": [
            {"type": StageType.PHONE_VERIFICATION, "name": "Phone Verification", "description": "Verify phone number"}
        ],
        "instagram": [
            {"type": StageType.PHONE_VERIFICATION, "name": "Phone Verification", "description": "Verify phone number"},
            {"type": StageType.HUMAN_VERIFICATION, "name": "Human Verification", "description": "Prove you're human"}
        ],
        "google": [
            {"type": StageType.PHONE_VERIFICATION, "name": "Phone Verification", "description": "Verify phone number"},
            {"type": StageType.TWO_FACTOR_AUTH, "name": "Two-Factor Auth", "description": "Set up 2FA"}
        ]
    }
    
    result = common_stages.copy()
    site_key = website_name.lower()
    if site_key in site_specific:
        result.extend(site_specific[site_key])
    
    return result


@router.get("/", response_model=List[AccountResponse])
async def list_accounts(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """List all accounts for the current user with stage information."""
    try:
        # Query accounts with stages and identity information
        result = await db.execute(
            select(Account)
            .options(
                selectinload(Account.stages),
                selectinload(Account.identity)
            )
            .join(Identity)
            .where(Identity.user_id == current_user.id)
        )
        accounts = result.scalars().all()
        
        return [
            AccountResponse(
                id=account.id,
                website_name=account.website_name,
                website_url=account.website_url,
                identity_id=account.identity_id,
                identity_name=account.identity.name,
                is_active=account.is_active,
                signup_completed=account.signup_completed,
                created_at=account.created_at,
                stages=[
                    StageStatusResponse(
                        stage_type=stage.stage_type.value,
                        stage_name=stage.stage_name,
                        status=stage.status.value,
                        attempts=stage.attempts,
                        started_at=stage.started_at,
                        completed_at=stage.completed_at,
                        error_message=stage.error_message
                    )
                    for stage in account.stages
                ]
            )
            for account in accounts
        ]
        
    except Exception as e:
        logger.error(f"Error listing accounts: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error retrieving accounts"
        )


@router.post("/", response_model=AccountResponse)
async def create_account(
    account_data: AccountCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Create a new account with stages."""
    try:
        # Verify the identity belongs to the current user
        identity_result = await db.execute(
            select(Identity).where(
                Identity.id == account_data.identity_id,
                Identity.user_id == current_user.id
            )
        )
        identity = identity_result.scalar_one_or_none()
        
        if not identity:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Identity not found or not owned by user"
            )
        
        # Extract domain from URL
        domain = account_data.website_domain
        if not domain and account_data.website_url:
            try:
                from urllib.parse import urlparse
                parsed = urlparse(account_data.website_url)
                domain = parsed.netloc.replace('www.', '')
            except:
                domain = account_data.website_name.lower()
        
        # Create the account
        new_account = Account(
            identity_id=account_data.identity_id,
            website_name=account_data.website_name,
            website_url=account_data.website_url,
            website_domain=domain,
            account_type=account_data.account_type,
            signup_method=account_data.signup_method,
            is_active=True,
            signup_completed=False
        )
        
        db.add(new_account)
        await db.flush()  # Get the account ID
        
        # Create default stages
        stages_to_create = get_default_stages_for_site(account_data.website_name)
        
        for stage_info in stages_to_create:
            stage = AccountStage(
                account_id=new_account.id,
                stage_type=stage_info["type"],
                stage_name=stage_info["name"],
                stage_description=stage_info["description"],
                status=StageStatus.PENDING
            )
            db.add(stage)
        
        await db.commit()
        await db.refresh(new_account)
        
        # Reload with stages and identity
        result = await db.execute(
            select(Account)
            .options(
                selectinload(Account.stages),
                selectinload(Account.identity)
            )
            .where(Account.id == new_account.id)
        )
        account_with_stages = result.scalar_one()
        
        logger.info(f"Created account {new_account.id} for user {current_user.id}")
        
        return AccountResponse(
            id=account_with_stages.id,
            website_name=account_with_stages.website_name,
            website_url=account_with_stages.website_url,
            identity_id=account_with_stages.identity_id,
            identity_name=account_with_stages.identity.name,
            is_active=account_with_stages.is_active,
            signup_completed=account_with_stages.signup_completed,
            created_at=account_with_stages.created_at,
            stages=[
                StageStatusResponse(
                    stage_type=stage.stage_type.value,
                    stage_name=stage.stage_name,
                    status=stage.status.value,
                    attempts=stage.attempts,
                    started_at=stage.started_at,
                    completed_at=stage.completed_at,
                    error_message=stage.error_message
                )
                for stage in account_with_stages.stages
            ]
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating account: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error creating account"
        )


@router.patch("/{account_id}/stages/{stage_id}")
async def update_account_stage(
    account_id: int,
    stage_id: int,
    stage_update: AccountStageUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Update a specific account stage."""
    try:
        # Verify the account belongs to the current user
        result = await db.execute(
            select(AccountStage)
            .join(Account)
            .join(Identity)
            .where(
                AccountStage.id == stage_id,
                AccountStage.account_id == account_id,
                Identity.user_id == current_user.id
            )
        )
        stage = result.scalar_one_or_none()
        
        if not stage:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Stage not found or not owned by user"
            )
        
        # Update stage
        stage.status = StageStatus(stage_update.status)
        stage.error_message = stage_update.error_message
        
        if stage_update.stage_data:
            stage.encrypted_stage_data = encrypt_field(stage_update.stage_data)
        
        if stage_update.status == "completed":
            stage.completed_at = datetime.utcnow()
        elif stage_update.status == "in_progress" and not stage.started_at:
            stage.started_at = datetime.utcnow()
        
        stage.attempts += 1
        
        await db.commit()
        
        logger.info(f"Updated stage {stage_id} for account {account_id}")
        
        return {"message": "Stage updated successfully"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating account stage: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error updating account stage"
        ) 
    common_stages = [
        {"type": StageType.EMAIL_VERIFICATION, "name": "Email Verification", "description": "Verify email address"},
        {"type": StageType.PROFILE_SETUP, "name": "Profile Setup", "description": "Complete profile information"},
        {"type": StageType.TERMS_ACCEPTANCE, "name": "Terms Acceptance", "description": "Accept terms and conditions"},
        {"type": StageType.ACCOUNT_ACTIVATION, "name": "Account Activation", "description": "Activate account"}
    ]
    
    # Add site-specific stages
    site_specific = {
        "facebook": [
            {"type": StageType.PHONE_VERIFICATION, "name": "Phone Verification", "description": "Verify phone number"},
            {"type": StageType.HUMAN_VERIFICATION, "name": "Human Verification", "description": "Prove you're human"}
        ],
        "twitter": [
            {"type": StageType.PHONE_VERIFICATION, "name": "Phone Verification", "description": "Verify phone number"}
        ],
        "instagram": [
            {"type": StageType.PHONE_VERIFICATION, "name": "Phone Verification", "description": "Verify phone number"},
            {"type": StageType.HUMAN_VERIFICATION, "name": "Human Verification", "description": "Prove you're human"}
        ],
        "google": [
            {"type": StageType.PHONE_VERIFICATION, "name": "Phone Verification", "description": "Verify phone number"},
            {"type": StageType.TWO_FACTOR_AUTH, "name": "Two-Factor Auth", "description": "Set up 2FA"}
        ]
    }
    
    result = common_stages.copy()
    site_key = website_name.lower()
    if site_key in site_specific:
        result.extend(site_specific[site_key])
    
    return result


@router.get("/", response_model=List[AccountResponse])
async def list_accounts(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """List all accounts for the current user with stage information."""
    try:
        # Query accounts with stages and identity information
        result = await db.execute(
            select(Account)
            .options(
                selectinload(Account.stages),
                selectinload(Account.identity)
            )
            .join(Identity)
            .where(Identity.user_id == current_user.id)
        )
        accounts = result.scalars().all()
        
        return [
            AccountResponse(
                id=account.id,
                website_name=account.website_name,
                website_url=account.website_url,
                identity_id=account.identity_id,
                identity_name=account.identity.name,
                is_active=account.is_active,
                signup_completed=account.signup_completed,
                created_at=account.created_at,
                stages=[
                    StageStatusResponse(
                        stage_type=stage.stage_type.value,
                        stage_name=stage.stage_name,
                        status=stage.status.value,
                        attempts=stage.attempts,
                        started_at=stage.started_at,
                        completed_at=stage.completed_at,
                        error_message=stage.error_message
                    )
                    for stage in account.stages
                ]
            )
            for account in accounts
        ]
        
    except Exception as e:
        logger.error(f"Error listing accounts: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error retrieving accounts"
        )


@router.post("/", response_model=AccountResponse)
async def create_account(
    account_data: AccountCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Create a new account with stages."""
    try:
        # Verify the identity belongs to the current user
        identity_result = await db.execute(
            select(Identity).where(
                Identity.id == account_data.identity_id,
                Identity.user_id == current_user.id
            )
        )
        identity = identity_result.scalar_one_or_none()
        
        if not identity:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Identity not found or not owned by user"
            )
        
        # Extract domain from URL
        domain = account_data.website_domain
        if not domain and account_data.website_url:
            try:
                from urllib.parse import urlparse
                parsed = urlparse(account_data.website_url)
                domain = parsed.netloc.replace('www.', '')
            except:
                domain = account_data.website_name.lower()
        
        # Create the account
        new_account = Account(
            identity_id=account_data.identity_id,
            website_name=account_data.website_name,
            website_url=account_data.website_url,
            website_domain=domain,
            account_type=account_data.account_type,
            signup_method=account_data.signup_method,
            is_active=True,
            signup_completed=False
        )
        
        db.add(new_account)
        await db.flush()  # Get the account ID
        
        # Create default stages
        stages_to_create = get_default_stages_for_site(account_data.website_name)
        
        for stage_info in stages_to_create:
            stage = AccountStage(
                account_id=new_account.id,
                stage_type=stage_info["type"],
                stage_name=stage_info["name"],
                stage_description=stage_info["description"],
                status=StageStatus.PENDING
            )
            db.add(stage)
        
        await db.commit()
        await db.refresh(new_account)
        
        # Reload with stages and identity
        result = await db.execute(
            select(Account)
            .options(
                selectinload(Account.stages),
                selectinload(Account.identity)
            )
            .where(Account.id == new_account.id)
        )
        account_with_stages = result.scalar_one()
        
        logger.info(f"Created account {new_account.id} for user {current_user.id}")
        
        return AccountResponse(
            id=account_with_stages.id,
            website_name=account_with_stages.website_name,
            website_url=account_with_stages.website_url,
            identity_id=account_with_stages.identity_id,
            identity_name=account_with_stages.identity.name,
            is_active=account_with_stages.is_active,
            signup_completed=account_with_stages.signup_completed,
            created_at=account_with_stages.created_at,
            stages=[
                StageStatusResponse(
                    stage_type=stage.stage_type.value,
                    stage_name=stage.stage_name,
                    status=stage.status.value,
                    attempts=stage.attempts,
                    started_at=stage.started_at,
                    completed_at=stage.completed_at,
                    error_message=stage.error_message
                )
                for stage in account_with_stages.stages
            ]
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating account: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error creating account"
        )


@router.patch("/{account_id}/stages/{stage_id}")
async def update_account_stage(
    account_id: int,
    stage_id: int,
    stage_update: AccountStageUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Update a specific account stage."""
    try:
        # Verify the account belongs to the current user
        result = await db.execute(
            select(AccountStage)
            .join(Account)
            .join(Identity)
            .where(
                AccountStage.id == stage_id,
                AccountStage.account_id == account_id,
                Identity.user_id == current_user.id
            )
        )
        stage = result.scalar_one_or_none()
        
        if not stage:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Stage not found or not owned by user"
            )
        
        # Update stage
        stage.status = StageStatus(stage_update.status)
        stage.error_message = stage_update.error_message
        
        if stage_update.stage_data:
            stage.encrypted_stage_data = encrypt_field(stage_update.stage_data)
        
        if stage_update.status == "completed":
            stage.completed_at = datetime.utcnow()
        elif stage_update.status == "in_progress" and not stage.started_at:
            stage.started_at = datetime.utcnow()
        
        stage.attempts += 1
        
        await db.commit()
        
        logger.info(f"Updated stage {stage_id} for account {account_id}")
        
        return {"message": "Stage updated successfully"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating account stage: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error updating account stage"
        ) 