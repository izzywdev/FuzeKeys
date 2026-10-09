"""Dedicated Connector instance decisions from verified delegation identity."""

import hashlib
import json

from fastapi import HTTPException

from app.security.platform_authz import (
    PlatformAuthorizationUnavailable,
    check_permission,
)


async def require_permission(*args, **kwargs) -> None:
    """Require an explicit boolean allow from the platform decision service."""
    allowed = await check_permission(*args, **kwargs)
    if allowed is not True:
        raise HTTPException(403, "Connector permission denied")


def connector_tenant(identity):
    tenant = identity.tenant_id
    if tenant is None:
        return None
    if (
        not isinstance(tenant, str)
        or not tenant
        or tenant.strip() != tenant
        or len(tenant) > 255
    ):
        raise HTTPException(403, "Verified connector tenant required")
    subject = identity.subject
    if (
        not isinstance(subject, str)
        or not subject
        or subject.strip() != subject
        or len(subject) > 255
    ):
        raise HTTPException(403, "Verified connector subject required")
    return tenant


def connector_resource_key(tenant, subject, provider):
    # JSON tuple framing avoids delimiter collisions and discloses no subject.
    value = json.dumps(
        [tenant, subject, provider], separators=(",", ":"), ensure_ascii=False
    )
    return "connector:" + hashlib.sha256(value.encode()).hexdigest()


async def require_connector_permission(identity, provider, action):
    tenant = connector_tenant(identity)
    if action not in {
        "read",
        "create",
        "configure",
        "disconnect",
        "reveal",
        "write_credential",
    }:
        raise HTTPException(403, "Invalid connector action")
    # A verified delegation with no selected organization is a personal
    # credential scope. The signed subject is the owner and no tenant grant
    # exists to evaluate; every data query below remains subject-scoped.
    if tenant is None:
        return
    try:
        await require_permission(
            identity.subject,
            tenant,
            "fuzekeys_Connector",
            action,
            resource_key=connector_resource_key(tenant, identity.subject, provider),
        )
    except PlatformAuthorizationUnavailable as exc:
        raise HTTPException(503, "Connector authorization unavailable") from exc
