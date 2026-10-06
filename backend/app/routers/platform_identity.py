"""Explicit dual-session linking, without changing existing login or policy."""

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.platform_identity import PlatformIdentity
from app.models.user import User
from app.routers.auth import get_current_user
from app.security.platform_authz import PlatformAuthorizationUnavailable
from app.security.platform_identity import (
    PlatformIdentityRejected,
    verify_platform_identity,
)

router = APIRouter()


class PlatformLinkResponse(BaseModel):
    subject: str
    tenant: str


@router.post(
    "/platform-link", response_model=PlatformLinkResponse, include_in_schema=False
)
async def link_platform_identity(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    platform_session: str = Header(alias="X-FuzeFront-Session", max_length=8192),
):
    """Bind the authenticated local account to a separately verified session.

    Bindings cannot be overwritten through this API. The database constraints
    also prevent races or linking one platform pair to two local accounts.
    """
    if not current_user.is_active:
        raise HTTPException(403, "Inactive local account")
    user_id = current_user.id
    try:
        subject, tenant = await verify_platform_identity(platform_session)
    except PlatformIdentityRejected:
        raise HTTPException(
            403, "Platform session or tenant membership rejected"
        ) from None
    except PlatformAuthorizationUnavailable:
        raise HTTPException(503, "Platform identity verification unavailable") from None

    existing = await db.get(PlatformIdentity, user_id)
    if existing is not None:
        if existing.subject != subject or existing.tenant != tenant:
            raise HTTPException(409, "Platform identity already linked")
        return PlatformLinkResponse(subject=subject, tenant=tenant)
    db.add(PlatformIdentity(user_id=user_id, subject=subject, tenant=tenant))
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        # A concurrent identical link is idempotent; every competing binding
        # remains a conflict. Do not reveal the other local account's identity.
        existing = await db.get(PlatformIdentity, user_id)
        if existing is None or existing.subject != subject or existing.tenant != tenant:
            raise HTTPException(409, "Platform identity already linked") from None
    return PlatformLinkResponse(subject=subject, tenant=tenant)
