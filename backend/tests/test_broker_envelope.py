"""
Envelope-encryption tests: a secret sealed to a recipient's published public key
can be opened ONLY by that recipient — safe to pass through an untrusted relay.
"""
import pytest

from app.broker.envelope import (
    SealedSecret,
    generate_recipient_keypair,
    load_rsa_public_from_jwk,
    open_sealed,
    seal_to_recipient,
)


def test_seal_open_roundtrip():
    priv, jwk = generate_recipient_keypair()
    pub = load_rsa_public_from_jwk(jwk)
    secret = b"downstream-api-key-value"
    sealed = seal_to_recipient(secret, pub)
    assert secret not in sealed.to_json().encode()  # ciphertext, not plaintext
    opened = open_sealed(sealed, priv)
    assert opened == secret


def test_wrong_recipient_cannot_open():
    _, jwk = generate_recipient_keypair()
    pub = load_rsa_public_from_jwk(jwk)
    attacker_priv, _ = generate_recipient_keypair()
    sealed = seal_to_recipient(b"top-secret", pub)
    with pytest.raises(Exception):
        open_sealed(sealed, attacker_priv)


def test_relay_sees_only_ciphertext():
    priv, jwk = generate_recipient_keypair()
    pub = load_rsa_public_from_jwk(jwk)
    sealed = seal_to_recipient(b"PLAINTEXT_MARKER_123", pub)
    wire = sealed.to_json()
    assert "PLAINTEXT_MARKER_123" not in wire
    # a relay round-trips the JSON without being able to read it
    round_tripped = SealedSecret.from_json(wire)
    assert open_sealed(round_tripped, priv) == b"PLAINTEXT_MARKER_123"
