"""Instance decisions for rows already selected with local ownership predicates."""

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.platform_identity import PlatformIdentity
from app.security.platform_authz import (
    PlatformAuthorizationUnavailable,
    check_permission,
)


async def require_permission(*args, **kwargs) -> None:
    """Require an explicit boolean allow from the platform decision service."""
    allowed = await check_permission(*args, **kwargs)
    if allowed is not True:
        raise HTTPException(403, "Resource permission denied")


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
        or action not in ("read", "update", "delete", "use")
        or (action == "use" and resource_type != "Identity")
    ):
        raise HTTPException(403, "Invalid resource permission request")
    result = await db.execute(
        select(PlatformIdentity).where(PlatformIdentity.user_id == user_id)
    )
    binding = result.scalar_one_or_none()
    if binding is None or binding.verified_at is None:
        raise HTTPException(403, "Verified platform identity required")
    try:
        await require_permission(
            binding.subject,
            binding.tenant,
            "fuzekeys_" + resource_type,
            action,
            resource_key=resource_type.lower() + ":" + str(resource_id),
        )
    except PlatformAuthorizationUnavailable as exc:
        raise HTTPException(503, "Resource authorization unavailable") from exc


async def require_delegated_owner_permission(
    db: AsyncSession,
    delegated_identity,
    user_id: int,
    resource_type: str,
    resource_id: int,
    action: str,
) -> None:
    """Bind a delegated platform identity to a local owner and exact instance.

    Legacy service routes do not have a local user session, so SQL ownership by
    itself is insufficient: a caller could otherwise name another user's row and
    cause an authorization lookup for that other user.  Require the verified
    delegation subject and tenant to match the immutable local platform binding
    before asking for the resource-instance decision.
    """
    if (
        resource_type not in ("Identity", "Account")
        or type(resource_id) is not int
        or resource_id <= 0
        or action not in ("read", "update", "delete", "use")
        or (action == "use" and resource_type != "Identity")
    ):
        raise HTTPException(403, "Invalid resource permission request")
    subject = getattr(delegated_identity, "subject", None)
    tenant = getattr(delegated_identity, "tenant_id", None)
    if (
        not isinstance(subject, str)
        or not subject
        or subject.strip() != subject
        or len(subject) > 255
        or not isinstance(tenant, str)
        or not tenant
        or tenant.strip() != tenant
        or len(tenant) > 255
    ):
        raise HTTPException(403, "Verified delegated owner required")
    result = await db.execute(
        select(PlatformIdentity).where(PlatformIdentity.user_id == user_id)
    )
    binding = result.scalar_one_or_none()
    if (
        binding is None
        or binding.verified_at is None
        or binding.subject != subject
        or binding.tenant != tenant
    ):
        raise HTTPException(403, "Delegated owner does not match local binding")
    try:
        await require_permission(
            subject,
            tenant,
            "fuzekeys_" + resource_type,
            action,
            resource_key=resource_type.lower() + ":" + str(resource_id),
        )
    except PlatformAuthorizationUnavailable as exc:
        raise HTTPException(503, "Resource authorization unavailable") from exc
