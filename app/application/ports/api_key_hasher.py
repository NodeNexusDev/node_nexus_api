"""API-key hashing port."""

from typing import Protocol


class APIKeyHasher(Protocol):
    """Create deterministic non-reversible API-key lookup values."""

    def hash(self, plain_key: str) -> str:
        """Hash one plain API key for persistence or lookup."""
        ...
