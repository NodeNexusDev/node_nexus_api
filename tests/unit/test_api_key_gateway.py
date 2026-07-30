"""Unit tests for the API-key persistence adapter mappings."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

from app.adapters.persistence.api_key import SqlAlchemyAPIKeyGateway
from app.application.dto.api_key import APIKeyPersistenceDTO, APIKeyUpdateDTO
from app.models.api_key import APIKeyModel


class _Context:
    def __init__(self, session: AsyncMock) -> None:
        self._session = session

    async def __aenter__(self) -> AsyncMock:
        return self._session

    async def __aexit__(self, *args: object) -> None:
        return None


class _Sessionmaker:
    def __init__(self, session: AsyncMock) -> None:
        self._session = session

    def __call__(self) -> _Context:
        return _Context(self._session)

    def begin(self) -> _Context:
        return _Context(self._session)


def _result(
    *,
    scalar: object = None,
    scalars: list[object] | None = None,
    count: int = 0,
) -> MagicMock:
    result = MagicMock()
    result.scalar_one_or_none.return_value = scalar
    result.scalar_one.return_value = count
    result.scalars.return_value = scalars or []
    return result


def _model() -> APIKeyModel:
    return APIKeyModel(
        id=uuid4(),
        name="automation",
        key_hash="sensitive",
        key_prefix="nnk_abcd",
        scope="read-write",
        is_active=True,
        created_at=datetime.now(UTC),
    )


def test_maps_auth_projection_without_hash() -> None:
    model = APIKeyModel(
        id=uuid4(),
        name="automation",
        key_hash="sensitive",
        key_prefix="nnk_abcd",
        scope="read-only",
        is_active=True,
        created_at=datetime.now(UTC),
    )

    auth = SqlAlchemyAPIKeyGateway._to_auth(model)

    assert auth.id == model.id
    assert auth.key_prefix == "nnk_abcd"
    assert not hasattr(auth, "key_hash")


def test_maps_management_view_without_hash() -> None:
    model = APIKeyModel(
        id=uuid4(),
        name="automation",
        key_hash="sensitive",
        key_prefix="nnk_abcd",
        scope="read-write",
        is_active=True,
        created_at=datetime.now(UTC),
    )

    view = SqlAlchemyAPIKeyGateway._to_view(model)

    assert view.name == "automation"
    assert not hasattr(view, "key_hash")


async def test_reads_auth_and_management_views() -> None:
    model = _model()
    session = AsyncMock()
    session.execute.side_effect = [_result(scalar=model), _result(scalar=model)]
    gateway = SqlAlchemyAPIKeyGateway(_Sessionmaker(session))  # type: ignore[arg-type]

    auth = await gateway.get_auth_by_hash(model.key_hash)
    view = await gateway.get_api_key(model.id)

    assert auth is not None and auth.id == model.id
    assert view is not None and view.name == model.name


async def test_reads_return_none_for_missing_keys() -> None:
    session = AsyncMock()
    session.execute.return_value = _result()
    gateway = SqlAlchemyAPIKeyGateway(_Sessionmaker(session))  # type: ignore[arg-type]

    assert await gateway.get_auth_by_hash("missing") is None
    assert await gateway.get_api_key(uuid4()) is None


async def test_lists_api_keys_with_total() -> None:
    models = [_model(), _model()]
    session = AsyncMock()
    session.execute.side_effect = [_result(count=2), _result(scalars=models)]
    gateway = SqlAlchemyAPIKeyGateway(_Sessionmaker(session))  # type: ignore[arg-type]

    page = await gateway.list_api_keys(offset=5, limit=10)

    assert page.total == 2
    assert tuple(item.id for item in page.items) == tuple(model.id for model in models)


async def test_creates_updates_and_revokes_key() -> None:
    created_at = datetime.now(UTC)
    session = AsyncMock()
    session.add = MagicMock(
        side_effect=lambda model: (
            setattr(model, "id", uuid4()),
            setattr(model, "created_at", created_at),
            setattr(model, "is_active", True),
        )
    )
    existing = _model()
    session.execute.side_effect = [
        _result(scalar=existing),
        _result(scalar=existing),
    ]
    gateway = SqlAlchemyAPIKeyGateway(_Sessionmaker(session))  # type: ignore[arg-type]

    created = await gateway.create_api_key(
        APIKeyPersistenceDTO(
            name="created",
            key_hash="hash",
            key_prefix="nnk_new",
            scope="read-only",
        )
    )
    updated = await gateway.update_api_key(
        existing.id,
        APIKeyUpdateDTO(changes=(("name", "renamed"),)),
    )
    revoked = await gateway.revoke_api_key(existing.id)

    assert created.name == "created"
    assert updated is not None and updated.name == "renamed"
    assert revoked is True
    assert existing.is_active is False


async def test_update_and_revoke_return_missing() -> None:
    session = AsyncMock()
    session.execute.return_value = _result()
    gateway = SqlAlchemyAPIKeyGateway(_Sessionmaker(session))  # type: ignore[arg-type]

    assert await gateway.update_api_key(uuid4(), APIKeyUpdateDTO(changes=())) is None
    assert await gateway.revoke_api_key(uuid4()) is False


async def test_touch_last_used_executes_short_update() -> None:
    session = AsyncMock()
    gateway = SqlAlchemyAPIKeyGateway(_Sessionmaker(session))  # type: ignore[arg-type]

    await gateway.touch_last_used(uuid4(), datetime.now(UTC))

    session.execute.assert_awaited_once()
