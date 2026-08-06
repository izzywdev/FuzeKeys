"""Async HTTP client for the FuzeFront Security API.

Only the endpoints FuzeKeys actually needs are implemented, each one taken
verbatim from the published contract (`packages/security/openapi.yaml`):

    GET    /v1/security/session          getSession       -> SessionInfo
    DELETE /v1/security/session          deleteSession    -> 204
    POST   /v1/security/authz/check      authzCheck       -> AuthzDecision
    POST   /v1/security/authz/bulk-check authzBulkCheck   -> AuthzBulkDecision
    GET    /v1/security/authz/permissions getPermissions  -> PermissionSet

No endpoint is invented here. If FuzeKeys needs a capability with no operation
in the contract, that is a contract gap to be raised against FuzeFront — never
worked around with a direct call to some other system.

FAIL-CLOSED is the whole point of this module. Any transport error, timeout,
non-2xx status, or unparseable body results in a denial, never an allow.
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

import httpx

from app.utils.logging import get_logger

from .contract import AuthzCheck, Identity

logger = get_logger(__name__)

# ── Configuration ─────────────────────────────────────────────────────────────
# This points at FUZEFRONT's own service. It is the ONLY auth-related endpoint
# FuzeKeys is allowed to know about, and it is deliberately platform-side
# config: the identity provider and policy engine sitting behind it are
# FuzeFront's business, invisible from here.
_DEFAULT_BASE_URL = "http://fuzefront-backend:3001"
_DEFAULT_TIMEOUT = 5.0


def _base_url() -> str:
    return os.getenv("FUZEFRONT_SECURITY_BASE_URL", _DEFAULT_BASE_URL).rstrip("/")


def _timeout() -> float:
    try:
        return float(os.getenv("FUZEFRONT_SECURITY_TIMEOUT_SECONDS", _DEFAULT_TIMEOUT))
    except (TypeError, ValueError):
        return _DEFAULT_TIMEOUT


def _service_token() -> Optional[str]:
    """Optional service-to-service token for server-initiated authz calls.

    Some deployments require the caller of `authz/check` to authenticate as a
    service rather than replay the end-user token. When set, it is used for
    authz calls made on behalf of a subject other than the caller.
    """
    token = os.getenv("FUZEFRONT_SECURITY_SERVICE_TOKEN")
    return token.strip() if token and token.strip() else None


class SecurityError(Exception):
    """A provider-neutral security failure.

    `code` uses the contract's `SecurityErrorCode` vocabulary so callers never
    have to interpret a vendor-specific error.
    """

    def __init__(self, code: str, message: str, status_code: int = 401):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


class FuzeFrontSecurityClient:
    """Thin, fail-closed client over the FuzeFront Security API."""

    def __init__(
        self,
        base_url: Optional[str] = None,
        timeout: Optional[float] = None,
        transport: Optional[httpx.AsyncBaseTransport] = None,
    ):
        self.base_url = (base_url or _base_url()).rstrip("/")
        self.timeout = timeout if timeout is not None else _timeout()
        self._transport = transport
        self._client: Optional[httpx.AsyncClient] = None

    # ── lifecycle ────────────────────────────────────────────────────────────
    def _http(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=self.timeout,
                transport=self._transport,
            )
        return self._client

    async def aclose(self) -> None:
        if self._client is not None and not self._client.is_closed:
            await self._client.aclose()
        self._client = None

    # ── session (AuthN) ──────────────────────────────────────────────────────
    async def get_session(self, token: str) -> Identity:
        """`GET /v1/security/session` — verify a token and return the identity.

        This REPLACES local token verification entirely. FuzeKeys does not hold
        a signing key, does not decode a JWT, and does not know the token
        format; it asks FuzeFront who the caller is.
        """
        if not token or not token.strip():
            raise SecurityError("NO_TOKEN", "No session token presented", 401)

        try:
            response = await self._http().get(
                "/v1/security/session",
                headers={"Authorization": f"Bearer {token}"},
            )
        except httpx.HTTPError as exc:
            # Fail closed: an unreachable verifier is NOT an allow.
            logger.error("Security session verification unavailable: %s", exc)
            raise SecurityError(
                "VERIFIER_UNAVAILABLE",
                "Authentication service unavailable",
                503,
            ) from exc

        if response.status_code == 401:
            raise SecurityError("INVALID_SIGNATURE", "Could not validate credentials", 401)
        if response.status_code >= 500:
            raise SecurityError(
                "VERIFIER_UNAVAILABLE", "Authentication service unavailable", 503
            )
        if response.status_code != 200:
            raise SecurityError("UNKNOWN", "Could not validate credentials", 401)

        try:
            return Identity.from_session_info(response.json())
        except (ValueError, TypeError) as exc:
            logger.error("Malformed SessionInfo from security service: %s", exc)
            raise SecurityError("MALFORMED", "Could not validate credentials", 401) from exc

    async def delete_session(self, token: str) -> None:
        """`DELETE /v1/security/session` — revoke the presented session.

        Idempotent by contract. A transport failure is logged, not raised: the
        client discards its token regardless, and refusing to "log out" because
        the revoke call flapped is worse UX with no security gain (the token
        still expires).
        """
        if not token or not token.strip():
            return
        try:
            await self._http().delete(
                "/v1/security/session",
                headers={"Authorization": f"Bearer {token}"},
            )
        except httpx.HTTPError as exc:
            logger.warning("Session revoke call failed (token discarded anyway): %s", exc)

    # ── authz ────────────────────────────────────────────────────────────────
    def _authz_headers(self, caller_token: Optional[str]) -> Dict[str, str]:
        token = _service_token() or caller_token
        return {"Authorization": f"Bearer {token}"} if token else {}

    async def authz_check(
        self,
        subject: str,
        tenant: str,
        check: AuthzCheck,
        caller_token: Optional[str] = None,
    ) -> bool:
        """`POST /v1/security/authz/check` — one decision. Fail-closed."""
        try:
            response = await self._http().post(
                "/v1/security/authz/check",
                json=check.to_payload(subject, tenant),
                headers=self._authz_headers(caller_token),
            )
        except httpx.HTTPError as exc:
            logger.error("authz/check unavailable, denying: %s", exc)
            return False

        if response.status_code != 200:
            logger.warning(
                "authz/check returned %s for %s:%s, denying",
                response.status_code,
                check.resource_type,
                check.action,
            )
            return False

        try:
            body = response.json()
        except ValueError:
            logger.error("authz/check returned an unparseable body, denying")
            return False

        return bool(isinstance(body, dict) and body.get("allow") is True)

    async def authz_bulk_check(
        self,
        subject: str,
        tenant: str,
        checks: List[AuthzCheck],
        caller_token: Optional[str] = None,
    ) -> List[bool]:
        """`POST /v1/security/authz/bulk-check` — index-aligned decisions.

        Fail-closed per element AND in aggregate: a transport failure, a
        non-200, or a length mismatch yields all-False rather than a partial
        list that a caller might mis-index.
        """
        if not checks:
            return []
        # Contract bounds the array at maxItems: 200.
        if len(checks) > 200:
            raise ValueError("authz/bulk-check accepts at most 200 checks per call")

        payload = {"checks": [c.to_payload(subject, tenant) for c in checks]}
        try:
            response = await self._http().post(
                "/v1/security/authz/bulk-check",
                json=payload,
                headers=self._authz_headers(caller_token),
            )
        except httpx.HTTPError as exc:
            logger.error("authz/bulk-check unavailable, denying all: %s", exc)
            return [False] * len(checks)

        if response.status_code != 200:
            logger.warning(
                "authz/bulk-check returned %s, denying all", response.status_code
            )
            return [False] * len(checks)

        try:
            body = response.json()
            decisions = body["decisions"]
        except (ValueError, KeyError, TypeError):
            logger.error("authz/bulk-check returned an unparseable body, denying all")
            return [False] * len(checks)

        if not isinstance(decisions, list) or len(decisions) != len(checks):
            logger.error(
                "authz/bulk-check returned %s decisions for %s checks, denying all",
                len(decisions) if isinstance(decisions, list) else "?",
                len(checks),
            )
            return [False] * len(checks)

        return [bool(isinstance(d, dict) and d.get("allow") is True) for d in decisions]

    async def get_permissions(
        self,
        subject: str,
        tenant: str,
        caller_token: Optional[str] = None,
    ) -> List[str]:
        """`GET /v1/security/authz/permissions` — effective `resource:action` set.

        Advisory only (used to render UI affordances). `authz/check` stays
        authoritative for every actual decision. Fail-closed to an empty set.
        """
        try:
            response = await self._http().get(
                "/v1/security/authz/permissions",
                params={"subject": subject, "tenant": tenant},
                headers=self._authz_headers(caller_token),
            )
        except httpx.HTTPError as exc:
            logger.error("authz/permissions unavailable: %s", exc)
            return []

        if response.status_code != 200:
            return []

        try:
            body = response.json()
            permissions = body["permissions"]
        except (ValueError, KeyError, TypeError):
            return []

        return [str(p) for p in permissions] if isinstance(permissions, list) else []


# ── Process-wide shared instance ─────────────────────────────────────────────
_client: Optional[FuzeFrontSecurityClient] = None


def get_security_client() -> FuzeFrontSecurityClient:
    """Return the shared client (connection-pooled)."""
    global _client
    if _client is None:
        _client = FuzeFrontSecurityClient()
    return _client


def set_security_client(client: Optional[FuzeFrontSecurityClient]) -> None:
    """Swap the shared client. For tests and for app startup wiring."""
    global _client
    _client = client


async def close_security_client() -> None:
    global _client
    if _client is not None:
        await _client.aclose()
    _client = None


def _reset_config_cache_for_tests() -> None:  # pragma: no cover - test helper
    set_security_client(None)


def get_authz_tenant_fallback() -> Optional[str]:
    """Tenant to use when the identity carries no tenant.

    Deliberately unset by default: with no tenant, tenant-scoped decisions fail
    closed exactly as the contract requires. A single-tenant deployment may set
    `FUZEFRONT_DEFAULT_TENANT` to opt in explicitly.
    """
    tenant = os.getenv("FUZEFRONT_DEFAULT_TENANT")
    return tenant.strip() if tenant and tenant.strip() else None
