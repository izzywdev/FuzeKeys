"""
Broker error types.

SECURITY — non-disclosing denials. Every rejection (unknown grant, wrong
redeemer, expired, already-used, revoked, out-of-scope) surfaces the SAME opaque
``BrokerDenied`` with a generic public message. The caller must NOT be able to
distinguish "no such grant" from "grant exists but you may not redeem it" — that
distinction is an oracle that leaks the existence of secrets/grants. The real
reason is carried in ``internal_reason`` for the audit log ONLY, never returned.

Mirrors A2A authz.md §1: deny by default, disclose nothing.
"""
from __future__ import annotations


class BrokerError(Exception):
    """Base broker error."""


class BrokerConfigError(BrokerError):
    """Broker is misconfigured (fail closed, do not release)."""


class BrokerDenied(BrokerError):
    """A non-disclosing denial. Public message is intentionally generic."""

    #: The single public message for ALL denial reasons.
    PUBLIC_MESSAGE = "grant is not redeemable"

    def __init__(self, internal_reason: str):
        # internal_reason is for audit only and must never be sent to the caller.
        self.internal_reason = internal_reason
        super().__init__(self.PUBLIC_MESSAGE)

    @property
    def public_message(self) -> str:
        return self.PUBLIC_MESSAGE


class ApprovalRequired(BrokerError):
    """The grant is high-sensitivity and needs human approval before release.

    This is NOT a denial — it is a legitimate deferred state. It deliberately
    carries only a request id + expiry, never any indication about the secret.
    """

    def __init__(self, request_id: int, expires_at):
        self.request_id = request_id
        self.expires_at = expires_at
        super().__init__("approval_required")
