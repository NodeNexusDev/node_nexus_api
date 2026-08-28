"""JWT token port."""

from typing import Protocol

type JWTClaimValue = str | int | bool | float | None
type JWTClaims = dict[str, JWTClaimValue]


class JWTHandler(Protocol):
    """Encode and decode JWT tokens."""

    def encode_access_token(self, user_id: str, email: str, is_superuser: bool) -> str:
        """Encode an access token."""
        ...

    def encode_refresh_token(self, user_id: str) -> str:
        """Encode a refresh token."""
        ...

    def decode_token(self, token: str, expected_type: str) -> JWTClaims:
        """Decode and validate a JWT token."""
        ...

    def hash_token(self, token: str) -> str:
        """Hash a token for storage."""
        ...
