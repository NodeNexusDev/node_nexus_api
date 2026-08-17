"""HMAC-SHA-256 API-key hashing adapter."""

import hashlib
import hmac

from app.core.config import get_settings


class HmacSha256APIKeyHasher:
    """Create HMAC-SHA-256 lookup hashes for API keys using SECRET_KEY."""

    def hash(self, plain_key: str) -> str:
        """Hash one plain API key with HMAC-SHA-256."""
        settings = get_settings()
        return hmac.new(
            settings.SECRET_KEY.encode(),
            plain_key.encode(),
            hashlib.sha256,
        ).hexdigest()
