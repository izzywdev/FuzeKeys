from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from datetime import datetime, timedelta
from typing import Optional
import os
from jose import JWTError, jwt
from pydantic import BaseModel, EmailStr

from app.database import get_db
from app.models.user import User
from app.utils.encryption import (
    hash_password, verify_password, generate_master_key_hash, 
    verify_master_key, set_global_encryption_manager
)
from app.utils.logging import get_logger, log_security_event

logger = get_logger(__name__)
router = APIRouter()
security = HTTPBearer()

# JWT Configuration
# SECURITY (MEDIUM-2 / appsec #18): the JWT signing key must come from the
# environment with NO insecure default. The previous default ("your-secret-key")
# made tokens forgeable by anyone who knew the public source, which undermines
# EVERY `get_current_user` object-level check downstream. We fail CLOSED:
#   - A blank/unset SECRET_KEY leaves the module importable (other routers import
#     this module at startup) but `_require_secret_key()` raises HTTP 503 at
#     request time on any token issue/verify, so no token is ever signed or
#     accepted with an absent/weak key.
#   - In a non-test environment we additionally reject the known-insecure legacy
#     placeholder value so it can never be reintroduced via env.
SECRET_KEY = os.getenv("SECRET_KEY")
ALGORITHM = os.getenv("ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "30"))

# Known-insecure placeholder values that must never be used to sign/verify tokens.
_INSECURE_SECRET_VALUES = {"your-secret-key", "your-super-secret-key-here-change-this-in-production"}

if not SECRET_KEY or not SECRET_KEY.strip():
    logger.warning(
        "SECRET_KEY is not set. JWT issuance/verification will fail closed with "
        "HTTP 503 until a strong SECRET_KEY is configured. No insecure default is used."
    )
elif SECRET_KEY.strip() in _INSECURE_SECRET_VALUES:
    logger.error(
        "SECRET_KEY is set to a known-insecure placeholder value. JWT issuance/"
        "verification will fail closed with HTTP 503 until a strong SECRET_KEY is "
        "configured."
    )


def _require_secret_key() -> str:
    """Return a usable JWT signing key or fail closed.

    SECURITY: raises HTTPException(503) when SECRET_KEY is missing/blank or is the
    known-insecure placeholder, so tokens can never be signed or validated with a
    forgeable key. Every create/verify path routes through here.
    """
    key = SECRET_KEY
    if not key or not key.strip() or key.strip() in _INSECURE_SECRET_VALUES:
        logger.error("Refusing JWT operation: SECRET_KEY is unset, blank, or insecure.")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication is not configured",
        )
    return key.strip()


# Pydantic models
class UserCreate(BaseModel):
    username: str
    email: EmailStr
    password: str
    master_key: str
    first_name: Optional[str] = None
    last_name: Optional[str] = None


class UserLogin(BaseModel):
    email: EmailStr
    password: str
    master_key: str


class Token(BaseModel):
    access_token: str
    token_type: str


class UserResponse(BaseModel):
    id: int
    username: str
    email: str
    first_name: Optional[str]
    last_name: Optional[str]
    is_active: bool
    is_verified: bool
    created_at: datetime


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    """Create JWT access token."""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, _require_secret_key(), algorithm=ALGORITHM)
    return encoded_jwt


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db)
) -> User:
    """Get current authenticated user."""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    try:
        payload = jwt.decode(credentials.credentials, _require_secret_key(), algorithms=[ALGORITHM])
        user_id: int = payload.get("sub")
        if user_id is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception
    
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise credentials_exception
    
    return user


@router.post("/register", response_model=UserResponse)
async def register(user_data: UserCreate, db: AsyncSession = Depends(get_db)):
    """Register a new user."""
    try:
        # Check if user already exists
        result = await db.execute(
            select(User).where(
                (User.email == user_data.email) | (User.username == user_data.username)
            )
        )
        existing_user = result.scalar_one_or_none()
        
        if existing_user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="User with this email or username already exists"
            )
        
        # Create new user
        hashed_password = hash_password(user_data.password)
        master_key_hash = generate_master_key_hash(user_data.master_key)
        
        new_user = User(
            username=user_data.username,
            email=user_data.email,
            hashed_password=hashed_password,
            master_key_hash=master_key_hash,
            first_name=user_data.first_name,
            last_name=user_data.last_name,
        )
        
        db.add(new_user)
        await db.commit()
        await db.refresh(new_user)
        
        log_security_event("user_registered", user_id=new_user.id, 
                          details={"email": user_data.email, "username": user_data.username})
        
        return UserResponse(
            id=new_user.id,
            username=new_user.username,
            email=new_user.email,
            first_name=new_user.first_name,
            last_name=new_user.last_name,
            is_active=new_user.is_active,
            is_verified=new_user.is_verified,
            created_at=new_user.created_at
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error registering user: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error"
        )


@router.post("/login", response_model=Token)
async def login(user_data: UserLogin, db: AsyncSession = Depends(get_db)):
    """Authenticate user and return access token."""
    try:
        # Find user by email
        result = await db.execute(select(User).where(User.email == user_data.email))
        user = result.scalar_one_or_none()
        
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Incorrect email or password"
            )
        
        # Verify password
        if not verify_password(user_data.password, user.hashed_password):
            log_security_event("failed_login_attempt", user_id=user.id, 
                              details={"reason": "invalid_password"})
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Incorrect email or password"
            )
        
        # Verify master key
        if not verify_master_key(user_data.master_key, user.master_key_hash):
            log_security_event("failed_login_attempt", user_id=user.id, 
                              details={"reason": "invalid_master_key"})
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Incorrect master key"
            )
        
        # Check if user is active
        if not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Account is deactivated"
            )
        
        # Set up encryption manager for this session
        set_global_encryption_manager(user_data.master_key)
        
        # Update last login
        user.last_login = datetime.utcnow()
        await db.commit()
        
        # Create access token
        access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
        access_token = create_access_token(
            data={"sub": str(user.id)}, expires_delta=access_token_expires
        )
        
        log_security_event("successful_login", user_id=user.id)
        
        return {"access_token": access_token, "token_type": "bearer"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error during login: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error"
        )


@router.get("/me", response_model=UserResponse)
async def get_current_user_info(current_user: User = Depends(get_current_user)):
    """Get current user information."""
    return UserResponse(
        id=current_user.id,
        username=current_user.username,
        email=current_user.email,
        first_name=current_user.first_name,
        last_name=current_user.last_name,
        is_active=current_user.is_active,
        is_verified=current_user.is_verified,
        created_at=current_user.created_at
    )


@router.post("/logout")
async def logout():
    """Logout user (client should discard token)."""
    # In a more sophisticated setup, you might want to blacklist the token
    return {"message": "Successfully logged out"} 