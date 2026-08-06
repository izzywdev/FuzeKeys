"""FastAPI dependencies backed by the FuzeFront Security API.

`get_current_user` keeps its historical name and return type (the local `User`
row) on purpose: ~15 routers and every ownership check depend on
`current_user.id` being the local integer primary key that all foreign keys
point at. Swapping the *implementation* under a stable seam migrates the whole
backend without touching a single feature router — and without a data
migration of every FK.

What changed underneath:
  before — decode a locally-minted HS256 JWT with a local SECRET_KEY
  after  — ask FuzeFront `GET /v1/security/session` who the caller is, then
           resolve (or provision) the local row that mirrors that subject
"""

from __future__ import annotations

import re
from typing import Callable, List, Optional

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.database import get_db
from app.models.user import User
from app.utils.logging import get_logger

from .client import (
    FuzeFrontSecurityClient,
    SecurityError,
    get_authz_tenant_fallback,
    get_security_client,
)
from .contract import AuthzCheck, Identity

logger = get_logger(__name__)

# auto_error=False so a missing header produces our own provider-neutral 401
# with a WWW-Authenticate challenge, identical to the pre-migration behaviour.
_bearer = HTTPBearer(auto_error=False)

_CREDENTIALS_EXCEPTION = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Could not validate credentials",
    headers={"WWW-Authenticate": "Bearer"},
)


def _bearer_token(credentials: Optional[HTTPAuthorizationCredentials]) -> str:
    if credentials is None or not credentials.credentials:
        raise _CREDENTIALS_EXCEPTION
    return credentials.credentials


async def require_identity(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
) -> Identity:
    """Resolve the caller's normalized `Identity` via FuzeFront. Fail-closed."""
    token = _bearer_token(credentials)
    client = get_security_client()
    try:
        return await client.get_session(token)
    except SecurityError as exc:
        if exc.status_code == 503:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Authentication service unavailable",
            ) from exc
        raise _CREDENTIALS_EXCEPTION from exc


async def optional_identity(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
) -> Optional[Identity]:
    """Like `require_identity` but returns None instead of raising on no/bad token."""
    if credentials is None or not credentials.credentials:
        return None
    try:
        return await get_security_client().get_session(credentials.credentials)
    except SecurityError:
        return None


_USERNAME_SAFE = re.compile(r"[^a-zA-Z0-9._-]+")


def _derive_username(identity: Identity) -> str:
    """Best-effort local display handle for a FuzeFront subject.

    Purely cosmetic — `fuzefront_user_id` is the identity key. The local
    `username` column predates the migration, is UNIQUE NOT NULL, and is shown
    in the UI, so it still needs a value.
    """
    candidate = ""
    if identity.email:
        candidate = identity.email.split("@", 1)[0]
    if not candidate:
        candidate = identity.user.get("firstName") or ""
    candidate = _USERNAME_SAFE.sub("", candidate)[:80]
    return candidate or f"user-{identity.user_id[:16]}"


async def resolve_local_user(identity: Identity, db: AsyncSession) -> User:
    """Map a FuzeFront subject onto the local `users` row.

    The local row is a PROJECTION, not a credential store: it exists so that
    `identities.user_id`, `accounts.user_id` etc. keep working. It holds no
    password (FuzeFront owns authentication) — only the FuzeFront subject id,
    the profile fields FuzeKeys renders, and the vault master-key hash, which
    is FuzeKeys' own domain secret and has nothing to do with sign-in.
    """
    result = await db.execute(
        select(User).where(User.fuzefront_user_id == identity.user_id)
    )
    user = result.scalar_one_or_none()

    if user is None and identity.email:
        # Adopt a pre-migration row that was created by the old local signup,
        # so existing vaults and their master-key hash survive the cutover.
        result = await db.execute(select(User).where(User.email == identity.email))
        legacy = result.scalar_one_or_none()
        if legacy is not None and legacy.fuzefront_user_id is None:
            legacy.fuzefront_user_id = identity.user_id
            user = legacy
            logger.info(
                "Linked pre-existing FuzeKeys user %s to FuzeFront subject", legacy.id
            )

    if user is None:
        base_username = _derive_username(identity)
        username = base_username
        suffix = 0
        while True:
            clash = await db.execute(select(User).where(User.username == username))
            if clash.scalar_one_or_none() is None:
                break
            suffix += 1
            username = f"{base_username}-{suffix}"

        user = User(
            fuzefront_user_id=identity.user_id,
            email=identity.email or f"{identity.user_id}@users.noreply.fuzefront",
            username=username,
            first_name=identity.user.get("firstName"),
            last_name=identity.user.get("lastName"),
            is_active=True,
            # Verified upstream — FuzeFront would not have issued a session for
            # an account it considers unusable.
            is_verified=True,
        )
        db.add(user)
        logger.info("Provisioned local FuzeKeys user for a FuzeFront subject")

    # Keep the projection fresh (email/name can change upstream).
    if identity.email and user.email != identity.email:
        user.email = identity.email
    first_name = identity.user.get("firstName")
    last_name = identity.user.get("lastName")
    if first_name and user.first_name != first_name:
        user.first_name = first_name
    if last_name and user.last_name != last_name:
        user.last_name = last_name

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Account is deactivated",
        )

    await db.commit()
    await db.refresh(user)
    return user


