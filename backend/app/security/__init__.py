"""FuzeFront Security integration for FuzeKeys.

FuzeKeys does NOT talk to any identity provider or authorization engine
directly. Every authentication and authorization decision is delegated to the
FuzeFront Security API (`@fuzefront/security-client` contract, `openapi.yaml`
in `packages/security` of the FuzeFront repo).

The provider behind that API — federation, MFA, policy engine — is FuzeFront's
private implementation detail. Nothing in this package (or anywhere else in
FuzeKeys) may name a vendor.

Public surface:
    Identity                      normalized principal (contract keystone)
    SecurityError                 provider-neutral failure
    get_security_client()         shared async HTTP client
    require_identity              FastAPI dep -> Identity
    get_current_user              FastAPI dep -> local User row (legacy name,
                                  kept so every existing router is unchanged)
    require_permission(res, act)  FastAPI dep factory -> authz/check
    check_permission(...)         imperative authz/check
    bulk_check_permissions(...)   imperative authz/bulk-check
"""

from .client import (
    FuzeFrontSecurityClient,
    SecurityError,
    close_security_client,
    get_security_client,
)
from .contract import SECURITY_CONTRACT_MAJOR, AuthzCheck, Identity
from .dependencies import (
    bulk_check_permissions,
    check_permission,
    get_current_user,
    optional_identity,
    require_identity,
    require_permission,
)

__all__ = [
    "AuthzCheck",
    "FuzeFrontSecurityClient",
    "Identity",
    "SECURITY_CONTRACT_MAJOR",
    "SecurityError",
    "bulk_check_permissions",
    "check_permission",
    "close_security_client",
    "get_current_user",
    "get_security_client",
    "optional_identity",
    "require_identity",
    "require_permission",
]
