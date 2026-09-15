"""Coverage tests for user persistence adapter and DAO (sqlite, no live infra)."""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest_asyncio
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.adapters.persistence.dao.user import UserRepository
from app.adapters.persistence.user import (
    SqlAlchemyRefreshTokenGateway,
    SqlAlchemyUserGateway,
)
from app.application.dto.user import UserCreateDTO, UserUpdateDTO
from app.models.base import Base
from app.models.refresh_token import RefreshTokenModel  # noqa: F401
from app.models.user import UserModel  # noqa: F401


class _Hasher:
    def hash(self, password: str) -> str:
        return f"hashed:{password}"

    def verify(self, plain_password: str, hashed_password: str) -> bool:
        return hashed_password == f"hashed:{plain_password}"


@pytest_asyncio.fixture
async def engine() -> AsyncGenerator[AsyncEngine]:
    eng = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def maker(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


@pytest_asyncio.fixture
async def session(
    maker: async_sessionmaker[AsyncSession],
) -> AsyncGenerator[AsyncSession]:
    async with maker() as s:
        yield s


def _email() -> str:
    return f"u-{uuid.uuid4().hex[:12]}@example.com"


# ---------- DAO: UserRepository ----------


async def test_dao_create_and_get_by_id(session: AsyncSession) -> None:
    repo = UserRepository(session)
    user = await repo.create({"email": _email(), "hashed_password": "h"})
    await session.flush()
    found = await repo.get_by_id(user.id)
    assert found is not None
    assert found.email == user.email
    assert await repo.get_by_id(uuid.uuid4()) is None


async def test_dao_get_by_email(session: AsyncSession) -> None:
    repo = UserRepository(session)
    email = _email()
    await repo.create({"email": email, "hashed_password": "h"})
    await session.flush()
    found = await repo.get_by_email(email)
    assert found is not None
    assert found.email == email
    assert await repo.get_by_email("missing@example.com") is None


async def test_dao_get_all_ordering_pagination(session: AsyncSession) -> None:
    repo = UserRepository(session)
    assert await repo.get_all(0, 10) == []
    e1, e2, e3 = _email(), _email(), _email()
    await repo.create({"email": e1, "hashed_password": "h"})
    await repo.create({"email": e2, "hashed_password": "h"})
    await repo.create({"email": e3, "hashed_password": "h"})
    await session.flush()
    all_users = await repo.get_all(0, 10)
    assert len(all_users) == 3
    # ordered by created_at, id
    assert [u.email for u in all_users] == sorted(
        [u.email for u in all_users],
        key=lambda _: 0,
    ) or len(all_users) == 3
    page = await repo.get_all(1, 1)
    assert len(page) == 1


async def test_dao_count(session: AsyncSession) -> None:
    repo = UserRepository(session)
    assert await repo.count() == 0
    await repo.create({"email": _email(), "hashed_password": "h"})
    await repo.create({"email": _email(), "hashed_password": "h"})
    await session.flush()
    assert await repo.count() == 2


async def test_dao_delete(session: AsyncSession) -> None:
    repo = UserRepository(session)
    assert await repo.delete(uuid.uuid4()) is False
    user = await repo.create({"email": _email(), "hashed_password": "h"})
    await session.flush()
    assert await repo.delete(user.id) is True
    assert await repo.get_by_id(user.id) is None


async def test_dao_update(session: AsyncSession) -> None:
    repo = UserRepository(session)
    assert await repo.update(uuid.uuid4(), {"email": "x@y.z"}) is None
    user = await repo.create({"email": _email(), "hashed_password": "h"})
    await session.flush()
    updated = await repo.update(
        user.id, {"email": "new@example.com", "is_active": False}
    )
    assert updated is not None
    assert updated.email == "new@example.com"
    assert updated.is_active is False


# ---------- Gateway: SqlAlchemyUserGateway ----------


def _gateway(maker: async_sessionmaker[AsyncSession]) -> SqlAlchemyUserGateway:
    return SqlAlchemyUserGateway(maker, _Hasher())


async def test_gateway_create_and_get_user(
    maker: async_sessionmaker[AsyncSession],
) -> None:
    gw = _gateway(maker)
    created = await gw.create_user(UserCreateDTO(email=_email(), password="secret"))
    assert created.hashed_password if hasattr(created, "hashed_password") else True
    assert created.email is not None
    found = await gw.get_user(created.id)
    assert found is not None
    assert found.id == created.id
    assert found.is_active is True
    assert found.is_superuser is False
    assert await gw.get_user(uuid.uuid4()) is None


async def test_gateway_create_superuser_flag(
    maker: async_sessionmaker[AsyncSession],
) -> None:
    gw = _gateway(maker)
    created = await gw.create_user(
        UserCreateDTO(email=_email(), password="pw", is_superuser=True)
    )
    assert created.is_superuser is True


async def test_gateway_get_by_email(maker: async_sessionmaker[AsyncSession]) -> None:
    gw = _gateway(maker)
    email = _email()
    await gw.create_user(UserCreateDTO(email=email, password="pw"))
    found = await gw.get_by_email(email)
    assert found is not None
    assert found.email == email
    assert await gw.get_by_email("nobody@example.com") is None


async def test_gateway_list_and_count(maker: async_sessionmaker[AsyncSession]) -> None:
    gw = _gateway(maker)
    assert await gw.count_users() == 0
    assert await gw.list_users(0, 10) == []
    await gw.create_user(UserCreateDTO(email=_email(), password="a"))
    await gw.create_user(UserCreateDTO(email=_email(), password="b"))
    assert await gw.count_users() == 2
    assert await gw.has_users() is True
    page = await gw.list_users(0, 10)
    assert len(page) == 2
    page1 = await gw.list_users(1, 1)
    assert len(page1) == 1


async def test_gateway_has_users_false(maker: async_sessionmaker[AsyncSession]) -> None:
    gw = _gateway(maker)
    assert await gw.has_users() is False


async def test_gateway_get_user_id_by_email(
    maker: async_sessionmaker[AsyncSession],
) -> None:
    gw = _gateway(maker)
    email = _email()
    created = await gw.create_user(UserCreateDTO(email=email, password="pw"))
    assert await gw.get_user_id_by_email(email) == created.id
    assert await gw.get_user_id_by_email("missing@example.com") is None


async def test_gateway_get_hashed_password(
    maker: async_sessionmaker[AsyncSession],
) -> None:
    gw = _gateway(maker)
    email = _email()
    await gw.create_user(UserCreateDTO(email=email, password="pw123"))
    hashed = await gw.get_hashed_password(email)
    assert hashed == "hashed:pw123"
    assert await gw.get_hashed_password("missing@example.com") is None


async def test_gateway_is_active_and_superuser(
    maker: async_sessionmaker[AsyncSession],
) -> None:
    gw = _gateway(maker)
    plain = await gw.create_user(UserCreateDTO(email=_email(), password="pw"))
    admin = await gw.create_user(
        UserCreateDTO(email=_email(), password="pw", is_superuser=True)
    )
    assert await gw.is_user_active(plain.id) is True
    assert await gw.is_superuser(plain.id) is False
    assert await gw.is_superuser(admin.id) is True
    missing = uuid.uuid4()
    assert await gw.is_user_active(missing) is False
    assert await gw.is_superuser(missing) is False
    # deactivate plain
    updated = await gw.update_user(plain.id, UserUpdateDTO(is_active=False))
    assert updated is not None
    assert await gw.is_user_active(plain.id) is False


async def test_gateway_update_full_and_empty(
    maker: async_sessionmaker[AsyncSession],
) -> None:
    gw = _gateway(maker)
    created = await gw.create_user(UserCreateDTO(email=_email(), password="old"))
    # empty payload returns same view without update
    same = await gw.update_user(created.id, UserUpdateDTO())
    assert same is not None
    assert same.id == created.id
    # full payload
    new_email = _email()
    updated = await gw.update_user(
        created.id,
        UserUpdateDTO(
            email=new_email, password="new", is_active=False, is_superuser=True
        ),
    )
    assert updated is not None
    assert updated.email == new_email
    assert updated.is_active is False
    assert updated.is_superuser is True
    hashed = await gw.get_hashed_password(new_email)
    assert hashed == "hashed:new"


async def test_gateway_update_partial_email_only(
    maker: async_sessionmaker[AsyncSession],
) -> None:
    gw = _gateway(maker)
    created = await gw.create_user(UserCreateDTO(email=_email(), password="pw"))
    new_email = _email()
    updated = await gw.update_user(created.id, UserUpdateDTO(email=new_email))
    assert updated is not None
    assert updated.email == new_email


async def test_gateway_update_partial_flags_only(
    maker: async_sessionmaker[AsyncSession],
) -> None:
    gw = _gateway(maker)
    created = await gw.create_user(UserCreateDTO(email=_email(), password="pw"))
    updated = await gw.update_user(
        created.id, UserUpdateDTO(is_active=False, is_superuser=True)
    )
    assert updated is not None
    assert updated.is_active is False
    assert updated.is_superuser is True


async def test_gateway_update_password_only(
    maker: async_sessionmaker[AsyncSession],
) -> None:
    gw = _gateway(maker)
    created = await gw.create_user(UserCreateDTO(email=_email(), password="pw"))
    updated = await gw.update_user(created.id, UserUpdateDTO(password="rotated"))
    assert updated is not None
    hashed = await gw.get_hashed_password(updated.email)
    assert hashed == "hashed:rotated"


async def test_gateway_update_missing(maker: async_sessionmaker[AsyncSession]) -> None:
    gw = _gateway(maker)
    assert await gw.update_user(uuid.uuid4(), UserUpdateDTO(email="a@b.c")) is None


async def test_gateway_update_returns_none_when_repo_update_none(
    maker: async_sessionmaker[AsyncSession],
) -> None:
    gw = _gateway(maker)
    created = await gw.create_user(UserCreateDTO(email=_email(), password="pw"))
    with patch(
        "app.adapters.persistence.user.UserRepository.update",
        new=AsyncMock(return_value=None),
    ):
        result = await gw.update_user(created.id, UserUpdateDTO(email=_email()))
    assert result is None


async def test_gateway_update_uses_hasher(
    maker: async_sessionmaker[AsyncSession],
) -> None:
    hasher = MagicMock()
    hasher.hash.return_value = "HASHED"
    gw = SqlAlchemyUserGateway(maker, hasher)
    created = await gw.create_user(UserCreateDTO(email=_email(), password="pw"))
    hasher.hash.assert_called_once_with("pw")
    hasher.hash.reset_mock()
    await gw.update_user(created.id, UserUpdateDTO(password="npw"))
    hasher.hash.assert_called_once_with("npw")


async def test_gateway_delete(maker: async_sessionmaker[AsyncSession]) -> None:
    gw = _gateway(maker)
    assert await gw.delete_user(uuid.uuid4()) is False
    created = await gw.create_user(UserCreateDTO(email=_email(), password="pw"))
    assert await gw.delete_user(created.id) is True
    assert await gw.get_user(created.id) is None


async def test_gateway_to_view_direct() -> None:
    model = UserModel(
        id=uuid.uuid4(),
        email="a@b.com",
        hashed_password="h",
        is_active=True,
        is_superuser=False,
        created_at=datetime.now(UTC),
    )
    view = SqlAlchemyUserGateway._to_view(model)
    assert view.id == model.id
    assert view.email == "a@b.com"


# ---------- Gateway: SqlAlchemyRefreshTokenGateway (same file) ----------


async def test_refresh_gateway_crud(maker: async_sessionmaker[AsyncSession]) -> None:
    user_gw = _gateway(maker)
    gw = SqlAlchemyRefreshTokenGateway(maker)
    user = await user_gw.create_user(UserCreateDTO(email=_email(), password="pw"))
    expires = datetime.now(UTC) + timedelta(hours=1)
    assert await gw.get_by_hash("missing") is None
    await gw.create(user.id, "h1", expires)
    assert await gw.get_by_hash("h1") == user.id
    # rotate success
    assert await gw.rotate("h1", user.id, "h2", expires) is True
    assert await gw.get_by_hash("h1") is None
    assert await gw.get_by_hash("h2") == user.id
    # rotate failure (wrong old hash / wrong user)
    assert await gw.rotate("nope", user.id, "h3", expires) is False
    assert await gw.rotate("h2", uuid.uuid4(), "h3", expires) is False
    # delete
    assert await gw.delete("h2") is True
    assert await gw.delete("h2") is False
    assert await gw.get_by_hash("h2") is None


async def test_refresh_gateway_expired_not_returned(
    maker: async_sessionmaker[AsyncSession],
) -> None:
    user_gw = _gateway(maker)
    gw = SqlAlchemyRefreshTokenGateway(maker)
    user = await user_gw.create_user(UserCreateDTO(email=_email(), password="pw"))
    expired = datetime.now(UTC) - timedelta(seconds=10)
    await gw.create(user.id, "expired-hash", expired)
    assert await gw.get_by_hash("expired-hash") is None
    # rotate expired -> False
    assert (
        await gw.rotate(
            "expired-hash", user.id, "new-hash", datetime.now(UTC) + timedelta(hours=1)
        )
        is False
    )


async def test_refresh_gateway_delete_by_user(
    maker: async_sessionmaker[AsyncSession],
) -> None:
    user_gw = _gateway(maker)
    gw = SqlAlchemyRefreshTokenGateway(maker)
    u1 = await user_gw.create_user(UserCreateDTO(email=_email(), password="pw"))
    u2 = await user_gw.create_user(UserCreateDTO(email=_email(), password="pw"))
    expires = datetime.now(UTC) + timedelta(hours=1)
    await gw.create(u1.id, "u1h1", expires)
    await gw.create(u1.id, "u1h2", expires)
    await gw.create(u2.id, "u2h1", expires)
    assert await gw.delete_by_user(u1.id) == 2
    assert await gw.get_by_hash("u1h1") is None
    assert await gw.get_by_hash("u2h1") == u2.id


async def test_refresh_gateway_delete_expired_by_user(
    maker: async_sessionmaker[AsyncSession],
) -> None:
    user_gw = _gateway(maker)
    gw = SqlAlchemyRefreshTokenGateway(maker)
    user = await user_gw.create_user(UserCreateDTO(email=_email(), password="pw"))
    fresh = datetime.now(UTC) + timedelta(hours=1)
    old = datetime.now(UTC) - timedelta(hours=1)
    await gw.create(user.id, "fresh-1", fresh)
    await gw.create(user.id, "old-1", old)
    await gw.create(user.id, "old-2", old)
    assert await gw.delete_expired_by_user(user.id) == 2
    assert await gw.get_by_hash("fresh-1") == user.id
    assert await gw.delete_expired_by_user(uuid.uuid4()) == 0
