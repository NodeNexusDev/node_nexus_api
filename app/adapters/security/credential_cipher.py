"""AES-GCM credential cipher adapter."""

import base64
import os
from functools import lru_cache

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from app.core.config import get_settings
from app.core.exceptions import CredentialDecryptionError

ENCRYPTION_PREFIX = "enc:v1:"


def _hkdf_derive(secret: str, salt: str) -> bytes:
    hkdf = HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt.encode(),
        info=b"aes-256-gcm",
    )
    return hkdf.derive(secret.encode())


@lru_cache
def _derive_key() -> bytes:
    """Derive current 32-byte AES key from SECRET_KEY via HKDF."""
    settings = get_settings()
    return _hkdf_derive(settings.SECRET_KEY, settings.ENCRYPTION_SALT)


@lru_cache
def _derive_prev_key() -> bytes | None:
    """Derive previous key for rotation, if configured."""
    settings = get_settings()
    if settings.SECRET_KEY_PREV and settings.ENCRYPTION_SALT_PREV:
        return _hkdf_derive(settings.SECRET_KEY_PREV, settings.ENCRYPTION_SALT_PREV)
    if settings.SECRET_KEY_PREV:
        # Salt not rotated, use current salt with prev secret
        return _hkdf_derive(settings.SECRET_KEY_PREV, settings.ENCRYPTION_SALT)
    if settings.ENCRYPTION_SALT_PREV:
        return _hkdf_derive(settings.SECRET_KEY, settings.ENCRYPTION_SALT_PREV)
    return None


def clear_key_cache() -> None:
    """Clear cached derived keys (call after settings reload)."""
    _derive_key.cache_clear()
    _derive_prev_key.cache_clear()


def encrypt(plaintext: str) -> str:
    """Encrypt a string with AES-256-GCM using the current versioned format."""
    nonce = os.urandom(12)
    ciphertext = AESGCM(_derive_key()).encrypt(nonce, plaintext.encode(), None)
    payload = base64.b64encode(nonce + ciphertext).decode()
    return f"{ENCRYPTION_PREFIX}{payload}"


def decrypt(token: str) -> str:
    """Decrypt AES-256-GCM ciphertext (enc:v1:) with rotation fallback."""
    if not token.startswith(ENCRYPTION_PREFIX):
        raise ValueError("Missing encryption prefix")
    payload = token.removeprefix(ENCRYPTION_PREFIX)
    raw = base64.b64decode(payload, validate=True)
    if len(raw) < 28:
        raise ValueError("Encrypted payload is too short")
    nonce, ciphertext = raw[:12], raw[12:]
    try:
        return AESGCM(_derive_key()).decrypt(nonce, ciphertext, None).decode()
    except Exception as primary_exc:
        prev = _derive_prev_key()
        if prev is not None:
            try:
                return AESGCM(prev).decrypt(nonce, ciphertext, None).decode()
            except Exception:
                pass
        raise primary_exc


def decrypt_value(value: str | None) -> str | None:
    """Decrypt credentials — only enc:v1: format is accepted."""
    if not value:
        return value
    if not value.startswith(ENCRYPTION_PREFIX):
        raise CredentialDecryptionError("Credential decryption failed")
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
        """Decrypt encrypted credentials (enc:v1: only)."""
        return decrypt_value(value)
