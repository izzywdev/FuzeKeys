"""Provider-neutral shapes mirrored from the FuzeFront Security contract.

These are the Python counterparts of the TypeScript types exported by
`@fuzefront/security-client` (`packages/security/src/types.ts` +
`openapi.yaml`). They are deliberately a hand-mirror rather than a generated
artifact: FuzeKeys consumes only a small slice of the contract (session +
authz), and a generated Python client is not published for it.

If any shape here drifts from the published contract, the mismatch surfaces as
a parse failure in `client.py`, not as a silent allow.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

# Major of the FuzeFront Security contract this module is written against.
# The contract states consumers may assert on the major (`SECURITY_CONTRACT_VERSION`).
SECURITY_CONTRACT_MAJOR = 0

# Verification modes the contract may report. Provider-neutral by design:
# these name token formats, never a vendor.
AUTH_MODES = ("legacy-hs256", "federated-jwks")


@dataclass(frozen=True)
class Identity:
    """The stable normalized identity — the contract's keystone.

    Mirrors `components.schemas.Identity`. `tenant_id` is `None` when the token
    carries no resolvable tenant; consumers MUST fail closed on any
    tenant-scoped authorization decision when that happens.
    """

    user_id: str
    tenant_id: Optional[str]
    roles: List[str]
    auth_mode: str
    email: Optional[str] = None
    issued_at: Optional[int] = None
    expires_at: Optional[int] = None
    issuer: Optional[str] = None
    # Hydrated user projection returned alongside the identity by
    # `GET /v1/security/session` (`components.schemas.SessionInfo.user`).
    user: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_session_info(cls, payload: Dict[str, Any]) -> "Identity":
        """Parse a `SessionInfo` body. Raises ValueError on a malformed body."""
        if not isinstance(payload, dict):
            raise ValueError("SessionInfo body is not an object")

        identity = payload.get("identity")
        if not isinstance(identity, dict):
            raise ValueError("SessionInfo.identity missing or not an object")

        user_id = identity.get("userId")
        if not isinstance(user_id, str) or not user_id:
            raise ValueError("Identity.userId missing")

        roles = identity.get("roles")
        if not isinstance(roles, list):
            raise ValueError("Identity.roles missing or not an array")

        auth_mode = identity.get("authMode")
        if not isinstance(auth_mode, str):
            raise ValueError("Identity.authMode missing")

        tenant_id = identity.get("tenantId")
        if tenant_id is not None and not isinstance(tenant_id, str):
            raise ValueError("Identity.tenantId must be a string or null")

        user = payload.get("user")
        if not isinstance(user, dict):
            user = {}

        return cls(
            user_id=user_id,
            tenant_id=tenant_id,
            roles=[str(r) for r in roles],
            auth_mode=auth_mode,
            email=identity.get("email") or user.get("email"),
            issued_at=identity.get("issuedAt"),
            expires_at=identity.get("expiresAt"),
            issuer=identity.get("issuer"),
            user=user,
        )


@dataclass(frozen=True)
class AuthzCheck:
    """One `AuthzCheckRequest`.

    `resource_type` / `action` are the BARE keys FuzeKeys already declares in
    `registration/policy.json` (e.g. `VaultAsset` / `reveal`). FuzeKeys never
    encodes an engine-specific policy identifier.
    """

    resource_type: str
    action: str
    resource_key: Optional[str] = None
    context: Optional[Dict[str, Any]] = None

    def to_payload(self, subject: str, tenant: str) -> Dict[str, Any]:
        resource: Dict[str, Any] = {"type": self.resource_type}
        if self.resource_key is not None:
            resource["key"] = self.resource_key
        payload: Dict[str, Any] = {
            "subject": subject,
            "tenant": tenant,
            "resource": resource,
            "action": self.action,
        }
        if self.context:
            payload["context"] = self.context
        return payload
