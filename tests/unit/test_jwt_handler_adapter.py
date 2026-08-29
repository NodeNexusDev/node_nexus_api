"""Tests for JWTHandlerAdapter."""

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

import jwt
import pytest

from app.adapters.security.jwt_handler import JWTHandlerAdapter
from app.application.ports.jwt_handler import JWTClaims


@pytest.fixture
def mock_settings():
    settings = MagicMock()
    settings.SECRET_KEY = "test-secret-key-32-chars-long-123"
    settings.ACCESS_TOKEN_EXPIRE_MINUTES = 15
    settings.REFRESH_TOKEN_EXPIRE_DAYS = 7
    return settings


@pytest.fixture
def handler(mock_settings):
    with patch(
        "app.adapters.security.jwt_handler.get_settings", return_value=mock_settings
    ):
        yield JWTHandlerAdapter()


class TestEncodeAccessToken:
    def test_encode_access_token(self, handler, mock_settings):
        token = handler.encode_access_token("user-123", "test@example.com", True)
        assert isinstance(token, str)
        payload = jwt.decode(
            token,
            mock_settings.SECRET_KEY,
            algorithms=["HS256"],
            issuer="node-nexus-api",
            options={"verify_exp": False},
        )
        assert payload["sub"] == "user-123"
        assert payload["email"] == "test@example.com"
        assert payload["is_superuser"] is True
        assert payload["type"] == "access"
        assert payload["iss"] == "node-nexus-api"
        assert "exp" in payload
        assert "iat" in payload
        assert "jti" in payload

    def test_encode_access_token_not_superuser(self, handler, mock_settings):
        token = handler.encode_access_token("user-456", "a@b.com", False)
        payload = jwt.decode(
            token,
            mock_settings.SECRET_KEY,
            algorithms=["HS256"],
            issuer="node-nexus-api",
            options={"verify_exp": False},
        )
        assert payload["is_superuser"] is False

    def test_encode_access_token_exp(self, handler, mock_settings):
        with patch("app.adapters.security.jwt_handler.datetime") as mock_dt:
            fixed = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
            mock_dt.now.return_value = fixed
            mock_dt.side_effect = lambda *args, **kw: datetime(*args, **kw)
            # Need to keep UTC
            mock_dt.UTC = UTC
            token = handler.encode_access_token("u", "e@e.com", False)
            payload = jwt.decode(
                token,
                mock_settings.SECRET_KEY,
                algorithms=["HS256"],
                issuer="node-nexus-api",
                options={"verify_exp": False},
            )
            # exp should be fixed + 15 minutes
            exp = datetime.fromtimestamp(payload["exp"], tz=UTC)
            assert exp == fixed + timedelta(minutes=15)


class TestEncodeRefreshToken:
    def test_encode_refresh_token(self, handler, mock_settings):
        token = handler.encode_refresh_token("user-789")
        assert isinstance(token, str)
        payload = jwt.decode(
            token,
            mock_settings.SECRET_KEY,
            algorithms=["HS256"],
            issuer="node-nexus-api",
            options={"verify_exp": False},
        )
        assert payload["sub"] == "user-789"
        assert payload["type"] == "refresh"
        assert payload["iss"] == "node-nexus-api"
        assert "jti" in payload

    def test_encode_refresh_token_exp(self, handler, mock_settings):
        with patch("app.adapters.security.jwt_handler.datetime") as mock_dt:
            fixed = datetime(2026, 1, 1, tzinfo=UTC)
            mock_dt.now.return_value = fixed
            mock_dt.UTC = UTC
            mock_dt.side_effect = lambda *args, **kw: datetime(*args, **kw)
            token = handler.encode_refresh_token("u")
            payload = jwt.decode(
                token,
                mock_settings.SECRET_KEY,
                algorithms=["HS256"],
                issuer="node-nexus-api",
                options={"verify_exp": False},
            )
            exp = datetime.fromtimestamp(payload["exp"], tz=UTC)
            assert exp == fixed + timedelta(days=7)


