"""User connector vault and Gmail OAuth/API surface.

Only non-secret metadata is stored in Postgres. Google access/refresh tokens are
serialized into the configured OpenBao KV-v2 mount under a per-user path.
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import os
import secrets
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.broker import runtime
from app.broker.vault import MutableSecretVault
from app.database import get_db
from app.models.connector import ConnectorCredential
from app.routers.auth import get_current_user

router = APIRouter(prefix="/api/v1/connectors", tags=["Connectors"])
PROVIDER = "google-gmail"
SCOPES = [
    "openid",
    "email",
    "profile",
    "https://www.googleapis.com/auth/gmail.readonly",
]
optional_bearer = HTTPBearer(auto_error=False)


class OAuthStartRequest(BaseModel):
    return_to: str = Field(default="/connectors", max_length=1000)


class ConnectorConfiguration(BaseModel):
    include_spam_trash: bool = False
    query: str = Field(default="in:inbox", max_length=500)


async def _connector_owner(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(optional_bearer),
    db: AsyncSession = Depends(get_db),
) -> str:
    """Resolve either a trusted platform-service subject or the MCP caller.

    Internal headers are deliberately read from Request so the shared service
    credential never appears as an MCP tool argument in OpenAPI.
    """
    x_fuze_user_id = request.headers.get("x-fuze-user-id", "")
    x_fuzekeys_internal_token = request.headers.get("x-fuzekeys-internal-token", "")
    expected = os.getenv("FUZEKEYS_CONNECTOR_INTERNAL_TOKEN", "")
    if expected and x_fuze_user_id and hmac.compare_digest(x_fuzekeys_internal_token, expected):
        return x_fuze_user_id.strip()
    if credentials is not None:
        user = await get_current_user(credentials=credentials, db=db)
        return str(user.id)
    raise HTTPException(status_code=401, detail="invalid connector identity")


def _vault() -> MutableSecretVault:
    vault = runtime.get_vault()
    if not isinstance(vault, MutableSecretVault):
        raise HTTPException(status_code=503, detail="mutable vault is not configured")
    return vault


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _state_key() -> bytes:
    key = os.getenv("CONNECTOR_STATE_SIGNING_KEY") or os.getenv("SECRET_KEY", "")
    if len(key) < 32:
        raise HTTPException(status_code=503, detail="connector state signing key is not configured")
    return key.encode()


def _sign_state(user_id: str, return_to: str) -> str:
    payload = {"sub": user_id, "return_to": return_to, "exp": int(time.time()) + 600, "nonce": secrets.token_urlsafe(16)}
    encoded = _b64(json.dumps(payload, separators=(",", ":")).encode())
    signature = _b64(hmac.new(_state_key(), encoded.encode(), hashlib.sha256).digest())
    return f"{encoded}.{signature}"


def _read_state(state: str) -> Dict[str, Any]:
    try:
        encoded, signature = state.split(".", 1)
        expected = _b64(hmac.new(_state_key(), encoded.encode(), hashlib.sha256).digest())
        if not hmac.compare_digest(signature, expected):
            raise ValueError("signature")
        payload = json.loads(base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4)))
        if int(payload["exp"]) < int(time.time()):
            raise ValueError("expired")
        return payload
    except (ValueError, KeyError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=400, detail="invalid or expired OAuth state") from exc


def _google_form(url: str, data: Dict[str, str]) -> Dict[str, Any]:
    request = urllib.request.Request(
        url,
        data=urllib.parse.urlencode(data).encode(),
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        return json.loads(response.read())


def _google_json(url: str, access_token: str) -> Dict[str, Any]:
    request = urllib.request.Request(url, headers={"Authorization": f"Bearer {access_token}"})
    with urllib.request.urlopen(request, timeout=20) as response:
        return json.loads(response.read())


def _oauth_config():
    client_id = os.getenv("GOOGLE_OAUTH_CLIENT_ID", "")
    client_secret = os.getenv("GOOGLE_OAUTH_CLIENT_SECRET", "")
    redirect_uri = os.getenv("GOOGLE_OAUTH_REDIRECT_URI", "")
    if not client_id or not client_secret or not redirect_uri:
        raise HTTPException(status_code=503, detail="Google OAuth is not configured")
    return client_id, client_secret, redirect_uri


async def _record(db: AsyncSession, owner: str) -> Optional[ConnectorCredential]:
    result = await db.execute(select(ConnectorCredential).where(
        ConnectorCredential.owner_subject == owner,
        ConnectorCredential.provider == PROVIDER,
    ))
    return result.scalar_one_or_none()


@router.post("/google-gmail/oauth/start", operation_id="post_connectors_google_gmail_oauth_start")
async def oauth_start(body: OAuthStartRequest, owner: str = Depends(_connector_owner)):
    client_id, _, redirect_uri = _oauth_config()
    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": " ".join(SCOPES),
        "access_type": "offline",
        "include_granted_scopes": "true",
        "prompt": "consent",
        "state": _sign_state(owner, body.return_to),
    }
    return {"authorization_url": f"https://accounts.google.com/o/oauth2/v2/auth?{urllib.parse.urlencode(params)}"}


@router.get("/google-gmail/oauth/callback", operation_id="get_connectors_google_gmail_oauth_callback")
async def oauth_callback(
    code: str = Query(...), state: str = Query(...), db: AsyncSession = Depends(get_db)
):
    payload = _read_state(state)
    owner = str(payload["sub"])
    client_id, client_secret, redirect_uri = _oauth_config()
    token = await asyncio.to_thread(_google_form, "https://oauth2.googleapis.com/token", {
        "code": code,
        "client_id": client_id,
        "client_secret": client_secret,
        "redirect_uri": redirect_uri,
        "grant_type": "authorization_code",
    })
    profile = await asyncio.to_thread(
        _google_json, "https://openidconnect.googleapis.com/v1/userinfo", token["access_token"]
    )
    token["expires_at"] = int(time.time()) + int(token.get("expires_in", 3600))
    token["identity_email"] = profile.get("email")
    vault_ref = f"connectors/{urllib.parse.quote(owner, safe='')}/{PROVIDER}"
    await asyncio.to_thread(_vault().put, vault_ref, json.dumps(token).encode())

    row = await _record(db, owner)
    if row is None:
        row = ConnectorCredential(owner_subject=owner, provider=PROVIDER, vault_ref=vault_ref)
        db.add(row)
    row.identity_email = profile.get("email")
    row.scopes = token.get("scope", "").split()
    row.status = "connected"
    row.configuration = row.configuration or {"query": "in:inbox", "include_spam_trash": False}
    await db.commit()
    return RedirectResponse(str(payload.get("return_to") or "/connectors") + "?connected=google-gmail")


@router.get("/google-gmail", operation_id="get_connectors_google_gmail_status")
async def status(owner: str = Depends(_connector_owner), db: AsyncSession = Depends(get_db)):
    row = await _record(db, owner)
    if row is None:
        return {"provider": PROVIDER, "status": "disconnected"}
    return {"provider": PROVIDER, "status": row.status, "identity_email": row.identity_email,
            "scopes": row.scopes, "configuration": row.configuration}


@router.patch("/google-gmail", operation_id="patch_connectors_google_gmail_configuration")
async def configure(body: ConnectorConfiguration, owner: str = Depends(_connector_owner), db: AsyncSession = Depends(get_db)):
    row = await _record(db, owner)
    if row is None:
        raise HTTPException(status_code=404, detail="connector is not connected")
    row.configuration = body.dict()
    await db.commit()
    return {"status": "configured", "configuration": row.configuration}


@router.delete("/google-gmail", operation_id="delete_connectors_google_gmail")
async def disconnect(owner: str = Depends(_connector_owner), db: AsyncSession = Depends(get_db)):
    row = await _record(db, owner)
    if row is not None:
        await asyncio.to_thread(_vault().delete, row.vault_ref)
        await db.delete(row)
        await db.commit()
    return {"status": "disconnected"}


async def _valid_access_token(row: ConnectorCredential) -> str:
    raw = await asyncio.to_thread(_vault().load_root, row.vault_ref)
    if raw is None:
        raise HTTPException(status_code=409, detail="connector credential is unavailable")
    token = json.loads(raw)
    if int(token.get("expires_at", 0)) > int(time.time()) + 60:
        return token["access_token"]
    refresh_token = token.get("refresh_token")
    if not refresh_token:
        raise HTTPException(status_code=409, detail="Google authorization must be renewed")
    client_id, client_secret, _ = _oauth_config()
    refreshed = await asyncio.to_thread(_google_form, "https://oauth2.googleapis.com/token", {
        "client_id": client_id, "client_secret": client_secret,
        "refresh_token": refresh_token, "grant_type": "refresh_token",
    })
    token.update(refreshed)
    token["refresh_token"] = refresh_token
    token["expires_at"] = int(time.time()) + int(refreshed.get("expires_in", 3600))
    await asyncio.to_thread(_vault().put, row.vault_ref, json.dumps(token).encode())
    return token["access_token"]


def _header(headers, name):
    target = name.lower()
    return next((h.get("value", "") for h in headers if h.get("name", "").lower() == target), "")


@router.get("/google-gmail/messages/recent", operation_id="get_connectors_google_gmail_recent_messages")
async def recent_messages(
    limit: int = Query(5, ge=1, le=20), owner: str = Depends(_connector_owner),
    db: AsyncSession = Depends(get_db),
):
    row = await _record(db, owner)
    if row is None:
        raise HTTPException(status_code=404, detail="Gmail is not connected")
    access_token = await _valid_access_token(row)
    config = row.configuration or {}
    query = config.get("query", "in:inbox")
    params = urllib.parse.urlencode({"maxResults": limit, "q": query, "includeSpamTrash": str(bool(config.get("include_spam_trash", False))).lower()})
    listing = await asyncio.to_thread(_google_json, f"https://gmail.googleapis.com/gmail/v1/users/me/messages?{params}", access_token)
    messages = []
    for item in listing.get("messages", [])[:limit]:
        detail = await asyncio.to_thread(_google_json, f"https://gmail.googleapis.com/gmail/v1/users/me/messages/{item['id']}?format=metadata&metadataHeaders=From&metadataHeaders=Subject&metadataHeaders=Date", access_token)
        headers = detail.get("payload", {}).get("headers", [])
        messages.append({
            "id": detail.get("id"), "thread_id": detail.get("threadId"),
            "from": _header(headers, "From"), "subject": _header(headers, "Subject") or "(no subject)",
            "date": _header(headers, "Date"), "snippet": detail.get("snippet", ""),
        })
    return {"identity_email": row.identity_email, "messages": messages}
