"""FuzeFront Security middleware binding for delegated connector requests."""
import os
from dataclasses import dataclass
from functools import lru_cache
from typing import Optional

from fastapi import Header, HTTPException, Request
from fuzefront_service_auth import MachineTokenVerifier, TokenVerificationError


@dataclass(frozen=True)
class Identity:
    subject: str
    scopes: frozenset[str]
    audience: Optional[str] = None
    actor: Optional[dict] = None
    token_kind: Optional[str] = None


@lru_cache(maxsize=1)
def _verifier() -> MachineTokenVerifier:
    base = os.environ.get("FUZEFRONT_SECURITY_URL", "http://fuzefront-security:3002")
    if not base.startswith(("http://", "https://")):
        raise HTTPException(status_code=503, detail="invalid identity service URL")
    return MachineTokenVerifier(base_url=base, timeout=3)


def _introspect(token: str) -> Identity:
    try:
        verified = _verifier().verify_machine_token(token)
    except TokenVerificationError as exc:
        raise HTTPException(
            status_code=401, detail="identity verification unavailable"
        ) from exc
    return Identity(
        subject=verified.subject,
        scopes=frozenset(verified.scopes),
        audience=verified.audience,
        actor=verified.actor,
        token_kind=verified.token_kind,
    )


def delegated_auth(required_scope: str):
    async def dependency(
        request: Request,
        authorization: str = Header(...),
        x_fuze_delegation: str = Header(...),
    ) -> Identity:
        if not authorization.lower().startswith(
            "bearer "
        ) or not x_fuze_delegation.lower().startswith("bearer "):
            raise HTTPException(
                status_code=401, detail="service and delegation tokens are required"
            )
        machine = _introspect(authorization.split(" ", 1)[1])
        delegated = _introspect(x_fuze_delegation.split(" ", 1)[1])
        if (
            machine.token_kind != "fuze-workload"
            or delegated.token_kind != "fuze-delegation"
            or delegated.audience != "service:fuzekeys"
            or not delegated.actor
            or delegated.actor.get("sub") != machine.subject
            or required_scope not in delegated.scopes
        ):
            raise HTTPException(status_code=403, detail="delegation is not authorized")
        request.state.machine_identity = machine
        request.state.delegated_identity = delegated
        return delegated

    return dependency
