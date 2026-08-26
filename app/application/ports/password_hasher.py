"""Password hashing port."""

from typing import Protocol


class PasswordHasher(Protocol):
    """Hash and verify passwords."""

    def hash(self, password: str) -> str:
        """Hash a password."""
        ...

    def verify(self, plain_password: str, hashed_password: str) -> bool:
        """Verify a password against a hash."""
        ...
