"""Credential encryption port."""

from typing import Protocol


class CredentialCipher(Protocol):
    """Protect and restore credentials at infrastructure boundaries."""

    def encrypt(self, plaintext: str) -> str:
        """Encrypt one plaintext credential."""
        ...

    def decrypt(self, value: str | None) -> str | None:
        """Decrypt one stored credential when needed."""
        ...
