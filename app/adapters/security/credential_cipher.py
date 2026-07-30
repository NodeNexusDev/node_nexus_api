"""AES-GCM credential cipher adapter."""

import base64
import binascii
import os
from functools import lru_cache

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from app.core.config import get_settings
from app.core.exceptions import CredentialDecryptionError

ENCRYPTION_PREFIX = "enc:v1:"


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
    nonce = os.urandom(12)
    ciphertext = AESGCM(_derive_key()).encrypt(nonce, plaintext.encode(), None)
    payload = base64.b64encode(nonce + ciphertext).decode()
    return f"{ENCRYPTION_PREFIX}{payload}"


def decrypt(token: str) -> str:
    """Decrypt current or legacy unprefixed AES-256-GCM ciphertext."""
    payload = token.removeprefix(ENCRYPTION_PREFIX)
    raw = base64.b64decode(payload, validate=True)
    if len(raw) < 28:
        raise ValueError("Encrypted payload is too short")
    nonce, ciphertext = raw[:12], raw[12:]
    return AESGCM(_derive_key()).decrypt(nonce, ciphertext, None).decode()


def _looks_like_legacy_ciphertext(value: str) -> bool:
    try:
        raw = base64.b64decode(value, validate=True)
    except (binascii.Error, ValueError):
        return False
    return len(raw) >= 28


def decrypt_value(value: str | None) -> str | None:
    """Decrypt credentials while retaining legacy plaintext support."""
    if not value:
        return value
    encrypted = value.startswith(ENCRYPTION_PREFIX) or _looks_like_legacy_ciphertext(
        value
    )
    if not encrypted:
        return value
    try:
        return decrypt(value)
    except (ValueError, UnicodeDecodeError) as exc:
        raise CredentialDecryptionError("Credential decryption failed") from exc
    except Exception as exc:
        raise CredentialDecryptionError("Credential decryption failed") from exc


class AesGcmCredentialCipher:
    """Protect credentials with the configured AES-256-GCM implementation."""

    def encrypt(self, plaintext: str) -> str:
        """Encrypt one plaintext credential."""
        return encrypt(plaintext)

    def decrypt(self, value: str | None) -> str | None:
        """Decrypt encrypted credentials with legacy plaintext compatibility."""
        return decrypt_value(value)
