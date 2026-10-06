"""Dedicated Connector instance decisions from verified delegation identity."""

import hashlib
import json

from fastapi import HTTPException

from app.security.platform_authz import (
    PlatformAuthorizationUnavailable,
    check_permission,
)


def connector_tenant(identity):
    tenant = identity.tenant_id
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
    try:
        allow = await check_permission(
            identity.subject,
            tenant,
            "fuzekeys_Connector",
            action,
            resource_key=connector_resource_key(tenant, identity.subject, provider),
        )
    except PlatformAuthorizationUnavailable as exc:
        raise HTTPException(503, "Connector authorization unavailable") from exc
    if allow is not True:
        raise HTTPException(403, "Connector permission denied")
