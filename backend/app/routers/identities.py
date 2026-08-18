from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from pydantic import BaseModel, ConfigDict, EmailStr
from typing import List, Optional, Dict, Any
from datetime import datetime

from app.database import get_db
from app.models.user import User
from app.models.identity import Identity
from app.routers.auth import get_current_user
from app.utils.encryption import encrypt_field, decrypt_field, decrypt_json_field
from app.utils.logging import get_logger

logger = get_logger(__name__)
router = APIRouter()


class IdentityCreate(BaseModel):
    # extra="forbid" per governance/identifier-standard.md 1 (enforced by
    # gate-identifier): a create body must reject fields it does not declare, so a
    # client cannot smuggle an id or any other attribute the caller does not own
    # (OWASP API3:2023 mass assignment). It lives on the model, not the spec —
    # contracts/openapi.yaml is exported FROM this code and loses hand-edits.
    model_config = ConfigDict(extra="forbid")

    name: str
    description: Optional[str] = None
    first_name: str
    last_name: str
    email: EmailStr
    phone: Optional[str] = None
    date_of_birth: Optional[str] = None
    address_line1: Optional[str] = None
    address_line2: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    zip_code: Optional[str] = None
    country: Optional[str] = None
    profession: Optional[str] = None
    company: Optional[str] = None
    bio: Optional[str] = None
    custom_fields: Optional[Dict[str, Any]] = None
    preferred_username_pattern: Optional[str] = None


class IdentityUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    email: Optional[EmailStr] = None
    phone: Optional[str] = None
    date_of_birth: Optional[str] = None
    address_line1: Optional[str] = None
    address_line2: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    zip_code: Optional[str] = None
    country: Optional[str] = None
    profession: Optional[str] = None
    company: Optional[str] = None
    bio: Optional[str] = None
    custom_fields: Optional[Dict[str, Any]] = None
    preferred_username_pattern: Optional[str] = None


class IdentityResponse(BaseModel):
    id: int
    name: str
    description: Optional[str]
    first_name: str
    last_name: str
    email: str
    phone: Optional[str]
    date_of_birth: Optional[str]
    address_line1: Optional[str]
    address_line2: Optional[str]
    city: Optional[str]
    state: Optional[str]
    zip_code: Optional[str]
    country: Optional[str]
    profession: Optional[str]
    company: Optional[str]
    bio: Optional[str]
    custom_fields: Optional[Dict[str, Any]]
    preferred_username_pattern: Optional[str]
    created_at: datetime
    updated_at: Optional[datetime]


class IdentityListResponse(BaseModel):
    id: int
    name: str
    description: Optional[str]
    created_at: datetime


def decrypt_identity_data(identity: Identity) -> IdentityResponse:
    """Decrypt identity data for response."""
    try:
        return IdentityResponse(
            id=identity.id,
            name=identity.name,
            description=identity.description,
            first_name=decrypt_field(identity.encrypted_first_name) or "",
            last_name=decrypt_field(identity.encrypted_last_name) or "",
            email=decrypt_field(identity.encrypted_email) or "",
            phone=decrypt_field(identity.encrypted_phone),
            date_of_birth=decrypt_field(identity.encrypted_date_of_birth),
            address_line1=decrypt_field(identity.encrypted_address_line1),
            address_line2=decrypt_field(identity.encrypted_address_line2),
            city=decrypt_field(identity.encrypted_city),
            state=decrypt_field(identity.encrypted_state),
            zip_code=decrypt_field(identity.encrypted_zip_code),
            country=decrypt_field(identity.encrypted_country),
            profession=decrypt_field(identity.encrypted_profession),
            company=decrypt_field(identity.encrypted_company),
            bio=decrypt_field(identity.encrypted_bio),
            custom_fields=decrypt_json_field(identity.encrypted_custom_fields),
            preferred_username_pattern=identity.preferred_username_pattern,
            created_at=identity.created_at,
            updated_at=identity.updated_at
        )
    except Exception as e:
        logger.error(f"Error decrypting identity data: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error decrypting identity data"
        )


