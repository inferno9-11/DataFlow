from datetime import timedelta

import pytest

from app.core.errors import AuthenticationError
from app.core.security import (
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)


def test_password_hashing_and_verification():
    raw_pass = "ProductionGradeSecret2026!"
    hashed = hash_password(raw_pass)

    assert hashed != raw_pass
    assert hashed.startswith("$argon2id$")
    assert verify_password(raw_pass, hashed) is True
    assert verify_password("WrongPassword!", hashed) is False


def test_password_too_short():
    with pytest.raises(ValueError, match="at least 8 characters"):
        hash_password("short")


def test_jwt_token_generation_and_decoding():
    subject_id = "123e4567-e89b-12d3-a456-426614174000"
    role = "admin"

    token = create_access_token(subject=subject_id, role=role)
    assert isinstance(token, str)

    payload = decode_access_token(token)
    assert payload["sub"] == subject_id
    assert payload["role"] == role
    assert payload["type"] == "access"
    assert "exp" in payload


def test_expired_jwt_token_rejection():
    subject_id = "123e4567-e89b-12d3-a456-426614174000"
    # Token expired 1 hour ago
    token = create_access_token(subject=subject_id, expires_delta=timedelta(hours=-1))

    with pytest.raises(AuthenticationError, match="Token has expired"):
        decode_access_token(token)


def test_tampered_jwt_token_rejection():
    token = create_access_token(subject="user1")
    tampered = token[:-5] + "AAAAA"

    with pytest.raises(AuthenticationError, match="Invalid or corrupted token"):
        decode_access_token(tampered)
