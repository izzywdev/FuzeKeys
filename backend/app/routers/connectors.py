"""Credential custody and non-secret connector metadata.

Provider protocols live in consuming Fuze services. Secrets stay in OpenBao.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import re
import urllib.parse
from typing import Any, Dict, List, Optional, cast

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import text
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
_GOOGLE_SCOPE_ROOT = "https://www.googleapis.com/auth/"
GOOGLE_SCOPES = {
    GMAIL: {"gmail.readonly"},
    "google-drive": {"drive.readonly"},
    "google-calendar": {"calendar.readonly"},
    "google-contacts": {"contacts.readonly"},
    "google-sheets": {"spreadsheets.readonly"},
    "google-docs": {"documents.readonly"},
    "google-slides": {"presentations.readonly", "drive.metadata.readonly"},
    "google-tasks": {"tasks.readonly"},
}
_PROVIDER_ID = re.compile(r"^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$")


class ConnectorConfiguration(BaseModel):
    include_spam_trash: bool = False
    query: str = Field(default="in:inbox", max_length=500)


class GoogleIdentity(BaseModel):
    model_config = {"extra": "forbid"}
    subject: str = Field(min_length=1, max_length=255, pattern=r"^\S+$")
    client_id: str = Field(min_length=1, max_length=255, pattern=r"^\S+$")


class CredentialUpdate(BaseModel):
    credential: Dict[str, Any]
    identity_email: Optional[str] = None
    scopes: Optional[List[str]] = None
    configuration: Optional[Dict[str, Any]] = None
    google_identity: Optional[GoogleIdentity] = None


def _canonical_google_ref(owner: str) -> str:
    # Preserve the deployed Gmail key while sharing only credential custody.
    return f"connectors/{urllib.parse.quote(owner, safe='')}/{GMAIL}"


async def _lock_google(db: AsyncSession, owner: str) -> None:
    # Transaction-scoped, cross-replica serialization. A process lock is not enough.
    # SQLite tests have one writer; production uses PostgreSQL.
    if db.get_bind().dialect.name == "postgresql":
        key = int.from_bytes(
            hashlib.sha256(f"fuzekeys:google:{owner}".encode()).digest()[:8],
            "big",
            signed=True,
        )
        await db.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": key})


async def _google_records(db: AsyncSession, owner: str):
    result = await db.execute(
        select(ConnectorCredential).where(
            ConnectorCredential.owner_subject == owner,
            ConnectorCredential.provider.in_(GOOGLE_SCOPES),
        )
    )
    return list(result.scalars().all())


def _google_scopes(credential: Dict[str, Any]) -> set[str]:
    scope = credential.get("scope")
    return set(scope.split()) if isinstance(scope, str) else set()


def _require_google_scopes(credential: Dict[str, Any], providers) -> None:
    granted = _google_scopes(credential)
    required = {
        _GOOGLE_SCOPE_ROOT + scope
        for provider in providers
        for scope in GOOGLE_SCOPES[provider]
    }
    if not required.issubset(granted):
        raise HTTPException(
            status_code=409, detail="Google authorization requires additional consent"
        )


async def _load_google(vault_ref: str):
    raw = await asyncio.to_thread(_vault().load_root, vault_ref)
    if raw is None:
        return {}, None
    data = json.loads(raw)
    if isinstance(data, dict) and isinstance(data.get("credential"), dict):
        binding = data.get("google_identity")
        return data["credential"], binding if isinstance(binding, dict) else None
    # Deployed Gmail credentials are unwrapped and have no verified binding.
    return data if isinstance(data, dict) else {}, None


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
@router.get(
    "/google-gmail",
    operation_id="get_connectors_google_gmail_status",
    openapi_extra={"x-pagination": "exempt"},
)
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
    if provider in GOOGLE_SCOPES:
        await _lock_google(db, identity.subject)
    row = await _record(db, identity.subject, provider)
    if row is not None:
        retained = []
        if provider in GOOGLE_SCOPES:
            retained = [
                other
                for other in await _google_records(db, identity.subject)
                if other.provider != provider and other.vault_ref == row.vault_ref
            ]
        if not retained:
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
    if provider in GOOGLE_SCOPES:
        await _lock_google(db, identity.subject)
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
    credential = json.loads(raw)
    binding = None
    if provider in GOOGLE_SCOPES:
        credential, binding = await _load_google(cast(str, row.vault_ref))
        # Legacy Gmail remains readable until expiry/reauthorization. No legacy
        # blob can be implicitly shared with a newly connected provider.
        if binding is not None or provider != GMAIL:
            _require_google_scopes(credential, [provider])
    return {
        "credential": credential,
        "google_identity": binding,
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
    google = provider in GOOGLE_SCOPES
    if google:
        await _lock_google(db, owner)
    row = await _record(db, owner, provider)
    credential = dict(body.credential)
    payload: Dict[str, Any] = credential
    if google:
        if body.google_identity is None:
            raise HTTPException(
                status_code=409,
                detail="Google identity verification requires reauthorization",
            )
        canonical = _canonical_google_ref(owner)
        records = await _google_records(db, owner)
        if any(record.vault_ref != canonical for record in records):
            raise HTTPException(
                status_code=409,
                detail="Disconnect legacy Google connectors before authorizing one shared account",
            )
        previous, binding = await _load_google(canonical)
        new_binding = body.google_identity.model_dump()
        if (
            binding is None
            and records
            and (
                provider != GMAIL or any(record.provider != GMAIL for record in records)
            )
        ):
            # Even a token granting Gmail scopes proves nothing about the
            # account behind an existing unbound Gmail credential. Only an
            # explicit Gmail reconnect may replace a sole legacy Gmail record.
            raise HTTPException(
                status_code=409,
                detail="Reauthorize Gmail before connecting other Google providers, or disconnect legacy Google connectors",
            )
        if binding is not None and binding != new_binding:
            raise HTTPException(
                status_code=409,
                detail="Disconnect Google connectors before switching accounts or OAuth clients",
            )
        if (
            not isinstance(credential.get("access_token"), str)
            or not credential["access_token"]
        ):
            raise HTTPException(
                status_code=422, detail="Google access token is required"
            )
        if not credential.get("refresh_token"):
            if binding == new_binding and previous.get("refresh_token"):
                credential["refresh_token"] = previous["refresh_token"]
            else:
                raise HTTPException(
                    status_code=409,
                    detail="Google offline consent requires reauthorization",
                )
        # An explicit new grant must preserve every still-connected resource.
        # Do not union old scopes into a token that no longer grants them.
        _require_google_scopes(
            credential, {provider, *(record.provider for record in records)}
        )
        payload = {"credential": credential, "google_identity": new_binding}
    if row is None:
        vault_ref = (
            _canonical_google_ref(owner)
            if google
            else f"connectors/{urllib.parse.quote(owner, safe='')}/{provider}"
        )
        row = ConnectorCredential(
            owner_subject=owner, provider=provider, vault_ref=vault_ref
        )
        db.add(row)
    await asyncio.to_thread(
        _vault().put, cast(str, row.vault_ref), json.dumps(payload).encode()
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
