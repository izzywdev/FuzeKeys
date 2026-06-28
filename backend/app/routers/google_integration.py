"""
Google integration API routes.

SECURITY (CRITICAL-1 / appsec #18): every route here is now gated by
`get_current_user` (JWT) AND scopes the identity/account it touches to the
calling user via the ownership chain Account.identity_id -> Identity.id ->
Identity.user_id == current_user.id. This mirrors the gold-standard pattern in
`accounts.py` / `identities.py`. A caller can only sign up / read accounts /
convert PII for an identity they own; any other identity returns 404 (we return
404 — not 403 — so we do not leak whether an identity id exists under a
different owner). The previous routes decrypted PII and drove real account
creation by raw path id with no auth, which was an unauthenticated PII
exfiltration + account-creation vector.

Note: these handlers use the async SQLAlchemy session (the app's `get_db` yields
an AsyncSession) and `select(...)`/`await db.execute(...)`, consistent with the
rest of the codebase.
"""

import logging
from typing import Dict, Any
from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.database import get_db
from app.models.identity import Identity
from app.models.account import Account
from app.models.user import User
from app.routers.auth import get_current_user
from app.integrations.google.backend.signup import GoogleSignupService
from app.integrations.google.backend.models import GoogleSignupConfig, GoogleSignupData, GoogleSignupResult
from app.utils.encryption import encrypt_field

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/google", tags=["Google Integration"])


async def _get_owned_identity(identity_id: int, current_user: User, db: AsyncSession) -> Identity:
    """Fetch an identity ONLY if it belongs to the current user.

    SECURITY (CRITICAL-1): scopes the lookup to the caller. Returns 404 (not 403)
    on no-match so we never leak the existence of another user's identity.
    """
    result = await db.execute(
        select(Identity).where(
            (Identity.id == identity_id) & (Identity.user_id == current_user.id)
        )
    )
    identity = result.scalar_one_or_none()
    if not identity:
        raise HTTPException(status_code=404, detail="Identity not found")
    return identity


@router.post("/signup/{identity_id}")
async def signup_with_identity(
    identity_id: int,
    config: GoogleSignupConfig = None,
    background_tasks: BackgroundTasks = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> Dict[str, Any]:
    """
    Create a Google account using the specified identity.

    SECURITY: requires auth and that the identity is owned by the caller.
    """
    try:
        # Ownership-scoped lookup (404 if not owned / not found).
        identity = await _get_owned_identity(identity_id, current_user, db)

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
            await db.commit()
            await db.refresh(account)

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

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in Google signup: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/signup/manual")
async def manual_signup(
    signup_data: GoogleSignupData,
    config: GoogleSignupConfig = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> Dict[str, Any]:
    """
    Create a Google account with manually provided data.

    SECURITY: requires auth. This route drives real signup automation from the
    request body and must not be reachable unauthenticated.
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

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in manual Google signup: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/config/default")
async def get_default_config(
    current_user: User = Depends(get_current_user),
) -> GoogleSignupConfig:
    """
    Get the default configuration for Google signup.

    SECURITY: requires auth. Even though it returns no PII, keep the whole
    router authenticated so there is no unauthenticated surface here.
    """
    return GoogleSignupConfig()


@router.post("/test/identity-conversion/{identity_id}")
async def test_identity_conversion(
    identity_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> Dict[str, Any]:
    """
    Test converting an identity to Google signup data without actually creating an account.

    SECURITY (CRITICAL-1): this endpoint returns DECRYPTED PII (names, username,
    phone, recovery email, birth date, gender). It now requires auth and that the
    identity belongs to the caller; otherwise 404. This closes the unauthenticated
    PII-exfiltration path.
    """
    try:
        # Ownership-scoped lookup (404 if not owned / not found).
        identity = await _get_owned_identity(identity_id, current_user, db)

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

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in identity conversion test: {str(e)}")
        raise HTTPException(status_code=400, detail="Conversion error")


@router.get("/accounts/{identity_id}")
async def get_google_accounts(
    identity_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> Dict[str, Any]:
    """
    Get all Google accounts for a specific identity.

    SECURITY (CRITICAL-1): requires auth; the identity must be owned by the
    caller (404 otherwise). The account lookup is additionally scoped through the
    owned identity so no cross-tenant account data is returned.
    """
    try:
        # Ownership-scoped identity lookup first (404 if not owned / not found).
        await _get_owned_identity(identity_id, current_user, db)

        # Get Google accounts for this (now confirmed owned) identity.
        result = await db.execute(
            select(Account).where(
                (Account.identity_id == identity_id)
                & (Account.platform == "google")
            )
        )
        accounts = result.scalars().all()

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

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting Google accounts: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")