class TestDecodeToken:
    def test_decode_access_token_success(self, handler, mock_settings):
        token = handler.encode_access_token("uid", "e@e.com", True)
        claims: JWTClaims = handler.decode_token(token, expected_type="access")
        assert claims["sub"] == "uid"
        assert claims["type"] == "access"

    def test_decode_refresh_token_success(self, handler, mock_settings):
        token = handler.encode_refresh_token("uid")
        claims = handler.decode_token(token, expected_type="refresh")
        assert claims["type"] == "refresh"

    def test_decode_wrong_type_raises(self, handler, mock_settings):
        token = handler.encode_access_token("uid", "e@e.com", False)
        with pytest.raises(jwt.InvalidTokenError, match="Expected token type"):
            handler.decode_token(token, expected_type="refresh")

    def test_decode_invalid_signature(self, handler, mock_settings):
        token = handler.encode_access_token("uid", "e@e.com", False)
        # Tamper
        with patch("app.adapters.security.jwt_handler.get_settings") as mock_get:
            mock_get.return_value.SECRET_KEY = "wrong-key-12345678901234567890"
            with pytest.raises(jwt.InvalidTokenError):
                handler.decode_token(token)

    def test_decode_expired(self, handler, mock_settings):
        # Create expired token manually
        now = datetime.now(UTC)
        payload = {
            "sub": "uid",
            "type": "access",
            "exp": now - timedelta(hours=1),
            "iat": now - timedelta(hours=2),
            "jti": "test",
            "iss": "node-nexus-api",
        }
        token = jwt.encode(payload, mock_settings.SECRET_KEY, algorithm="HS256")
        with pytest.raises(jwt.ExpiredSignatureError):
            handler.decode_token(token)

    def test_decode_unsupported_claim_value(self, handler, mock_settings):
        # Create token with unsupported claim type (e.g., list)
        now = datetime.now(UTC)
        payload = {
            "sub": "uid",
            "type": "access",
            "exp": now + timedelta(hours=1),
            "iat": now,
            "jti": "test",
            "iss": "node-nexus-api",
            "bad": [
                "unsupported"
            ],  # list is JsonValue but our check only allows str|int|float|bool|None
        }
        token = jwt.encode(payload, mock_settings.SECRET_KEY, algorithm="HS256")
        with pytest.raises(jwt.InvalidTokenError, match="unsupported claim"):
            handler.decode_token(token)

    def test_decode_invalid_key_type(self, handler, mock_settings):
        now = datetime.now(UTC)
        payload = {
            "sub": "uid",
            "type": "access",
            "exp": now + timedelta(hours=1),
            "iat": now,
            "jti": "test",
            "iss": "node-nexus-api",
        }
        token = jwt.encode(payload, mock_settings.SECRET_KEY, algorithm="HS256")
        # Manually craft decode to have non-str key
        with patch(
            "app.adapters.security.jwt_handler.jwt.decode", return_value={123: "bad"}
        ):
            with pytest.raises(jwt.InvalidTokenError, match="unsupported claim"):
                handler.decode_token(token)

    def test_decode_type_missing(self, handler, mock_settings):
        now = datetime.now(UTC)
        payload = {
            "sub": "uid",
            "exp": now + timedelta(hours=1),
            "iat": now,
            "jti": "test",
            "iss": "node-nexus-api",
        }
        token = jwt.encode(payload, mock_settings.SECRET_KEY, algorithm="HS256")
        with pytest.raises(jwt.InvalidTokenError, match="Expected token type"):
            handler.decode_token(token)


class TestHashToken:
    def test_hash_token(self, handler):
        hashed = handler.hash_token("my-token")
        import hashlib

        expected = hashlib.sha256(b"my-token").hexdigest()
        assert hashed == expected
        assert len(hashed) == 64

    def test_hash_token_different(self, handler):
        assert handler.hash_token("a") != handler.hash_token("b")

    def test_hash_empty(self, handler):
        assert handler.hash_token("") == handler.hash_token("")