@router.post("/", response_model=IdentityResponse)
async def create_identity(
    identity_data: IdentityCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Create a new identity."""
    try:
        # Create new identity with encrypted fields
        new_identity = Identity(
            user_id=current_user.id,
            name=identity_data.name,
            description=identity_data.description,
            encrypted_first_name=encrypt_field(identity_data.first_name),
            encrypted_last_name=encrypt_field(identity_data.last_name),
            encrypted_email=encrypt_field(identity_data.email),
            encrypted_phone=encrypt_field(identity_data.phone) if identity_data.phone else None,
            encrypted_date_of_birth=encrypt_field(identity_data.date_of_birth) if identity_data.date_of_birth else None,
            encrypted_address_line1=encrypt_field(identity_data.address_line1) if identity_data.address_line1 else None,
            encrypted_address_line2=encrypt_field(identity_data.address_line2) if identity_data.address_line2 else None,
            encrypted_city=encrypt_field(identity_data.city) if identity_data.city else None,
            encrypted_state=encrypt_field(identity_data.state) if identity_data.state else None,
            encrypted_zip_code=encrypt_field(identity_data.zip_code) if identity_data.zip_code else None,
            encrypted_country=encrypt_field(identity_data.country) if identity_data.country else None,
            encrypted_profession=encrypt_field(identity_data.profession) if identity_data.profession else None,
            encrypted_company=encrypt_field(identity_data.company) if identity_data.company else None,
            encrypted_bio=encrypt_field(identity_data.bio) if identity_data.bio else None,
            encrypted_custom_fields=encrypt_field(identity_data.custom_fields) if identity_data.custom_fields else None,
            preferred_username_pattern=identity_data.preferred_username_pattern
        )
        
        db.add(new_identity)
        await db.commit()
        await db.refresh(new_identity)
        
        logger.info(f"Created identity {new_identity.id} for user {current_user.id}")
        
        return decrypt_identity_data(new_identity)
        
    except Exception as e:
        logger.error(f"Error creating identity: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error creating identity"
        )


@router.get("/", response_model=List[IdentityListResponse])
async def list_identities(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """List all identities for the current user."""
    try:
        result = await db.execute(
            select(Identity).where(Identity.user_id == current_user.id)
        )
        identities = result.scalars().all()
        
        return [
            IdentityListResponse(
                id=identity.id,
                name=identity.name,
                description=identity.description,
                created_at=identity.created_at
            )
            for identity in identities
        ]
        
    except Exception as e:
        logger.error(f"Error listing identities: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error retrieving identities"
        )


@router.get("/{identity_id}", response_model=IdentityResponse)
async def get_identity(
    identity_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get a specific identity."""
    try:
        result = await db.execute(
            select(Identity).where(
                (Identity.id == identity_id) & (Identity.user_id == current_user.id)
            )
        )
        identity = result.scalar_one_or_none()
        
        if not identity:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Identity not found"
            )
        
        return decrypt_identity_data(identity)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting identity {identity_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error retrieving identity"
        )


@router.put("/{identity_id}", response_model=IdentityResponse)
async def update_identity(
    identity_id: int,
    identity_data: IdentityUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Update an identity."""
    try:
        result = await db.execute(
            select(Identity).where(
                (Identity.id == identity_id) & (Identity.user_id == current_user.id)
            )
        )
        identity = result.scalar_one_or_none()
        
        if not identity:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Identity not found"
            )
        
        # Update fields
        if identity_data.name is not None:
            identity.name = identity_data.name
        if identity_data.description is not None:
            identity.description = identity_data.description
        if identity_data.first_name is not None:
            identity.encrypted_first_name = encrypt_field(identity_data.first_name)
        if identity_data.last_name is not None:
            identity.encrypted_last_name = encrypt_field(identity_data.last_name)
        if identity_data.email is not None:
            identity.encrypted_email = encrypt_field(identity_data.email)
        if identity_data.phone is not None:
            identity.encrypted_phone = encrypt_field(identity_data.phone)
        if identity_data.date_of_birth is not None:
            identity.encrypted_date_of_birth = encrypt_field(identity_data.date_of_birth)
        if identity_data.address_line1 is not None:
            identity.encrypted_address_line1 = encrypt_field(identity_data.address_line1)
        if identity_data.address_line2 is not None:
            identity.encrypted_address_line2 = encrypt_field(identity_data.address_line2)
        if identity_data.city is not None:
            identity.encrypted_city = encrypt_field(identity_data.city)
        if identity_data.state is not None:
            identity.encrypted_state = encrypt_field(identity_data.state)
        if identity_data.zip_code is not None:
            identity.encrypted_zip_code = encrypt_field(identity_data.zip_code)
        if identity_data.country is not None:
            identity.encrypted_country = encrypt_field(identity_data.country)
        if identity_data.profession is not None:
            identity.encrypted_profession = encrypt_field(identity_data.profession)
        if identity_data.company is not None:
            identity.encrypted_company = encrypt_field(identity_data.company)
        if identity_data.bio is not None:
            identity.encrypted_bio = encrypt_field(identity_data.bio)
        if identity_data.custom_fields is not None:
            identity.encrypted_custom_fields = encrypt_field(identity_data.custom_fields)
        if identity_data.preferred_username_pattern is not None:
            identity.preferred_username_pattern = identity_data.preferred_username_pattern
        
        await db.commit()
        await db.refresh(identity)
        
        logger.info(f"Updated identity {identity_id} for user {current_user.id}")
        
        return decrypt_identity_data(identity)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating identity {identity_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error updating identity"
        )


@router.delete("/{identity_id}")
async def delete_identity(
    identity_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Delete an identity."""
    try:
        result = await db.execute(
            select(Identity).where(
                (Identity.id == identity_id) & (Identity.user_id == current_user.id)
            )
        )
        identity = result.scalar_one_or_none()
        
        if not identity:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Identity not found"
            )
        
        await db.delete(identity)
        await db.commit()
        
        logger.info(f"Deleted identity {identity_id} for user {current_user.id}")
        
        return {"message": "Identity deleted successfully"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting identity {identity_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error deleting identity"
        ) 