async def get_current_user(
    identity: Identity = Depends(require_identity),
    db: AsyncSession = Depends(get_db),
) -> User:
    """The seam every feature router already depends on.

    Same name, same return type, same object-level guarantees as before — but
    the identity now comes from FuzeFront instead of a locally-signed token.
    """
    return await resolve_local_user(identity, db)


# ── Authorization ─────────────────────────────────────────────────────────────
def _tenant_for(identity: Identity) -> str:
    tenant = identity.tenant_id or get_authz_tenant_fallback()
    if not tenant:
        # Contract: "Consumers fail-closed on tenant-scoped decisions when this
        # is null." Denying is the whole point — do not substitute a guess.
        logger.warning(
            "Authorization denied: identity carries no tenant and no explicit "
            "FUZEFRONT_DEFAULT_TENANT is configured"
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not permitted",
        )
    return tenant


def _caller_token(request: Optional[Request]) -> Optional[str]:
    if request is None:
        return None
    header = request.headers.get("authorization") or ""
    if header.lower().startswith("bearer "):
        return header[7:].strip() or None
    return None


async def check_permission(
    identity: Identity,
    resource_type: str,
    action: str,
    resource_key: Optional[str] = None,
    caller_token: Optional[str] = None,
    client: Optional[FuzeFrontSecurityClient] = None,
) -> bool:
    """Imperative single authorization check. Fail-closed.

    `resource_type` / `action` are the bare keys from
    `registration/policy.json` — e.g. ("VaultAsset", "reveal").
    """
    tenant = identity.tenant_id or get_authz_tenant_fallback()
    if not tenant:
        return False
    return await (client or get_security_client()).authz_check(
        subject=identity.user_id,
        tenant=tenant,
        check=AuthzCheck(
            resource_type=resource_type, action=action, resource_key=resource_key
        ),
        caller_token=caller_token,
    )


async def bulk_check_permissions(
    identity: Identity,
    checks: List[AuthzCheck],
    caller_token: Optional[str] = None,
    client: Optional[FuzeFrontSecurityClient] = None,
) -> List[bool]:
    """Imperative bulk authorization check, index-aligned. Fail-closed."""
    tenant = identity.tenant_id or get_authz_tenant_fallback()
    if not tenant:
        return [False] * len(checks)
    return await (client or get_security_client()).authz_bulk_check(
        subject=identity.user_id,
        tenant=tenant,
        checks=checks,
        caller_token=caller_token,
    )


def require_permission(
    resource_type: str,
    action: str,
) -> Callable:
    """FastAPI dependency factory enforcing one `resource:action`.

    Usage:
        @router.post("/reveal", dependencies=[Depends(require_permission("VaultAsset", "reveal"))])

    Denial is a 403 raised BEFORE the handler runs, and any failure to obtain a
    decision is also a denial.
    """

    async def _dependency(
        request: Request,
        identity: Identity = Depends(require_identity),
    ) -> Identity:
        tenant = _tenant_for(identity)
        allowed = await get_security_client().authz_check(
            subject=identity.user_id,
            tenant=tenant,
            check=AuthzCheck(resource_type=resource_type, action=action),
            caller_token=_caller_token(request),
        )
        if not allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not permitted",
            )
        return identity

    _dependency.__name__ = f"require_{resource_type}_{action}"
    return _dependency
