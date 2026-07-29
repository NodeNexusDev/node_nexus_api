"""Encryption utilities for sensitive data at rest."""

import base64
import hashlib
import os
from functools import lru_cache

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from app.core.config import get_settings

ENCRYPTION_PREFIX = "enc:v1:"


def hash_api_key(plain_key: str) -> str:
    """Hash an API key with SHA-256 for storage and lookup."""
    return hashlib.sha256(plain_key.encode()).hexdigest()


@lru_cache
def _derive_key() -> bytes:
    """Derive a 32-byte AES key from SECRET_KEY via HKDF."""
    settings = get_settings()
    hkdf = HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=settings.ENCRYPTION_SALT.encode(),
        info=b"aes-256-gcm",
    )
    return hkdf.derive(settings.SECRET_KEY.encode())


def encrypt(plaintext: str) -> str:
    """Encrypt a string with AES-256-GCM using the current versioned format."""
    key = _derive_key()
    nonce = os.urandom(12)
    aesgcm = AESGCM(key)
    ct = aesgcm.encrypt(nonce, plaintext.encode(), None)
    payload = base64.b64encode(nonce + ct).decode()
    return f"{ENCRYPTION_PREFIX}{payload}"


def decrypt(token: str) -> str:
    """Decrypt current or legacy unprefixed AES-256-GCM ciphertext."""
    key = _derive_key()
    payload = token.removeprefix(ENCRYPTION_PREFIX)
    raw = base64.b64decode(payload, validate=True)
    if len(raw) < 28:
        raise ValueError("Encrypted payload is too short")
    nonce, ct = raw[:12], raw[12:]
    aesgcm = AESGCM(key)
    return aesgcm.decrypt(nonce, ct, None).decode()
