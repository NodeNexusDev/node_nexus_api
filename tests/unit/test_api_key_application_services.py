"""Tests for split API-key authentication and management use cases."""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.application.dto.api_key import (
    APIKeyAuthDTO,
    APIKeyCreateDTO,
    APIKeyUpdateDTO,
    APIKeyViewDTO,
)
from app.application.services.api_key_authentication import (
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
    return APIKeyAuthDTO(**values)  # type: ignore[arg-type]


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
    service = APIKeyAuthenticationService(reader, writer)

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
        await APIKeyAuthenticationService(reader, writer).authenticate("invalid")


async def test_management_create_returns_plain_key_once() -> None:
    reader, writer = AsyncMock(), AsyncMock()
    writer.create_api_key.return_value = _view()
    service = APIKeyManagementService(reader, writer)

    result = await service.create_api_key(APIKeyCreateDTO(name="automation"))

    assert result.plain_key.startswith("nnk_")
    assert result.plain_key not in repr(result)


async def test_management_missing_update_and_revoke_use_not_found() -> None:
    reader, writer = AsyncMock(), AsyncMock()
    writer.update_api_key.return_value = None
    writer.revoke_api_key.return_value = False
    service = APIKeyManagementService(reader, writer)

    with pytest.raises(APIKeyNotFoundError):
        await service.update_api_key(uuid4(), APIKeyUpdateDTO(changes=()))
    with pytest.raises(APIKeyNotFoundError):
        await service.revoke_api_key(uuid4())
