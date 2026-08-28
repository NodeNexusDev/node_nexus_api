"""Tests for split API-key authentication and management use cases."""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.adapters.security import HmacSha256APIKeyHasher
from app.application.dto.api_key import (
    APIKeyAuthDTO,
    APIKeyCreateDTO,
    APIKeyUpdateDTO,
    APIKeyViewDTO,
)
from app.application.services.api_key_authentication import (
    _LAST_USED_UPDATE_INTERVAL,
    APIKeyAuthenticationService,
)
from app.application.services.api_key_management import APIKeyManagementService
from app.core.exceptions import (
    APIKeyExpiredError,
    APIKeyNotFoundError,
    APIKeyRevokedError,
    AuthenticationError,
)


def _auth(**changes: object) -> APIKeyAuthDTO:
    values = {
        "id": uuid4(),
        "key_prefix": "nnk_abcd",
        "is_active": True,
        "scope": "read-write",
        "expires_at": None,
        "last_used_at": None,
        **changes,
    }
    return APIKeyAuthDTO(
        id=values["id"],
        key_prefix=values["key_prefix"],
        is_active=values["is_active"],
        scope=values["scope"],
        expires_at=values["expires_at"],
        last_used_at=values["last_used_at"],
    )


def _view() -> APIKeyViewDTO:
    return APIKeyViewDTO(
        id=uuid4(),
        name="automation",
        key_prefix="nnk_abcd",
        is_active=True,
        scope="read-write",
        created_at=datetime.now(UTC),
        last_used_at=None,
        expires_at=None,
    )


async def test_authentication_returns_principal_and_touches_usage() -> None:
    reader, writer = AsyncMock(), AsyncMock()
    reader.get_auth_by_hash.return_value = _auth()
    service = APIKeyAuthenticationService(reader, writer, HmacSha256APIKeyHasher())

    principal = await service.authenticate("nnk_secret")

    assert principal.key_prefix == "nnk_abcd"
    writer.touch_last_used.assert_awaited_once()


@pytest.mark.parametrize(
    ("record", "error"),
    [
        (None, AuthenticationError),
        (_auth(is_active=False), APIKeyRevokedError),
        (
            _auth(expires_at=datetime.now(UTC) - timedelta(seconds=1)),
            APIKeyExpiredError,
        ),
    ],
)
async def test_authentication_errors_are_distinct(
    record: APIKeyAuthDTO | None, error: type[Exception]
) -> None:
    reader, writer = AsyncMock(), AsyncMock()
    reader.get_auth_by_hash.return_value = record

    with pytest.raises(error):
        await APIKeyAuthenticationService(
            reader,
            writer,
            HmacSha256APIKeyHasher(),
        ).authenticate("invalid")


async def test_management_create_returns_plain_key_once() -> None:
    reader, writer = AsyncMock(), AsyncMock()
    writer.create_api_key.return_value = _view()
    service = APIKeyManagementService(reader, writer, HmacSha256APIKeyHasher())

    result = await service.create_api_key(APIKeyCreateDTO(name="automation"))

    assert result.plain_key.startswith("nnk_")
    assert result.plain_key not in repr(result)


async def test_management_missing_update_and_revoke_use_not_found() -> None:
    reader, writer = AsyncMock(), AsyncMock()
    writer.update_api_key.return_value = None
    writer.revoke_api_key.return_value = False
    service = APIKeyManagementService(reader, writer, HmacSha256APIKeyHasher())

    with pytest.raises(APIKeyNotFoundError):
        await service.update_api_key(uuid4(), APIKeyUpdateDTO(changes=()))
    with pytest.raises(APIKeyNotFoundError):
        await service.revoke_api_key(uuid4())


async def test_auth_skips_touch_when_used_within_interval() -> None:
    """touch_last_used is NOT called when last_used_at is recent."""
    reader, writer = AsyncMock(), AsyncMock()
    recent = datetime.now(UTC) - timedelta(seconds=60)
    reader.get_auth_by_hash.return_value = _auth(last_used_at=recent)

    await APIKeyAuthenticationService(
        reader, writer, HmacSha256APIKeyHasher()
    ).authenticate("nnk_secret")

    writer.touch_last_used.assert_not_awaited()


async def test_auth_calls_touch_when_interval_elapsed() -> None:
    """touch_last_used IS called when last_used_at exceeds the interval."""
    reader, writer = AsyncMock(), AsyncMock()
    old = datetime.now(UTC) - _LAST_USED_UPDATE_INTERVAL - timedelta(seconds=1)
    reader.get_auth_by_hash.return_value = _auth(last_used_at=old)

    await APIKeyAuthenticationService(
        reader, writer, HmacSha256APIKeyHasher()
    ).authenticate("nnk_secret")

    writer.touch_last_used.assert_awaited_once()


async def test_auth_calls_touch_when_last_used_is_none() -> None:
    """touch_last_used IS called on first use (last_used_at is None)."""
    reader, writer = AsyncMock(), AsyncMock()
    reader.get_auth_by_hash.return_value = _auth(last_used_at=None)

    await APIKeyAuthenticationService(
        reader, writer, HmacSha256APIKeyHasher()
    ).authenticate("nnk_secret")

    writer.touch_last_used.assert_awaited_once()
