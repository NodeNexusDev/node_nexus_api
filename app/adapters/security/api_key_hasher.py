"""SHA-256 API-key hashing adapter."""

import hashlib


class Sha256APIKeyHasher:
    """Create stable SHA-256 lookup hashes for API keys."""

    def hash(self, plain_key: str) -> str:
        """Hash one plain API key."""
        return hashlib.sha256(plain_key.encode()).hexdigest()
