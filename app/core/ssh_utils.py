"""Shared SSH-related utilities for services."""

import base64
import binascii

from app.core.exceptions import CredentialDecryptionError
from app.core.security import ENCRYPTION_PREFIX, decrypt


def _looks_like_legacy_ciphertext(value: str) -> bool:
    """Return whether an unprefixed value has the legacy ciphertext shape."""
    try:
        raw = base64.b64decode(value, validate=True)
    except (binascii.Error, ValueError):
        return False
    return len(raw) >= 28


def decrypt_value(value: str | None) -> str | None:
    """Decrypt a credential while retaining explicit legacy plaintext support."""
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
