"""
Cryptographic utilities.

Provides Fernet-based symmetric encryption for sensitive fields
(e.g., MFA secrets, API key references to external services).

Fernet guarantees:
- AES-128-CBC encryption
- HMAC-SHA256 authentication
- Timestamp-based token verification

The encryption key is derived from the application's SECRET_KEY.
"""

from __future__ import annotations

import base64
import hashlib

from cryptography.fernet import Fernet

from src.config import get_settings


def _derive_fernet_key() -> bytes:
    """
    Derive a valid 32-byte Fernet key from the application secret.

    Fernet requires a URL-safe base64-encoded 32-byte key.
    We derive it from SECRET_KEY using SHA-256 to ensure consistent
    key length regardless of the input secret length.
    """
    settings = get_settings()
    # SHA-256 produces 32 bytes, which is exactly what Fernet needs
    raw = hashlib.sha256(settings.secret_key.encode()).digest()
    return base64.urlsafe_b64encode(raw)


def encrypt_value(plaintext: str) -> str:
    """
    Encrypt a string value using Fernet symmetric encryption.

    Returns the encrypted value as a URL-safe base64 string.
    """
    key = _derive_fernet_key()
    f = Fernet(key)
    return f.encrypt(plaintext.encode()).decode()


def decrypt_value(ciphertext: str) -> str:
    """
    Decrypt a Fernet-encrypted string value.

    Raises cryptography.fernet.InvalidToken if the ciphertext
    is invalid or was encrypted with a different key.
    """
    key = _derive_fernet_key()
    f = Fernet(key)
    return f.decrypt(ciphertext.encode()).decode()
