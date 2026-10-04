"""Credential custody and non-secret connector metadata.

Provider protocols live in consuming Fuze services. Secrets stay in OpenBao.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import urllib.parse
from typing import Any, Dict, List, Optional, cast

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.broker import runtime
from app.broker.vault import MutableSecretVault
from app.database import get_db
from app.models.connector import ConnectorCredential
from app.security.fuzefront_auth import Identity, delegated_auth

router = APIRouter(prefix="/api/v1/connectors", tags=["Connectors"])
logger = logging.getLogger(__name__)
GMAIL = "google-gmail"
_PROVIDER_ID = re.compile(r"^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$")


class ConnectorConfiguration(BaseModel):
    include_spam_trash: bool = False
    query: str = Field(default="in:inbox", max_length=500)


class CredentialUpdate(BaseModel):
    credential: Dict[str, Any]
    identity_email: Optional[str] = None
    scopes: Optional[List[str]] = None
    configuration: Optional[Dict[str, Any]] = None


def _provider(value: str) -> str:
    # Reject path traversal, encoded separators, and aliases before constructing a vault key.
    if len(value) > 80 or not _PROVIDER_ID.fullmatch(value):
        raise HTTPException(status_code=422, detail="invalid connector provider ID")
    return value


def _vault() -> MutableSecretVault:
    vault = runtime.get_vault()
    if not isinstance(vault, MutableSecretVault):
        raise HTTPException(status_code=503, detail="mutable vault is not configured")
    return vault


async def _record(
    db: AsyncSession, owner: str, provider: str
) -> Optional[ConnectorCredential]:
    result = await db.execute(
        select(ConnectorCredential).where(
            ConnectorCredential.owner_subject == owner,
            ConnectorCredential.provider == provider,
        )
    )
    return result.scalar_one_or_none()


@router.get("/{provider}", operation_id="get_connector_status")
@router.get("/google-gmail", operation_id="get_connectors_google_gmail_status", openapi_extra={"x-pagination": "exempt"})
async def status(
    provider: str = GMAIL,
    identity: Identity = Depends(delegated_auth("connectors:metadata")),
    db: AsyncSession = Depends(get_db),
):
    provider = _provider(provider)
    row = await _record(db, identity.subject, provider)
    if row is None:
        return {"provider": provider, "status": "disconnected"}
    return {
        "provider": provider,
        "status": row.status,
        "identity_email": row.identity_email,
        "scopes": row.scopes,
        "configuration": row.configuration,
    }


@router.patch(
    "/google-gmail", operation_id="patch_connectors_google_gmail_configuration"
)
async def configure_gmail(
    body: ConnectorConfiguration,
    identity: Identity = Depends(delegated_auth("connectors:metadata")),
    db: AsyncSession = Depends(get_db),
):
    return await _configure(GMAIL, body.dict(), identity, db)


@router.patch("/{provider}", operation_id="patch_connector_configuration")
async def configure(
    provider: str,
    body: Dict[str, Any],
    identity: Identity = Depends(delegated_auth("connectors:metadata")),
    db: AsyncSession = Depends(get_db),
):
    return await _configure(_provider(provider), body, identity, db)


async def _configure(
    provider: str, configuration: Dict[str, Any], identity: Identity, db: AsyncSession
):
    row = await _record(db, identity.subject, provider)
    if row is None:
        raise HTTPException(status_code=404, detail="connector is not connected")
    row.configuration = configuration  # type: ignore[assignment]
    await db.commit()
    return {"status": "configured", "configuration": row.configuration}


@router.delete("/{provider}", operation_id="delete_connector")
@router.delete("/google-gmail", operation_id="delete_connectors_google_gmail")
async def disconnect(
    provider: str = GMAIL,
    identity: Identity = Depends(delegated_auth("connectors:metadata")),
    db: AsyncSession = Depends(get_db),
):
    provider = _provider(provider)
    row = await _record(db, identity.subject, provider)
    if row is not None:
        await asyncio.to_thread(_vault().delete, cast(str, row.vault_ref))
        await db.delete(row)
        await db.commit()
    return {"status": "disconnected"}


@router.get("/{provider}/credential", include_in_schema=False)
@router.get("/google-gmail/credential", include_in_schema=False)
async def lease_credential(
    provider: str = GMAIL,
    identity: Identity = Depends(delegated_auth("connectors:credentials:read")),
    db: AsyncSession = Depends(get_db),
):
    provider = _provider(provider)
    row = await _record(db, identity.subject, provider)
    if row is None:
        raise HTTPException(status_code=404, detail="connector is not connected")
    raw = await asyncio.to_thread(_vault().load_root, cast(str, row.vault_ref))
    if raw is None:
        raise HTTPException(
            status_code=409, detail="connector credential is unavailable"
        )
    logger.info(
        "connector credential leased",
        extra={"owner_subject": identity.subject, "provider": provider},
    )
    return {
        "credential": json.loads(raw),
        "configuration": row.configuration,
        "identity_email": row.identity_email,
    }


@router.put("/{provider}/credential", include_in_schema=False)
@router.put("/google-gmail/credential", include_in_schema=False)
async def update_credential(
    body: CredentialUpdate,
    provider: str = GMAIL,
    identity: Identity = Depends(delegated_auth("connectors:credentials:write")),
    db: AsyncSession = Depends(get_db),
):
    provider = _provider(provider)
    owner = identity.subject
    row = await _record(db, owner, provider)
    if row is None:
        vault_ref = f"connectors/{urllib.parse.quote(owner, safe='')}/{provider}"
        row = ConnectorCredential(
            owner_subject=owner, provider=provider, vault_ref=vault_ref
        )
        db.add(row)
    await asyncio.to_thread(
        _vault().put, cast(str, row.vault_ref), json.dumps(body.credential).encode()
    )
    if body.identity_email is not None:
        row.identity_email = body.identity_email  # type: ignore[assignment]
    if body.scopes is not None:
        row.scopes = body.scopes  # type: ignore[assignment]
    if body.configuration is not None:
        row.configuration = body.configuration  # type: ignore[assignment]
    row.status = "connected"  # type: ignore[assignment]
    await db.commit()
    logger.info(
        "connector credential updated",
        extra={"owner_subject": owner, "provider": provider},
    )
    return {"status": "updated"}
