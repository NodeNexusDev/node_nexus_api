"""Persistence regression tests for atomic refresh-token rotation."""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

from app.adapters.persistence.dao.refresh_token import RefreshTokenRepository
from app.models.refresh_token import RefreshTokenModel


async def test_rotation_consumes_and_replaces_token_in_one_session() -> None:
    user_id = uuid4()
    expires_at = datetime.now(UTC) + timedelta(days=1)
    session = AsyncMock()
    session.add = MagicMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = user_id
    session.execute.return_value = result
    repository = RefreshTokenRepository(session)

    rotated = await repository.rotate(
        "old-token",
        user_id,
        "new-token",
        expires_at,
    )

    assert rotated is True
    statement = session.execute.await_args.args[0]
    sql = str(statement)
    assert sql.startswith("DELETE FROM refresh_tokens")
    assert "RETURNING refresh_tokens.user_id" in sql
    result.close.assert_called_once_with()
    session.add.assert_called_once()
    replacement = session.add.call_args.args[0]
    assert isinstance(replacement, RefreshTokenModel)
    assert replacement.user_id == user_id
    assert replacement.token_hash == "new-token"
    session.flush.assert_awaited_once_with()


async def test_rotation_does_not_issue_replacement_after_token_was_consumed() -> None:
    user_id = uuid4()
    session = AsyncMock()
    session.add = MagicMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = None
    session.execute.return_value = result
    repository = RefreshTokenRepository(session)

    rotated = await repository.rotate(
        "consumed-token",
        user_id,
        "must-not-be-issued",
        datetime.now(UTC) + timedelta(days=1),
    )

    assert rotated is False
    result.close.assert_called_once_with()
    session.add.assert_not_called()
    session.flush.assert_not_awaited()
