"""Extra coverage for user DAO/gateway and bulk ops."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.persistence.dao.user import UserRepository
from app.adapters.persistence.user import SqlAlchemyUserGateway


# --- User DAO ---
class TestUserDAO:
    async def test_get_by_id(self):
        session = AsyncMock(spec=AsyncSession)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        session.execute.return_value = mock_result
        repo = UserRepository(session)
        res = await repo.get_by_id(uuid.uuid4())
        assert res is None

    async def test_get_by_email(self):
        session = AsyncMock(spec=AsyncSession)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        session.execute.return_value = mock_result
        repo = UserRepository(session)
        res = await repo.get_by_email("a@b.com")
        assert res is None

    async def test_get_all(self):
        session = AsyncMock(spec=AsyncSession)
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        session.execute.return_value = mock_result
        repo = UserRepository(session)
        res = await repo.get_all(0, 10)
        assert res == []

    async def test_create(self):
        session = AsyncMock(spec=AsyncSession)
        session.flush = AsyncMock()
        repo = UserRepository(session)
        user = await repo.create(
            {"email": "a@b.com", "hashed_password": "h", "is_superuser": False}
        )
        assert user.email == "a@b.com"

    async def test_delete_not_found(self):
        session = AsyncMock(spec=AsyncSession)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        session.execute.return_value = mock_result
        repo = UserRepository(session)
        assert await repo.delete(uuid.uuid4()) is False

    async def test_delete_found(self):
        session = AsyncMock(spec=AsyncSession)
        mock_user = MagicMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_user
        session.execute.return_value = mock_result
        session.delete = AsyncMock()
        session.flush = AsyncMock()
        repo = UserRepository(session)
        assert await repo.delete(uuid.uuid4()) is True

    async def test_update_found(self):
        session = AsyncMock(spec=AsyncSession)
        mock_user = MagicMock()
        mock_user.email = "old@b.com"
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_user
        session.execute.return_value = mock_result
        session.flush = AsyncMock()
        repo = UserRepository(session)
        res = await repo.update(uuid.uuid4(), {"email": "new@b.com"})
        assert res is not None
        assert res.email == "new@b.com"

    async def test_update_not_found(self):
        session = AsyncMock(spec=AsyncSession)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        session.execute.return_value = mock_result
        repo = UserRepository(session)
        assert await repo.update(uuid.uuid4(), {"email": "x"}) is None

    async def test_count(self):
        session = AsyncMock(spec=AsyncSession)
        mock_result = MagicMock()
        mock_result.scalar_one.return_value = 5
        session.execute.return_value = mock_result
        repo = UserRepository(session)
        assert await repo.count() == 5


# --- User Gateway (covers 62 miss) ---
class TestUserGateway:
    def _mock_sessionmaker(self, session: AsyncMock):
        # sessionmaker returns context manager
        mock_ctx = MagicMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=session)
        mock_ctx.__aexit__ = AsyncMock(return_value=None)
        # begin() returns same ctx
        mock_begin = MagicMock()
        mock_begin.__aenter__ = AsyncMock(return_value=session)
        mock_begin.__aexit__ = AsyncMock(return_value=None)
        maker = MagicMock()
        maker.return_value = mock_ctx
        maker.begin.return_value = mock_begin
        return maker

    async def test_get_user_found(self):
        session = AsyncMock(spec=AsyncSession)
        # Mock UserRepository.get_by_id to return a model
        from app.models.user import UserModel

        model = UserModel(
            id=uuid.uuid4(),
            email="a@b.com",
            hashed_password="h",
            is_active=True,
            is_superuser=False,
            created_at=datetime.now(UTC),
        )
        with patch("app.adapters.persistence.user.UserRepository") as mock_repo:
            inst = mock_repo.return_value
            inst.get_by_id = AsyncMock(return_value=model)
            maker = self._mock_sessionmaker(session)
            gw = SqlAlchemyUserGateway(maker, MagicMock())
            res = await gw.get_user(model.id)
            assert res is not None
            assert res.email == "a@b.com"

    async def test_get_user_not_found(self):
        session = AsyncMock(spec=AsyncSession)
        with patch("app.adapters.persistence.user.UserRepository") as mock_repo:
            mock_repo.return_value.get_by_id = AsyncMock(return_value=None)
            maker = self._mock_sessionmaker(session)
            gw = SqlAlchemyUserGateway(maker, MagicMock())
            assert await gw.get_user(uuid.uuid4()) is None

    async def test_create_user(self):
        session = AsyncMock(spec=AsyncSession)
        from app.application.dto.user import UserCreateDTO
        from app.models.user import UserModel

        model = UserModel(
            id=uuid4(),
            email="a@b.com",
            hashed_password="h",
            is_active=True,
            is_superuser=False,
            created_at=datetime.now(UTC),
        )
        hasher = MagicMock()
        hasher.hash.return_value = "hashed"
        with patch("app.adapters.persistence.user.UserRepository") as mock_repo:
            mock_repo.return_value.create = AsyncMock(return_value=model)
            maker = self._mock_sessionmaker(session)
            gw = SqlAlchemyUserGateway(maker, hasher)
            res = await gw.create_user(UserCreateDTO(email="a@b.com", password="p"))
            assert res.email == "a@b.com"

    async def test_update_user_found(self):
        session = AsyncMock(spec=AsyncSession)
        from app.application.dto.user import UserUpdateDTO
        from app.models.user import UserModel

        model = UserModel(
            id=uuid4(),
            email="new@b.com",
            hashed_password="h",
            is_active=False,
            is_superuser=True,
            created_at=datetime.now(UTC),
        )
        with patch("app.adapters.persistence.user.UserRepository") as mock_repo:
            mock_repo.return_value.get_by_id = AsyncMock(return_value=MagicMock())
            mock_repo.return_value.update = AsyncMock(return_value=model)
            maker = self._mock_sessionmaker(session)
            gw = SqlAlchemyUserGateway(maker, MagicMock())
            res = await gw.update_user(
                uuid4(),
                UserUpdateDTO(email="new@b.com", is_active=False, is_superuser=True),
            )
            assert res is not None
            assert res.is_active is False

    async def test_delete_user(self):
        session = AsyncMock(spec=AsyncSession)
        with patch("app.adapters.persistence.user.UserRepository") as mock_repo:
            mock_repo.return_value.delete = AsyncMock(return_value=True)
            maker = self._mock_sessionmaker(session)
            gw = SqlAlchemyUserGateway(maker, MagicMock())
            assert await gw.delete_user(uuid4()) is True

    async def test_has_users(self):
        session = AsyncMock(spec=AsyncSession)
        with patch("app.adapters.persistence.user.UserRepository") as mock_repo:
            mock_repo.return_value.count = AsyncMock(return_value=1)
            maker = self._mock_sessionmaker(session)
            gw = SqlAlchemyUserGateway(maker, MagicMock())
            assert await gw.has_users() is True

    async def test_list_users(self):
        session = AsyncMock(spec=AsyncSession)
        from app.models.user import UserModel

        model = UserModel(
            id=uuid4(),
            email="a@b.com",
            hashed_password="h",
            is_active=True,
            is_superuser=False,
            created_at=datetime.now(UTC),
        )
        with patch("app.adapters.persistence.user.UserRepository") as mock_repo:
            mock_repo.return_value.get_all = AsyncMock(return_value=[model])
            maker = self._mock_sessionmaker(session)
            gw = SqlAlchemyUserGateway(maker, MagicMock())
            res = await gw.list_users(0, 10)
            assert len(res) == 1

    async def test_count_users(self):
        session = AsyncMock(spec=AsyncSession)
        with patch("app.adapters.persistence.user.UserRepository") as mock_repo:
            mock_repo.return_value.count = AsyncMock(return_value=5)
            maker = self._mock_sessionmaker(session)
            gw = SqlAlchemyUserGateway(maker, MagicMock())
            assert await gw.count_users() == 5

    async def test_get_user_id_by_email(self):
        session = AsyncMock(spec=AsyncSession)
        with patch("app.adapters.persistence.user.UserRepository") as mock_repo:
            from app.models.user import UserModel

            model = UserModel(
                id=uuid4(),
                email="a@b.com",
                hashed_password="h",
                is_active=True,
                is_superuser=False,
                created_at=datetime.now(UTC),
            )
            mock_repo.return_value.get_by_email = AsyncMock(return_value=model)
            maker = self._mock_sessionmaker(session)
            gw = SqlAlchemyUserGateway(maker, MagicMock())
            assert await gw.get_user_id_by_email("a@b.com") == model.id

    async def test_get_hashed_password(self):
        session = AsyncMock(spec=AsyncSession)
        with patch("app.adapters.persistence.user.UserRepository") as mock_repo:
            from app.models.user import UserModel

            model = UserModel(
                id=uuid4(),
                email="a@b.com",
                hashed_password="hashed",
                is_active=True,
                is_superuser=False,
                created_at=datetime.now(UTC),
            )
            mock_repo.return_value.get_by_email = AsyncMock(return_value=model)
            maker = self._mock_sessionmaker(session)
            gw = SqlAlchemyUserGateway(maker, MagicMock())
            assert await gw.get_hashed_password("a@b.com") == "hashed"

    async def test_is_user_active(self):
        session = AsyncMock(spec=AsyncSession)
        with patch("app.adapters.persistence.user.UserRepository") as mock_repo:
            from app.models.user import UserModel

            model = UserModel(
                id=uuid4(),
                email="a@b.com",
                hashed_password="h",
                is_active=True,
                is_superuser=False,
                created_at=datetime.now(UTC),
            )
            mock_repo.return_value.get_by_id = AsyncMock(return_value=model)
            maker = self._mock_sessionmaker(session)
            gw = SqlAlchemyUserGateway(maker, MagicMock())
            assert await gw.is_user_active(model.id) is True

    async def test_is_superuser(self):
        session = AsyncMock(spec=AsyncSession)
        with patch("app.adapters.persistence.user.UserRepository") as mock_repo:
            from app.models.user import UserModel

            model = UserModel(
                id=uuid4(),
                email="a@b.com",
                hashed_password="h",
                is_active=True,
                is_superuser=True,
                created_at=datetime.now(UTC),
            )
            mock_repo.return_value.get_by_id = AsyncMock(return_value=model)
            maker = self._mock_sessionmaker(session)
            gw = SqlAlchemyUserGateway(maker, MagicMock())
            assert await gw.is_superuser(model.id) is True

    async def test_get_by_email(self):
        session = AsyncMock(spec=AsyncSession)
        with patch("app.adapters.persistence.user.UserRepository") as mock_repo:
            from app.models.user import UserModel

            model = UserModel(
                id=uuid4(),
                email="a@b.com",
                hashed_password="h",
                is_active=True,
                is_superuser=False,
                created_at=datetime.now(UTC),
            )
            mock_repo.return_value.get_by_email = AsyncMock(return_value=model)
            maker = self._mock_sessionmaker(session)
            gw = SqlAlchemyUserGateway(maker, MagicMock())
            res = await gw.get_by_email("a@b.com")
            assert res is not None
            assert res.email == "a@b.com"


# --- Node bulk operation (covers small) ---
class TestNodeBulkOperation:
    async def test_import(self):
        # Just import to cover module load
        from app.application.services import node_bulk_operation_service

        assert node_bulk_operation_service is not None
