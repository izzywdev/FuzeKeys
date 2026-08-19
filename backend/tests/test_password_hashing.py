"""Regression tests for password hashing.

These exist because the backend shipped with `passlib[bcrypt]==1.7.4` and an
unpinned `bcrypt`. passlib 1.7.4 is its final release and probes the bcrypt
backend at import time in a way bcrypt >= 4.1 rejects, so once bcrypt 5.x
started resolving, every hash_password() call raised ValueError -- taking down
user registration, login, and the CI "Set up test environment" step, which calls
init_database(). Nothing in the suite exercised hashing, so it went unnoticed.
"""

import pytest

from app.utils.encryption import hash_password, verify_password


def test_hash_password_produces_a_bcrypt_hash():
    """The bcrypt backend must actually load and hash."""
    hashed = hash_password("correct horse battery staple")
    assert hashed.startswith("$2"), f"not a bcrypt hash: {hashed[:8]!r}"
    assert hashed != "correct horse battery staple"


def test_verify_password_round_trip():
    hashed = hash_password("demo123")
    assert verify_password("demo123", hashed) is True
    assert verify_password("not-the-password", hashed) is False


def test_hashes_are_salted():
    """Two hashes of the same password must differ."""
    assert hash_password("same-password") != hash_password("same-password")


@pytest.mark.parametrize(
    "password",
    [
        "short",
        "a" * 64,
        "unicode-påsswörd-🔐",
    ],
)
def test_hash_password_handles_representative_inputs(password):
    assert verify_password(password, hash_password(password)) is True
