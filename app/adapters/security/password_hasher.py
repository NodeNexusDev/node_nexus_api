"""Password hashing adapter using bcrypt."""

import bcrypt


class PasswordHasherAdapter:
    """Password hasher implementation using bcrypt."""

    def hash(self, password: str) -> str:
        """Hash a password using bcrypt."""
        return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

    def verify(self, plain_password: str, hashed_password: str) -> bool:
        """Verify a password against a bcrypt hash."""
        return bcrypt.checkpw(plain_password.encode(), hashed_password.encode())
