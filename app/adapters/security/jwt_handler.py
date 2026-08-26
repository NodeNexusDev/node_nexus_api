"""JWT token handler adapter."""

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

import jwt

from app.core.config import get_settings


class JWTHandlerAdapter:
    """JWT handler implementation using PyJWT."""

    def encode_access_token(self, user_id: str, email: str, is_superuser: bool) -> str:
        """Encode an access token with user claims."""
        settings = get_settings()
        now = datetime.now(UTC)
        payload = {
            "sub": user_id,
            "email": email,
            "is_superuser": is_superuser,
            "type": "access",
            "exp": now + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
            "iat": now,
            "jti": str(uuid4()),
            "iss": "node-nexus-api",
        }
        return jwt.encode(payload, settings.SECRET_KEY, algorithm="HS256")

    def encode_refresh_token(self, user_id: str) -> str:
        """Encode a refresh token."""
        settings = get_settings()
        now = datetime.now(UTC)
        payload = {
            "sub": user_id,
            "type": "refresh",
            "exp": now + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
            "iat": now,
            "jti": str(uuid4()),
            "iss": "node-nexus-api",
        }
        return jwt.encode(payload, settings.SECRET_KEY, algorithm="HS256")

    def decode_token(self, token: str, expected_type: str = "access") -> dict[str, Any]:
        """Decode and validate a JWT token.

        Raises:
            jwt.ExpiredSignatureError: Token has expired.
            jwt.DecodeError: Invalid token format or signature.
            jwt.InvalidTokenError: General token validation error.
        """
        settings = get_settings()
        payload = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=["HS256"],
            issuer="node-nexus-api",
        )
        if payload.get("type") != expected_type:
            msg = f"Expected token type '{expected_type}', got '{payload.get('type')}'"
            raise jwt.InvalidTokenError(msg)
        return payload

    def hash_token(self, token: str) -> str:
        """Hash a token using SHA-256 for storage."""
        import hashlib

        return hashlib.sha256(token.encode()).hexdigest()
