"""Fail-closed FuzeFront authorization client for the FuzeKeys workload.

Route guards must supply a persisted, verified subject and server-owned resource
key. This client does not infer identity from email or a request body.
"""

from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import urlsplit

import httpx

WORKLOAD_TOKEN_PATH = Path("/var/run/secrets/tokens/token")


class PlatformAuthorizationUnavailable(Exception):
    """The decision could not be established; callers must deny the request."""


def _security_url() -> str:
    raw = os.environ.get("FUZEFRONT_SECURITY_URL", "")
    parsed = urlsplit(raw)
    if parsed.scheme not in ("http", "https") or not parsed.hostname or parsed.username:
        raise PlatformAuthorizationUnavailable("Security URL is not configured")
    if parsed.path not in ("", "/") or parsed.query or parsed.fragment:
        raise PlatformAuthorizationUnavailable("Security URL has an invalid base path")
    return raw.rstrip("/")


def _tenant() -> str:
    tenant = os.environ.get("FUZEKEYS_AUTHZ_TENANT", "")
    if not tenant or tenant.strip() != tenant:
        raise PlatformAuthorizationUnavailable("FuzeKeys tenant is not configured")
    return tenant


async def check_permission(
    subject: str,
    tenant: str,
    resource_type: str,
    action: str,
    *,
    resource_key: str | None = None,
    token_path: Path = WORKLOAD_TOKEN_PATH,
) -> bool:
    """Return True only for an explicit platform allow decision.

    A caller must still enforce its local row ownership and credential checks.
    Missing configuration, invalid identity, transport errors and malformed
    responses raise, so no caller can mistake them for an allow decision.
    """
    if not all(
        isinstance(value, str) and value.strip() == value
        for value in (subject, tenant, resource_type, action)
    ):
        raise PlatformAuthorizationUnavailable("Authorization query is invalid")
    if not subject or not resource_type or not action or tenant != _tenant():
        raise PlatformAuthorizationUnavailable("Authorization query is incomplete")
    if resource_key is not None and (
        not resource_key or resource_key.strip() != resource_key
    ):
        raise PlatformAuthorizationUnavailable("Resource key is invalid")

    base_url = _security_url()
    try:
        service_account_token = token_path.read_text(encoding="utf-8").strip()
        if not service_account_token:
            raise PlatformAuthorizationUnavailable("Workload identity token is empty")
        async with httpx.AsyncClient(timeout=3.0) as client:
            exchange = await client.post(
                f"{base_url}/api/v1/security/tokens/workload",
                json={"serviceAccountToken": service_account_token},
            )
            exchange.raise_for_status()
            workload = exchange.json()
            access_token = (
                workload.get("accessToken") if isinstance(workload, dict) else None
            )
            if not isinstance(access_token, str) or not access_token:
                raise PlatformAuthorizationUnavailable(
                    "Workload exchange was malformed"
                )
            resource = {"type": resource_type}
            if resource_key is not None:
                resource["key"] = resource_key
            response = await client.post(
                f"{base_url}/api/v1/security/authz/check",
                headers={"Authorization": f"Bearer {access_token}"},
                json={
                    "subject": subject,
                    "tenant": tenant,
                    "resource": resource,
                    "action": action,
                },
            )
            response.raise_for_status()
            decision = response.json()
            if (
                not isinstance(decision, dict)
                or type(decision.get("allow")) is not bool
            ):
                raise PlatformAuthorizationUnavailable(
                    "Authorization decision was malformed"
                )
            return decision["allow"] is True
    except (OSError, httpx.HTTPError, ValueError, TypeError) as exc:
        raise PlatformAuthorizationUnavailable(
            "Authorization decision unavailable"
        ) from exc
