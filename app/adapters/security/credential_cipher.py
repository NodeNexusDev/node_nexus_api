"""AES-GCM credential cipher adapter."""

from app.core.security import encrypt
from app.core.ssh_utils import decrypt_value


class AesGcmCredentialCipher:
    """Protect credentials with the configured AES-256-GCM implementation."""

    def encrypt(self, plaintext: str) -> str:
        """Encrypt one plaintext credential."""
        return encrypt(plaintext)

    def decrypt(self, value: str | None) -> str | None:
        """Decrypt encrypted credentials with legacy plaintext compatibility."""
        return decrypt_value(value)
