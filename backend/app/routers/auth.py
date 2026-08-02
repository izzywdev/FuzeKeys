"""Session + vault-unlock routes.

FuzeKeys does NOT authenticate users. Authentication — password login, social
login, signup, MFA, password reset, session revocation — is owned end-to-end by
the FuzeFront Security API, which the frontend calls directly on the
same-origin API base. This router therefore no longer exposes `/login` or
`/register`; there is nothing left here to log in *to*.

What remains is the seam, plus the one thing that is genuinely FuzeKeys':

  GET  /api/v1/auth/me            the caller's identity, resolved via FuzeFront
  POST /api/v1/auth/logout        delegates to `DELETE /v1/security/session`
  GET  /api/v1/auth/vault         vault (master-key) status for this user
  POST /api/v1/auth/vault/setup   set the vault master key the first time
  POST /api/v1/auth/vault/unlock  unlock the vault for this process

The master key is a DOMAIN secret, not a login factor. Before this migration it
was smuggled into the login request, which conflated "prove who you are" with
"decrypt my vault" and made it impossible to delegate authentication without
also losing the vault. Splitting them PRESERVES the capability — you still
cannot read a secret without the master key — while letting FuzeFront own
identity.

`get_current_user` is re-exported from `app.security`, so every router doing
`from app.routers.auth import get_current_user` keeps working unchanged.
"""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.user import User
from app.security import (  # noqa: F401  (re-exported for existing routers)
    Identity,
    check_permission,
    get_current_user,
    get_security_client,
    require_identity,
    require_permission,
)
from app.utils.encryption import (
    generate_master_key_hash,
    get_global_encryption_manager,
    set_global_encryption_manager,
    verify_master_key,
)
from app.utils.logging import get_logger, log_security_event

logger = get_logger(__name__)
router = APIRouter()

__all__ = [
    "router",
    "get_current_user",
    "require_identity",
    "require_permission",
    "check_permission",
    "Identity",
]


# ── Request / response models ────────────────────────────────────────────────
class UserResponse(BaseModel):
    id: int
    username: str
    email: str
    first_name: Optional[str]
    last_name: Optional[str]
    is_active: bool
    is_verified: bool
    created_at: Optional[datetime]
    # Whether this user has completed vault setup. Lets the UI prompt for
    # "set up your vault" instead of failing on the first encrypted read.
    vault_initialized: bool


class VaultStatus(BaseModel):
    vault_initialized: bool
    vault_unlocked: bool


class MasterKeyRequest(BaseModel):
    master_key: str = Field(..., min_length=8)


def _to_user_response(user: User) -> UserResponse:
    return UserResponse(
        id=user.id,
        username=user.username,
        email=user.email,
        first_name=user.first_name,
        last_name=user.last_name,
        is_active=user.is_active,
        is_verified=user.is_verified,
        created_at=user.created_at,
        vault_initialized=bool(user.master_key_hash),
    )


def _bearer(request: Request) -> Optional[str]:
    header = request.headers.get("authorization") or ""
    if header.lower().startswith("bearer "):
        return header[7:].strip() or None
    return None


# ── Session ──────────────────────────────────────────────────────────────────
@router.get("/me", response_model=UserResponse)
async def get_current_user_info(current_user: User = Depends(get_current_user)):
    """The caller, as FuzeKeys sees them.

    The identity itself comes from `GET /v1/security/session`; this adds the
    FuzeKeys-local projection (the integer id every vault relation points at,
    plus vault status).
    """
    return _to_user_response(current_user)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(request: Request):
    """Revoke the session via FuzeFront (`DELETE /v1/security/session`).

    Previously a no-op that merely told the client to forget its token, leaving
    a stolen token valid until expiry. Delegating to FuzeFront makes logout
    actually revoke.
    """
    token = _bearer(request)
    if token:
        await get_security_client().delete_session(token)
    return None


# ── Vault (FuzeKeys domain) ──────────────────────────────────────────────────
@router.get("/vault", response_model=VaultStatus)
async def vault_status(current_user: User = Depends(get_current_user)):
    """Whether this user has a vault master key, and whether it is unlocked."""
    return VaultStatus(
        vault_initialized=bool(current_user.master_key_hash),
        vault_unlocked=get_global_encryption_manager() is not None,
    )


@router.post("/vault/setup", response_model=VaultStatus)
async def vault_setup(
    body: MasterKeyRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Set the vault master key for the first time.

    409 if one already exists — re-keying an existing vault would orphan every
    ciphertext already stored under the old key, so it is deliberately not a
    silent overwrite.
    """
    if current_user.master_key_hash:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A vault master key already exists for this account",
        )

    current_user.master_key_hash = generate_master_key_hash(body.master_key)
    await db.commit()

    set_global_encryption_manager(body.master_key)
    log_security_event("vault_master_key_set", user_id=current_user.id)

    return VaultStatus(vault_initialized=True, vault_unlocked=True)


@router.post("/vault/unlock", response_model=VaultStatus)
async def vault_unlock(
    body: MasterKeyRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Unlock the vault with the master key.

    This is the capability that used to ride along on `POST /auth/login`. Its
    effect is unchanged — a wrong master key still yields no plaintext — but it
    is now an explicitly authenticated action rather than part of sign-in.
    """
    if not current_user.master_key_hash:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="No vault master key has been set for this account",
        )

    if not verify_master_key(body.master_key, current_user.master_key_hash):
        log_security_event(
            "failed_vault_unlock",
            user_id=current_user.id,
            details={"reason": "invalid_master_key"},
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect master key",
        )

    set_global_encryption_manager(body.master_key)
    current_user.last_login = datetime.utcnow()
    await db.commit()

    log_security_event("vault_unlocked", user_id=current_user.id)
    return VaultStatus(vault_initialized=True, vault_unlocked=True)
