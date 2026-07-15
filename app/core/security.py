"""Encryption utilities for sensitive data at rest."""

import base64
import os
from functools import lru_cache

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from app.core.config import get_settings


@lru_cache
def _derive_key() -> bytes:
    """Derive a 32-byte AES key from SECRET_KEY via HKDF."""
    settings = get_settings()
    hkdf = HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=b"node-nexus-ssh-v1",
        info=b"aes-256-gcm",
    )
    return hkdf.derive(settings.SECRET_KEY.encode())


def encrypt(plaintext: str) -> str:
    """Encrypt a string with AES-256-GCM. Returns base64(nonce:ciphertext:tag)."""
    key = _derive_key()
    nonce = os.urandom(12)
    aesgcm = AESGCM(key)
    ct = aesgcm.encrypt(nonce, plaintext.encode(), None)
    return base64.b64encode(nonce + ct).decode()


def decrypt(token: str) -> str:
    """Decrypt a string encrypted with `encrypt`."""
    key = _derive_key()
    raw = base64.b64decode(token)
    nonce, ct = raw[:12], raw[12:]
    aesgcm = AESGCM(key)
    return aesgcm.decrypt(nonce, ct, None).decode()
