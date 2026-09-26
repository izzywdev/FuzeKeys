"""FuzeFront Security middleware binding for this Python service.

Kept API-compatible with ``fuzefront-service-auth`` so it can be replaced by
the published package without changing route dependencies.
"""
import json
import os
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Optional

from fastapi import Header, HTTPException, Request


@dataclass(frozen=True)
class Identity:
    subject: str
    scopes: frozenset[str]
    audience: Optional[str] = None
    actor: Optional[dict] = None
    token_kind: Optional[str] = None


def _introspect(token: str) -> Identity:
    base = os.environ.get(
        "FUZEFRONT_SECURITY_URL", "http://fuzefront-security:3002"
    ).rstrip("/")
    if urllib.parse.urlparse(base).scheme not in {"http", "https"}:
        raise HTTPException(status_code=401, detail="invalid identity service URL")
    request = urllib.request.Request(
        f"{base}/api/v1/security/tokens/introspect",
        data=json.dumps({"token": token}).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        # Origin is constrained to http(s) above.
        with urllib.request.urlopen(request, timeout=3) as response:  # nosec B310
            body = json.loads(response.read())
    except Exception as exc:
        raise HTTPException(
            status_code=401, detail="identity verification unavailable"
        ) from exc
    if body.get("active") is not True or not body.get("subject"):
        raise HTTPException(status_code=401, detail="inactive identity")
    return Identity(
        subject=body["subject"],
        scopes=frozenset(str(body.get("scope", "")).split()),
        audience=body.get("audience"),
        actor=body.get("actor"),
        token_kind=body.get("tokenKind"),
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
