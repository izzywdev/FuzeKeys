"""Instance decisions for rows already selected with local ownership predicates."""

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.platform_identity import PlatformIdentity
from app.security.platform_authz import (
    PlatformAuthorizationUnavailable,
    check_permission,
)


async def require_owner_permission(
    db: AsyncSession,
    user_id: int,
    resource_type: str,
    resource_id: int,
    action: str,
) -> None:
    """Require a verified binding and an explicit allow for an existing instance.

    Call only after selecting the row through its SQL owner. Creates require a
    separate parent authorization/grant lifecycle and cannot use this helper.
    Resource names and keys match the repository ownership inventory exactly.
    """
    if (
        resource_type not in ("Identity", "Account")
        or type(resource_id) is not int
        or resource_id <= 0
        or action not in ("update", "delete")
    ):
        raise HTTPException(403, "Invalid resource permission request")
    result = await db.execute(
        select(PlatformIdentity).where(PlatformIdentity.user_id == user_id)
    )
    binding = result.scalar_one_or_none()
    if binding is None or binding.verified_at is None:
        raise HTTPException(403, "Verified platform identity required")
    try:
        allowed = await check_permission(
            binding.subject,
            binding.tenant,
            "fuzekeys_" + resource_type,
            action,
            resource_key=resource_type.lower() + ":" + str(resource_id),
        )
    except PlatformAuthorizationUnavailable as exc:
        raise HTTPException(503, "Resource authorization unavailable") from exc
    if allowed is not True:
        raise HTTPException(403, "Resource permission denied")
