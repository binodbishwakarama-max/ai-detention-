"""Unit tests for security module."""

from __future__ import annotations

from datetime import timedelta
from uuid import uuid4

import pytest

from src.security import (
    Role,
    TokenType,
    create_access_token,
    create_refresh_token,
    decode_token,
    generate_api_key,
    has_permission,
    hash_api_key,
    hash_password,
    verify_password,
)


class TestPasswordHashing:
    def test_hash_and_verify(self):
        hashed = hash_password("SecurePass123!")
        assert verify_password("SecurePass123!", hashed) is True

    def test_wrong_password_fails(self):
        hashed = hash_password("SecurePass123!")
        assert verify_password("WrongPass!", hashed) is False

    def test_hash_is_not_plaintext(self):
        hashed = hash_password("SecurePass123!")
        assert hashed != "SecurePass123!"
        assert hashed.startswith("$2b$")

    def test_same_password_different_hashes(self):
        """bcrypt uses random salt — same input produces different hashes."""
        h1 = hash_password("Same123!")
        h2 = hash_password("Same123!")
        assert h1 != h2


class TestJWT:
    def test_access_token_roundtrip(self):
        user_id = uuid4()
        org_id = uuid4()
        token = create_access_token(user_id, org_id, Role.ADMIN)
        payload = decode_token(token)

        assert payload["sub"] == str(user_id)
        assert payload["org"] == str(org_id)
        assert payload["role"] == "admin"
        assert payload["type"] == TokenType.ACCESS.value

    def test_refresh_token_roundtrip(self):
        user_id = uuid4()
        org_id = uuid4()
        token = create_refresh_token(user_id, org_id)
        payload = decode_token(token)

        assert payload["sub"] == str(user_id)
        assert payload["type"] == TokenType.REFRESH.value
        assert "role" not in payload  # refresh tokens have minimal claims

    def test_expired_token_raises(self):
        from jose import ExpiredSignatureError

        token = create_access_token(
            uuid4(), uuid4(), Role.ADMIN,
            expires_delta=timedelta(seconds=-1),
        )
        with pytest.raises(ExpiredSignatureError):
            decode_token(token)

    def test_tampered_token_raises(self):
        from jose import JWTError

        token = create_access_token(uuid4(), uuid4(), Role.ADMIN)
        # Flip a character in the signature
        tampered = token[:-1] + ("a" if token[-1] != "a" else "b")
        with pytest.raises(JWTError):
            decode_token(tampered)

    def test_missing_token_raises(self):
        from jose import JWTError

        with pytest.raises(JWTError):
            decode_token("")


class TestApiKeys:
    def test_generate_api_key_format(self):
        raw, key_hash, prefix = generate_api_key()
        assert raw.startswith("ev_")
        assert len(raw) == 43  # "ev_" + 40 hex chars
        assert prefix == raw[:11]
        assert len(key_hash) == 64  # SHA-256 hex

    def test_hash_api_key_deterministic(self):
        raw_key = "ev_abc123def456"
        h1 = hash_api_key(raw_key)
        h2 = hash_api_key(raw_key)
        assert h1 == h2

    def test_different_keys_different_hashes(self):
        _, h1, _ = generate_api_key()
        _, h2, _ = generate_api_key()
        assert h1 != h2


class TestRBAC:
    def test_admin_has_all_permissions(self):
        assert has_permission(Role.ADMIN, Role.ADMIN) is True
        assert has_permission(Role.ADMIN, Role.MEMBER) is True
        assert has_permission(Role.ADMIN, Role.VIEWER) is True

    def test_member_cannot_admin(self):
        assert has_permission(Role.MEMBER, Role.ADMIN) is False
        assert has_permission(Role.MEMBER, Role.MEMBER) is True
        assert has_permission(Role.MEMBER, Role.VIEWER) is True

    def test_viewer_read_only(self):
        assert has_permission(Role.VIEWER, Role.ADMIN) is False
        assert has_permission(Role.VIEWER, Role.MEMBER) is False
        assert has_permission(Role.VIEWER, Role.VIEWER) is True
