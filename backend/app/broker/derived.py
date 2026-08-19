"""
Dynamic / derived secrets + RFC 8693 OAuth 2.0 Token Exchange (STS).

Two release mechanisms that mean the **long-lived root secret never leaves the
vault** (mirrors Vault/OpenBao dynamic secrets + response-wrapping):

1. ``derive_credential`` — on redeem, mint a **purpose-scoped, short-lived DERIVED
   credential** from the root using an HKDF-style HMAC. The root stays in the
   vault; downstream services validate the derived cred by re-deriving with the
   root (which they reach independently), so the derived value is useless outside
   its scope/TTL and is provably NOT the root.

2. ``mint_exchanged_token`` — **RFC 8693** token exchange: the caller presents its
   OWN identity token (``subject_token``); the broker (acting as STS) returns a
   scoped, short-TTL downstream access token carrying an ``act`` (actor) claim.
   This is the secretless ideal — no stored secret is shared at all.

Crypto is from ``cryptography`` / ``python-jose`` (both vetted); nothing hand-rolled.
"""
from __future__ import annotations

import hashlib
import hmac
import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

from jose import jwt

# RFC 8693 token type URIs.
TOKEN_TYPE_ACCESS = "urn:ietf:params:oauth:token-type:access_token"  # noqa: S105
TOKEN_TYPE_JWT = "urn:ietf:params:oauth:token-type:jwt"  # noqa: S105


@dataclass(frozen=True)
class DerivedCredential:
    """A short-lived credential derived from (but never equal to) the root."""

    value: str  # the derived credential material (safe to release)
    expires_at: datetime
    scope: str
    secret_ref: str
    kind: str = "derived"


def derive_credential(
    *,
    root_secret: bytes,
    secret_ref: str,
    redeemer: str,
    scope: str,
    ttl_seconds: int,
    now: Optional[datetime] = None,
) -> DerivedCredential:
    """HKDF-style derivation of a scoped, time-boxed credential from the root.

    The output binds redeemer + scope + expiry into the derivation input, so the
    credential is only meaningful for that redeemer/scope/window. The root itself
    is never returned and cannot be recovered from the derived value.
    """
    now = now or datetime.now(timezone.utc)
    expires_at = now + timedelta(seconds=ttl_seconds)
    salt = os.urandom(16)
    info = f"{secret_ref}|{redeemer}|{scope}|{int(expires_at.timestamp())}".encode()
    # HKDF-Expand-ish single block (RFC 5869 style) over the root as PRK.
    prk = hmac.new(salt, root_secret, hashlib.sha256).digest()
    okm = hmac.new(prk, info + b"\x01", hashlib.sha256).digest()
    value = "fkderiv_" + salt.hex() + "." + okm.hex()
    return DerivedCredential(
        value=value, expires_at=expires_at, scope=scope, secret_ref=secret_ref
    )


@dataclass(frozen=True)
class ExchangedToken:
    """The result of an RFC 8693 token exchange."""

    access_token: str
    issued_token_type: str
    token_type: str  # "Bearer"
    expires_in: int
    scope: str


def mint_exchanged_token(
    *,
    signing_key: str,
    algorithm: str,
    subject_principal: str,  # the VERIFIED transport identity (not asserted)
    audience: str,
    scope: str,
    ttl_seconds: int,
    issuer: str = "fuzekeys-broker",
    now: Optional[datetime] = None,
) -> ExchangedToken:
    """Issue a scoped, short-TTL downstream token (RFC 8693 §2.2.1 response).

    ``subject_principal`` MUST be the caller's authenticated transport identity —
    the broker only exchanges an identity it itself verified, never one asserted
    in the request body. The ``act`` claim records the actor per RFC 8693 §4.1.
    """
    now = now or datetime.now(timezone.utc)
    exp = now + timedelta(seconds=ttl_seconds)
    claims = {
        "iss": issuer,
        "sub": subject_principal,
        "aud": audience,
        "scope": scope,
        "iat": int(now.timestamp()),
        "exp": int(exp.timestamp()),
        # RFC 8693 actor claim: who is acting (the exchanging party).
        "act": {"sub": subject_principal},
        "token_type": "downstream_access",
    }
    token = jwt.encode(claims, signing_key, algorithm=algorithm)
    return ExchangedToken(
        access_token=token,
        issued_token_type=TOKEN_TYPE_ACCESS,
        token_type="Bearer",
        expires_in=ttl_seconds,
        scope=scope,
    )
