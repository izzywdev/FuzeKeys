"""
Envelope encryption / KMS-style wrap-unwrap (``cryptography`` library — vetted,
NOT hand-rolled).

Use case (the rare tier-2b): a secret must pass through an **untrusted relay**
(an artifact, a broker hop, an MCP arg) to reach a specific recipient agent. We
encrypt it to the **recipient's published public key** (from its agent-card
``securitySchemes`` / a FuzeKeys JWK), so only the recipient's private key can
open it — the relay sees ciphertext only.

Scheme (standard envelope encryption, mirrors AWS KMS / OpenBao transit):
  1. generate a fresh random **data key** (DEK), 32 bytes;
  2. encrypt the payload with **AES-256-GCM** under the DEK (AEAD, integrity);
  3. **wrap** the DEK to the recipient's **RSA public key** with **RSA-OAEP-SHA256**;
  4. ship {wrapped_dek, nonce, ciphertext}. Only the recipient unwraps the DEK.

The broker never persists plaintext and never logs the DEK.
"""
from __future__ import annotations

import base64
import json
import os
from dataclasses import dataclass

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives.ciphers.aead import AESGCM


def _b64u(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64u_dec(data: str) -> bytes:
    pad = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + pad)


@dataclass(frozen=True)
class SealedSecret:
    """Ciphertext bundle safe to hand to an untrusted relay."""

    wrapped_dek: str  # b64url RSA-OAEP-wrapped data key
    nonce: str  # b64url AES-GCM nonce
    ciphertext: str  # b64url AES-GCM ciphertext (incl. tag)
    alg: str = "RSA-OAEP-256+A256GCM"

    def to_json(self) -> str:
        return json.dumps(
            {
                "alg": self.alg,
                "wrapped_dek": self.wrapped_dek,
                "nonce": self.nonce,
                "ciphertext": self.ciphertext,
            },
            separators=(",", ":"),
        )

    @staticmethod
    def from_json(raw: str) -> "SealedSecret":
        d = json.loads(raw)
        return SealedSecret(
            wrapped_dek=d["wrapped_dek"],
            nonce=d["nonce"],
            ciphertext=d["ciphertext"],
            alg=d.get("alg", "RSA-OAEP-256+A256GCM"),
        )


def load_rsa_public_from_jwk(jwk: dict) -> rsa.RSAPublicKey:
    """Load an RSA public key from a published JWK (agent-card securityScheme)."""
    if jwk.get("kty") != "RSA":
        raise ValueError("only RSA JWKs supported for envelope wrap")
    n = int.from_bytes(_b64u_dec(jwk["n"]), "big")
    e = int.from_bytes(_b64u_dec(jwk["e"]), "big")
    return rsa.RSAPublicNumbers(e, n).public_key()


def seal_to_recipient(
    plaintext: bytes, recipient_public: rsa.RSAPublicKey
) -> SealedSecret:
    """Envelope-encrypt ``plaintext`` so only the recipient's private key opens it."""
    dek = AESGCM.generate_key(bit_length=256)
    nonce = os.urandom(12)
    ct = AESGCM(dek).encrypt(nonce, plaintext, None)
    wrapped = recipient_public.encrypt(
        dek,
        padding.OAEP(
            mgf=padding.MGF1(algorithm=hashes.SHA256()),
            algorithm=hashes.SHA256(),
            label=None,
        ),
    )
    return SealedSecret(
        wrapped_dek=_b64u(wrapped), nonce=_b64u(nonce), ciphertext=_b64u(ct)
    )


def open_sealed(sealed: SealedSecret, recipient_private: rsa.RSAPrivateKey) -> bytes:
    """Recipient side: unwrap the DEK, then AES-GCM-decrypt the payload."""
    dek = recipient_private.decrypt(
        _b64u_dec(sealed.wrapped_dek),
        padding.OAEP(
            mgf=padding.MGF1(algorithm=hashes.SHA256()),
            algorithm=hashes.SHA256(),
            label=None,
        ),
    )
    return AESGCM(dek).decrypt(
        _b64u_dec(sealed.nonce), _b64u_dec(sealed.ciphertext), None
    )


def generate_recipient_keypair(bits: int = 2048):
    """Test/helper: an RSA keypair + its public JWK (as an agent would publish)."""
    priv = rsa.generate_private_key(public_exponent=65537, key_size=bits)
    pub = priv.public_key()
    nums = pub.public_numbers()
    jwk = {
        "kty": "RSA",
        "n": _b64u(nums.n.to_bytes((nums.n.bit_length() + 7) // 8, "big")),
        "e": _b64u(nums.e.to_bytes((nums.e.bit_length() + 7) // 8, "big")),
        "use": "enc",
        "alg": "RSA-OAEP-256",
    }
    return priv, jwk
