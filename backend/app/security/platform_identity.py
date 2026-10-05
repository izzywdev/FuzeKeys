"""Verify both a platform session and canonical active organization membership."""

import httpx

from app.security.platform_authz import (
    PlatformAuthorizationUnavailable,
    _security_url,
    _tenant,
)


class PlatformIdentityRejected(Exception):
    """The supplied platform session does not prove the required membership."""


async def verify_platform_identity(token: str) -> tuple[str, str]:
    # Only the operator's tenant and origin are trusted. Request input supplies
    # a session credential, never a subject, tenant, URL, email or role.
    if not token or len(token) > 8192 or any(c.isspace() for c in token):
        raise PlatformIdentityRejected("Invalid platform session")
    tenant = _tenant()
    base_url = _security_url()
    try:
        async with httpx.AsyncClient(timeout=3.0, follow_redirects=False) as client:
            headers = {"Authorization": f"Bearer {token}"}
            session = await client.get(
                f"{base_url}/api/v1/security/session",
                headers=headers,
                params={"tenant": tenant},
            )
            if session.status_code in (401, 403):
                raise PlatformIdentityRejected("Invalid platform session")
            session.raise_for_status()
            payload = session.json()
            identity = payload.get("identity") if isinstance(payload, dict) else None
            if not isinstance(identity, dict):
                raise PlatformAuthorizationUnavailable("Platform identity malformed")
            subject = identity.get("userId")
            if (
                not isinstance(subject, str)
                or not subject
                or len(subject) > 255
                or subject.strip() != subject
            ):
                raise PlatformAuthorizationUnavailable("Platform identity malformed")

            # The optional Security tenant proof requires canonical active SQL
            # membership. Older deployments return tenantId null and fail closed.
            if identity.get("tenantId") != tenant:
                raise PlatformIdentityRejected("Active tenant membership required")
            return subject, tenant
    except (httpx.HTTPError, ValueError, TypeError) as exc:
        raise PlatformAuthorizationUnavailable("Platform identity unavailable") from exc
