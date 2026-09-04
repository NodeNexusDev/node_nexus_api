"""Coverage tests for new CRUD endpoints added in 2.2.0."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from dishka import Provider, Scope, make_async_container, provide
from dishka.integrations.fastapi import setup_dishka
from fastapi import FastAPI
from httpx2 import ASGITransport, AsyncClient

from app.api.error_mapping import domain_error_handler
from app.application.dto.favorite import FavoriteDTO
from app.application.dto.template_pack import PackViewDTO
from app.application.dto.template_registry import RegistryViewDTO
from app.application.dto.user import UserViewDTO
from app.application.ports.jwt_handler import JWTHandler
from app.application.services.api_key_authentication import APIKeyAuthenticationService
from app.application.services.api_key_management import APIKeyManagementService
from app.application.services.command_management_service import CommandManagementService
from app.application.services.favorite_service import FavoriteService
from app.application.services.script_management_service import ScriptManagementService
from app.application.services.template_pack_service import TemplatePackService
from app.application.services.template_registry_service import TemplateRegistryService
from app.application.services.user_service import UserService
from app.core.exceptions import DomainError, FavoriteNotFoundError


def _mock_jwt(is_superuser: bool = True) -> MagicMock:
    h = MagicMock(spec=JWTHandler)
    h.decode_token.return_value = {
        "sub": str(uuid4()),
        "email": "admin@example.com",
        "is_superuser": is_superuser,
        "type": "access",
    }
    h.hash_token.return_value = "hashed"
    return h


def _favorite_dto(**overrides) -> FavoriteDTO:
    defaults = {
        "id": uuid4(),
        "target_type": "node",
        "target_id": uuid4(),
        "name": "fav",
        "note": "note",
        "created_at": datetime.now(UTC),
    }
    defaults.update(overrides)
    return FavoriteDTO(**defaults)


def _pack_view(**overrides) -> PackViewDTO:
    defaults = {
        "id": uuid4(),
        "registry_id": None,
        "pack_id": "test-pack",
        "name": "Test Pack",
        "description": "desc",
        "version": "1.0.0",
        "author": "author",
        "tags": ("tag1",),
        "manifest_sha": "abc",
        "readme": "readme",
        "installed_version": None,
        "installed_at": None,
        "created_at": datetime.now(UTC),
        "updated_at": datetime.now(UTC),
    }
    defaults.update(overrides)
    return PackViewDTO(**defaults)


def _registry_view(**overrides) -> RegistryViewDTO:
    defaults = {
        "id": uuid4(),
        "owner": "owner",
        "name": "repo",
        "default_branch": "main",
        "last_synced_at": None,
        "created_at": datetime.now(UTC),
        "updated_at": datetime.now(UTC),
    }
    defaults.update(overrides)
    return RegistryViewDTO(**defaults)


def _user_view(**overrides) -> UserViewDTO:
    defaults = {
        "id": uuid4(),
        "email": "test@example.com",
        "is_active": True,
        "is_superuser": False,
        "created_at": datetime.now(UTC),
    }
    defaults.update(overrides)
    return UserViewDTO(**defaults)


# --- Favorites ---
class TestFavoritesNewCRUD:
    def _app(self, mock_fav_service: AsyncMock) -> FastAPI:
        from app.api.v2.favorites import router
        from app.application.services.favorite_service import FavoriteService

        app = FastAPI()
        app.add_exception_handler(DomainError, domain_error_handler)
        app.include_router(router)

        class P(Provider):
            @provide(scope=Scope.REQUEST)
            def get_fav(self) -> FavoriteService:
                from tests.typing import as_typed_mock

                return as_typed_mock(FavoriteService, mock_fav_service)

            @provide(scope=Scope.APP)
            def get_jwt(self) -> JWTHandler:
                from tests.typing import as_typed_mock

                return as_typed_mock(JWTHandler, _mock_jwt())

            @provide(scope=Scope.APP)
            def get_api_key(self) -> APIKeyAuthenticationService:
                from tests.typing import as_typed_mock

                return as_typed_mock(
                    APIKeyAuthenticationService,
                    AsyncMock(spec=APIKeyAuthenticationService),
                )


        c = make_async_container(P())
        setup_dishka(c, app)
        return app

    @patch("app.api.deps.get_settings")
    async def test_get_favorite_success(self, mock_settings):

        mock_settings.return_value = MagicMock(
            MASTER_API_KEY="test", SECRET_KEY="test", ENVIRONMENT="test"
        )
        svc = AsyncMock()
        dto = _favorite_dto()
        svc.get_favorite.return_value = dto
        app = self._app(svc)
        async with AsyncClient(
            transport=ASGITransport(app=app, raise_app_exceptions=False),
            base_url="http://test",
        ) as ac:
            resp = await ac.get(
                f"/favorites/{dto.target_type}/{dto.target_id}",
                headers={"Authorization": "Bearer token"},
            )
        assert resp.status_code == 200
        assert resp.json()["target_type"] == "node"

    @patch("app.api.deps.get_settings")
    async def test_get_favorite_invalid_uuid(self, mock_settings):
        mock_settings.return_value = MagicMock(
            MASTER_API_KEY="test", SECRET_KEY="test", ENVIRONMENT="test"
        )
        svc = AsyncMock()
        app = self._app(svc)
        async with AsyncClient(
            transport=ASGITransport(app=app, raise_app_exceptions=False),
            base_url="http://test",
        ) as ac:
            resp = await ac.get(
                "/favorites/node/not-uuid", headers={"Authorization": "Bearer token"}
            )
        assert resp.status_code == 422

    @patch("app.api.deps.get_settings")
    async def test_patch_favorite_success(self, mock_settings):
        mock_settings.return_value = MagicMock(
            MASTER_API_KEY="test", SECRET_KEY="test", ENVIRONMENT="test"
        )
        svc = AsyncMock()
        dto = _favorite_dto(name="new")
        svc.update_favorite.return_value = dto
        app = self._app(svc)
        tid = dto.target_id
        async with AsyncClient(
            transport=ASGITransport(app=app, raise_app_exceptions=False),
            base_url="http://test",
        ) as ac:
            resp = await ac.patch(
                f"/favorites/node/{tid}",
                json={"name": "new", "note": "n"},
                headers={"Authorization": "Bearer token"},
            )
        assert resp.status_code == 200
        svc.update_favorite.assert_awaited_once()

    @patch("app.api.deps.get_settings")
    async def test_patch_favorite_invalid_uuid(self, mock_settings):
        mock_settings.return_value = MagicMock(
            MASTER_API_KEY="test", SECRET_KEY="test", ENVIRONMENT="test"
        )
        svc = AsyncMock()
        app = self._app(svc)
        async with AsyncClient(
            transport=ASGITransport(app=app, raise_app_exceptions=False),
            base_url="http://test",
        ) as ac:
            resp = await ac.patch(
                "/favorites/node/not-uuid",
                json={"name": "x"},
                headers={"Authorization": "Bearer token"},
            )
        assert resp.status_code == 422

    @patch("app.api.deps.get_settings")
    async def test_get_favorite_not_found(self, mock_settings):
        mock_settings.return_value = MagicMock(
            MASTER_API_KEY="test", SECRET_KEY="test", ENVIRONMENT="test"
        )
        svc = AsyncMock()
        svc.get_favorite.side_effect = FavoriteNotFoundError("not found")
        app = self._app(svc)
        tid = uuid4()
        async with AsyncClient(
            transport=ASGITransport(app=app, raise_app_exceptions=False),
            base_url="http://test",
        ) as ac:
            resp = await ac.get(
                f"/favorites/node/{tid}", headers={"Authorization": "Bearer token"}
            )
        assert resp.status_code == 404

    @patch("app.api.deps.get_settings")
    async def test_list_favorites_remainder(self, mock_settings):
        mock_settings.return_value = MagicMock(
            MASTER_API_KEY="test", SECRET_KEY="test", ENVIRONMENT="test"
        )
        svc = AsyncMock()
        # Mock list_favorites to return items for remainder handling
        dto1 = _favorite_dto()
        dto2 = _favorite_dto()
        svc.list_favorites.return_value = ([dto1, dto2], 2)
        app = self._app(svc)
        # encode offset 5 with limit 20 -> remainder 5, mock returns 2 items  # noqa: E501
        from app.api.pagination import encode_offset

        cursor = encode_offset(0)
        async with AsyncClient(
            transport=ASGITransport(app=app, raise_app_exceptions=False),
            base_url="http://test",
        ) as ac:
            resp = await ac.get(
                f"/favorites/?cursor={cursor}&limit=20",
                headers={"Authorization": "Bearer token"},
            )
        assert resp.status_code == 200


# --- Packs ---
class TestPacksManagement:
    def _app(self, mock_pack: AsyncMock) -> FastAPI:
        from app.api.v2.templates_handlers.packs_handlers.crud_handlers.management import (  # noqa: E501
            router,
        )
        from app.application.services.template_pack_service import TemplatePackService

        app = FastAPI()
        app.add_exception_handler(DomainError, domain_error_handler)
        # Need to include with prefix as real app does: /templates
        app.include_router(router)

        class P(Provider):
            @provide(scope=Scope.REQUEST)
            def get_pack(self) -> TemplatePackService:
                from tests.typing import as_typed_mock

                return as_typed_mock(TemplatePackService, mock_pack)

            @provide(scope=Scope.APP)
            def get_jwt(self) -> JWTHandler:
                from tests.typing import as_typed_mock

                return as_typed_mock(JWTHandler, _mock_jwt())

            @provide(scope=Scope.APP)
            def get_api_key(self) -> APIKeyAuthenticationService:
                from tests.typing import as_typed_mock

                return as_typed_mock(
                    APIKeyAuthenticationService,
                    AsyncMock(spec=APIKeyAuthenticationService),
                )

        c = make_async_container(P())
        setup_dishka(c, app)
        return app

    @patch("app.api.deps.get_settings")
    async def test_patch_pack_success(self, mock_settings):
        mock_settings.return_value = MagicMock(
            MASTER_API_KEY="test", SECRET_KEY="test", ENVIRONMENT="test"
        )
        svc = AsyncMock()
        view = _pack_view(name="new")
        svc.patch_pack.return_value = view
        app = self._app(svc)
        pid = view.id
        async with AsyncClient(
            transport=ASGITransport(app=app, raise_app_exceptions=False),
            base_url="http://test",
        ) as ac:
            resp = await ac.patch(
                f"/packs/{pid}",
                json={"name": "new"},
                headers={"Authorization": "Bearer token"},
            )
        assert resp.status_code == 200
        assert resp.json()["name"] == "new"

    @patch("app.api.deps.get_settings")
    async def test_patch_pack_404(self, mock_settings):
        from app.core.exceptions import PackNotFoundError

        mock_settings.return_value = MagicMock(
            MASTER_API_KEY="test", SECRET_KEY="test", ENVIRONMENT="test"
        )
        svc = AsyncMock()
        svc.patch_pack.side_effect = PackNotFoundError("not found")
        app = self._app(svc)
        async with AsyncClient(
            transport=ASGITransport(app=app, raise_app_exceptions=False),
            base_url="http://test",
        ) as ac:
            resp = await ac.patch(
                f"/packs/{uuid4()}",
                json={"name": "x"},
                headers={"Authorization": "Bearer token"},
            )
        assert resp.status_code == 404

    @patch("app.api.deps.get_settings")
    async def test_delete_pack_success(self, mock_settings):
        mock_settings.return_value = MagicMock(
            MASTER_API_KEY="test", SECRET_KEY="test", ENVIRONMENT="test"
        )
        svc = AsyncMock()
        svc.delete_pack.return_value = None
        app = self._app(svc)
        async with AsyncClient(
            transport=ASGITransport(app=app, raise_app_exceptions=False),
            base_url="http://test",
        ) as ac:
            resp = await ac.delete(
                f"/packs/{uuid4()}", headers={"Authorization": "Bearer token"}
            )
        assert resp.status_code == 204

    @patch("app.api.deps.get_settings")
    async def test_delete_pack_404(self, mock_settings):
        from app.core.exceptions import PackNotFoundError

        mock_settings.return_value = MagicMock(
            MASTER_API_KEY="test", SECRET_KEY="test", ENVIRONMENT="test"
        )
        svc = AsyncMock()
        svc.delete_pack.side_effect = PackNotFoundError("not found")
        app = self._app(svc)
        async with AsyncClient(
            transport=ASGITransport(app=app, raise_app_exceptions=False),
            base_url="http://test",
        ) as ac:
            resp = await ac.delete(
                f"/packs/{uuid4()}", headers={"Authorization": "Bearer token"}
            )
        assert resp.status_code == 404

    @patch("app.api.deps.get_settings")
    async def test_bulk_delete_packs_207(self, mock_settings):
        from app.core.exceptions import PackNotFoundError

        mock_settings.return_value = MagicMock(
            MASTER_API_KEY="test", SECRET_KEY="test", ENVIRONMENT="test"
        )
        svc = AsyncMock()
        ok_id = uuid4()
        fail_id = uuid4()
        svc.delete_pack.side_effect = [None, PackNotFoundError("not found")]
        app = self._app(svc)
        async with AsyncClient(
            transport=ASGITransport(app=app, raise_app_exceptions=False),
            base_url="http://test",
        ) as ac:
            resp = await ac.post(
                "/packs/deletions",
                json={"pack_ids": [str(ok_id), str(fail_id)]},
                headers={"Authorization": "Bearer token"},
            )
        assert resp.status_code == 207
        assert resp.json()["succeeded"] == 1
        assert resp.json()["failed"] == 1

    @patch("app.api.deps.get_settings")
    async def test_bulk_delete_all_success(self, mock_settings):
        mock_settings.return_value = MagicMock(
            MASTER_API_KEY="test", SECRET_KEY="test", ENVIRONMENT="test"
        )
        svc = AsyncMock()
        svc.delete_pack.return_value = None
        app = self._app(svc)
        async with AsyncClient(
            transport=ASGITransport(app=app, raise_app_exceptions=False),
            base_url="http://test",
        ) as ac:
            resp = await ac.post(
                "/packs/deletions",
                json={"pack_ids": [str(uuid4())]},
                headers={"Authorization": "Bearer token"},
            )
        assert resp.status_code == 200


# --- Registries PATCH ---
class TestRegistriesPatch:
    def _app(self, mock_reg: AsyncMock) -> FastAPI:
        from app.api.v2.templates_handlers.registries import router
        from app.application.services.template_registry_service import (
            TemplateRegistryService,
        )

        app = FastAPI()
        app.add_exception_handler(DomainError, domain_error_handler)
        app.include_router(router)

        class P(Provider):
            @provide(scope=Scope.REQUEST)
            def get_reg(self) -> TemplateRegistryService:
                from tests.typing import as_typed_mock

                return as_typed_mock(TemplateRegistryService, mock_reg)

            @provide(scope=Scope.APP)
            def get_jwt(self) -> JWTHandler:
                from tests.typing import as_typed_mock

                return as_typed_mock(JWTHandler, _mock_jwt())

            @provide(scope=Scope.APP)
            def get_api_key(self) -> APIKeyAuthenticationService:
                from tests.typing import as_typed_mock

                return as_typed_mock(
                    APIKeyAuthenticationService,
                    AsyncMock(spec=APIKeyAuthenticationService),
                )

        c = make_async_container(P())
        setup_dishka(c, app)
        return app

    @patch("app.api.deps.get_settings")
    async def test_patch_success(self, mock_settings):
        mock_settings.return_value = MagicMock(
            MASTER_API_KEY="test", SECRET_KEY="test", ENVIRONMENT="test"
        )
        svc = AsyncMock()
        view = _registry_view(owner="newowner")
        svc.patch_registry.return_value = view
        app = self._app(svc)
        rid = view.id
        async with AsyncClient(
            transport=ASGITransport(app=app, raise_app_exceptions=False),
            base_url="http://test",
        ) as ac:
            resp = await ac.patch(
                f"/registries/{rid}",
                json={"owner": "newowner"},
                headers={"Authorization": "Bearer token"},
            )
        assert resp.status_code == 200

    @patch("app.api.deps.get_settings")
    async def test_patch_404(self, mock_settings):
        from app.application.services.template_registry_service import (
            RegistryNotFoundError,
        )

        mock_settings.return_value = MagicMock(
            MASTER_API_KEY="test", SECRET_KEY="test", ENVIRONMENT="test"
        )
        svc = AsyncMock()
        svc.patch_registry.side_effect = RegistryNotFoundError("not found")
        app = self._app(svc)
        async with AsyncClient(
            transport=ASGITransport(app=app, raise_app_exceptions=False),
            base_url="http://test",
        ) as ac:
            resp = await ac.patch(
                f"/registries/{uuid4()}",
                json={"owner": "x"},
                headers={"Authorization": "Bearer token"},
            )
        assert resp.status_code == 404

    @patch("app.api.deps.get_settings")
    async def test_patch_conflict(self, mock_settings):
        from app.application.services.template_registry_service import (
            RegistryConflictError,
        )

        mock_settings.return_value = MagicMock(
            MASTER_API_KEY="test", SECRET_KEY="test", ENVIRONMENT="test"
        )
        svc = AsyncMock()
        svc.patch_registry.side_effect = RegistryConflictError("conflict")
        app = self._app(svc)
        async with AsyncClient(
            transport=ASGITransport(app=app, raise_app_exceptions=False),
            base_url="http://test",
        ) as ac:
            resp = await ac.patch(
                f"/registries/{uuid4()}",
                json={"owner": "x", "name": "y"},
                headers={"Authorization": "Bearer token"},
            )
        assert resp.status_code == 409


# --- Users GET/PATCH ---
class TestUsersNew:
    def _app(self, mock_user: AsyncMock, is_superuser: bool = True) -> FastAPI:
        from app.api.v2.users import router
        from app.application.services.user_service import UserService

        app = FastAPI()
        app.add_exception_handler(DomainError, domain_error_handler)
        app.include_router(router)

        class P(Provider):
            @provide(scope=Scope.REQUEST)
            def get_user(self) -> UserService:
                from tests.typing import as_typed_mock

                return as_typed_mock(UserService, mock_user)

            @provide(scope=Scope.APP)
            def get_jwt(self) -> JWTHandler:
                from tests.typing import as_typed_mock

                return as_typed_mock(JWTHandler, _mock_jwt(is_superuser=is_superuser))

            @provide(scope=Scope.APP)
            def get_api_key(self) -> APIKeyAuthenticationService:
                from tests.typing import as_typed_mock

                return as_typed_mock(
                    APIKeyAuthenticationService,
                    AsyncMock(spec=APIKeyAuthenticationService),
                )

        c = make_async_container(P())
        setup_dishka(c, app)
        return app

    @patch("app.api.deps.get_settings")
    async def test_get_user_success(self, mock_settings):
        mock_settings.return_value = MagicMock(
            MASTER_API_KEY="test", SECRET_KEY="test", ENVIRONMENT="test"
        )
        svc = AsyncMock()
        view = _user_view()
        svc.get_user.return_value = view
        app = self._app(svc)
        async with AsyncClient(
            transport=ASGITransport(app=app, raise_app_exceptions=False),
            base_url="http://test",
        ) as ac:
            resp = await ac.get(
                f"/users/{view.id}", headers={"Authorization": "Bearer token"}
            )
        assert resp.status_code == 200
        assert resp.json()["email"] == "test@example.com"

    @patch("app.api.deps.get_settings")
    async def test_get_user_not_found(self, mock_settings):
        from app.core.exceptions import UserNotFoundError

        mock_settings.return_value = MagicMock(
            MASTER_API_KEY="test", SECRET_KEY="test", ENVIRONMENT="test"
        )
        svc = AsyncMock()
        svc.get_user.side_effect = UserNotFoundError("not found")
        app = self._app(svc)
        async with AsyncClient(
            transport=ASGITransport(app=app, raise_app_exceptions=False),
            base_url="http://test",
        ) as ac:
            resp = await ac.get(
                f"/users/{uuid4()}", headers={"Authorization": "Bearer token"}
            )
        assert resp.status_code == 404

    @patch("app.api.deps.get_settings")
    async def test_patch_user_all_fields(self, mock_settings):
        mock_settings.return_value = MagicMock(
            MASTER_API_KEY="test", SECRET_KEY="test", ENVIRONMENT="test"
        )
        svc = AsyncMock()
        view = _user_view(is_active=False, is_superuser=True, email="new@example.com")
        svc.patch_user.return_value = view
        app = self._app(svc)
        uid = view.id
        async with AsyncClient(
            transport=ASGITransport(app=app, raise_app_exceptions=False),
            base_url="http://test",
        ) as ac:
            resp = await ac.patch(
                f"/users/{uid}",
                json={
                    "email": "new@example.com",
                    "is_active": False,
                    "is_superuser": True,
                    "password": "new-strong-password123",
                },
                headers={"Authorization": "Bearer token"},
            )
        assert resp.status_code == 200

    @patch("app.api.deps.get_settings")
    async def test_patch_user_duplicate_email(self, mock_settings):
        from app.core.exceptions import UserAlreadyExistsError

        mock_settings.return_value = MagicMock(
            MASTER_API_KEY="test", SECRET_KEY="test", ENVIRONMENT="test"
        )
        svc = AsyncMock()
        svc.patch_user.side_effect = UserAlreadyExistsError("dup")
        app = self._app(svc)
        async with AsyncClient(
            transport=ASGITransport(app=app, raise_app_exceptions=False),
            base_url="http://test",
        ) as ac:
            resp = await ac.patch(
                f"/users/{uuid4()}",
                json={"email": "dup@example.com"},
                headers={"Authorization": "Bearer token"},
            )
        assert resp.status_code == 409

    @patch("app.api.deps.get_settings")
    async def test_patch_user_forbidden(self, mock_settings):
        mock_settings.return_value = MagicMock(
            MASTER_API_KEY="test", SECRET_KEY="test", ENVIRONMENT="test"
        )
        svc = AsyncMock()
        app = self._app(svc, is_superuser=False)
        async with AsyncClient(
            transport=ASGITransport(app=app, raise_app_exceptions=False),
            base_url="http://test",
        ) as ac:
            resp = await ac.patch(
                f"/users/{uuid4()}",
                json={"is_active": False},
                headers={"Authorization": "Bearer token"},
            )
        assert resp.status_code == 403


# --- API Keys GET/bulk ---
class TestAPIKeysNew:
    def _app(self, mock_ak: AsyncMock) -> FastAPI:
        from app.api.v2.api_keys import router as ak_router
        from app.application.services.api_key_management import APIKeyManagementService

        app = FastAPI()
        app.add_exception_handler(DomainError, domain_error_handler)
        app.include_router(ak_router)

        class P(Provider):
            @provide(scope=Scope.REQUEST)
            def get_ak(self) -> APIKeyManagementService:
                from tests.typing import as_typed_mock

                return as_typed_mock(APIKeyManagementService, mock_ak)

            @provide(scope=Scope.REQUEST)
            def get_auth(self) -> APIKeyAuthenticationService:
                from tests.typing import as_typed_mock

                return as_typed_mock(
                    APIKeyAuthenticationService,
                    AsyncMock(spec=APIKeyAuthenticationService),
                )

            @provide(scope=Scope.APP)
            def get_jwt(self) -> JWTHandler:
                from tests.typing import as_typed_mock

                return as_typed_mock(JWTHandler, _mock_jwt())

        c = make_async_container(P())
        setup_dishka(c, app)
        return app

    @patch("app.api.deps.get_settings")
    async def test_get_api_key_success(self, mock_settings):
        mock_settings.return_value = MagicMock(
            MASTER_API_KEY="test", SECRET_KEY="test", ENVIRONMENT="test"
        )
        svc = AsyncMock()
        from app.application.dto.api_key import APIKeyViewDTO

        view = APIKeyViewDTO(
            id=uuid4(),
            name="k",
            key_prefix="nnk_",
            is_active=True,
            scope="read-write",
            created_at=datetime.now(UTC),
            last_used_at=None,
            expires_at=None,
        )
        svc.get_api_key.return_value = view
        app = self._app(svc)
        async with AsyncClient(
            transport=ASGITransport(app=app, raise_app_exceptions=False),
            base_url="http://test",
        ) as ac:
            resp = await ac.get(
                f"/api-keys/{view.id}", headers={"X-API-Key": "test-master-key"}
            )
        assert resp.status_code == 200

    @patch("app.api.deps.get_settings")
    async def test_get_api_key_404(self, mock_settings):
        from app.core.exceptions import APIKeyNotFoundError

        mock_settings.return_value = MagicMock(
            MASTER_API_KEY="test", SECRET_KEY="test", ENVIRONMENT="test"
        )
        svc = AsyncMock()
        svc.get_api_key.side_effect = APIKeyNotFoundError("not found")
        app = self._app(svc)
        async with AsyncClient(
            transport=ASGITransport(app=app, raise_app_exceptions=False),
            base_url="http://test",
        ) as ac:
            resp = await ac.get(
                f"/api-keys/{uuid4()}", headers={"X-API-Key": "test-master-key"}
            )
        assert resp.status_code == 404

    @patch("app.api.deps.get_settings")
    async def test_bulk_delete_success(self, mock_settings):
        mock_settings.return_value = MagicMock(
            MASTER_API_KEY="test", SECRET_KEY="test", ENVIRONMENT="test"
        )
        svc = AsyncMock()
        svc.revoke_api_key.return_value = None
        app = self._app(svc)
        async with AsyncClient(
            transport=ASGITransport(app=app, raise_app_exceptions=False),
            base_url="http://test",
        ) as ac:
            resp = await ac.post(
                "/api-keys/deletions",
                json={"key_ids": [str(uuid4())]},
                headers={"X-API-Key": "test-master-key"},
            )
        assert resp.status_code == 200
        assert resp.json()["succeeded"] == 1

    @patch("app.api.deps.get_settings")
    async def test_bulk_delete_207(self, mock_settings):
        from app.core.exceptions import APIKeyNotFoundError

        mock_settings.return_value = MagicMock(
            MASTER_API_KEY="test", SECRET_KEY="test", ENVIRONMENT="test"
        )
        svc = AsyncMock()
        svc.revoke_api_key.side_effect = [None, APIKeyNotFoundError("not found")]
        app = self._app(svc)
        async with AsyncClient(
            transport=ASGITransport(app=app, raise_app_exceptions=False),
            base_url="http://test",
        ) as ac:
            resp = await ac.post(
                "/api-keys/deletions",
                json={"key_ids": [str(uuid4()), str(uuid4())]},
                headers={"X-API-Key": "test-master-key"},
            )
        assert resp.status_code == 207
        assert resp.json()["failed"] == 1


# --- Commands/Scripts bulk ---
class TestCommandsBulk:
    def _app_commands(self, mock_cmd: AsyncMock) -> FastAPI:
        from app.api.v2.commands import router as commands_router
        from app.application.services.command_management_service import (
            CommandManagementService,
        )

        app = FastAPI()
        app.add_exception_handler(DomainError, domain_error_handler)
        app.include_router(commands_router)

        class P(Provider):
            @provide(scope=Scope.REQUEST)
            def get_cmd(self) -> CommandManagementService:
                from tests.typing import as_typed_mock

                return as_typed_mock(CommandManagementService, mock_cmd)

            @provide(scope=Scope.APP)
            def get_jwt(self) -> JWTHandler:
                from tests.typing import as_typed_mock

                return as_typed_mock(JWTHandler, _mock_jwt())

            @provide(scope=Scope.APP)
            def get_api_key(self) -> APIKeyAuthenticationService:
                from tests.typing import as_typed_mock

                return as_typed_mock(
                    APIKeyAuthenticationService,
                    AsyncMock(spec=APIKeyAuthenticationService),
                )

        c = make_async_container(P())
        setup_dishka(c, app)
        return app

    @patch("app.api.deps.get_settings")
    async def test_bulk_update_commands_207(self, mock_settings):
        mock_settings.return_value = MagicMock(
            MASTER_API_KEY="test", SECRET_KEY="test", ENVIRONMENT="test"
        )
        svc = AsyncMock()
        # first success, second fail
        from app.application.dto.command_management import CommandViewDTO
        from app.core.exceptions import CommandNotFoundError

        view = CommandViewDTO(
            id=uuid4(),
            name="n",
            description=None,
            command="echo",
            parameters=(),
            tags=(),
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        svc.update_command.side_effect = [view, CommandNotFoundError("not found")]
        app = self._app_commands(svc)
        cid1, cid2 = uuid4(), uuid4()
        async with AsyncClient(
            transport=ASGITransport(app=app, raise_app_exceptions=False),
            base_url="http://test",
        ) as ac:
            resp = await ac.patch(
                "/commands/",
                json={
                    "updates": [
                        {"id": str(cid1), "changes": {"name": "a"}},
                        {"id": str(cid2), "changes": {"name": "b"}},
                    ]
                },
                headers={"Authorization": "Bearer token"},
            )
        assert resp.status_code == 207
        assert resp.json()["succeeded"] == 1

    @patch("app.api.deps.get_settings")
    async def test_bulk_delete_commands_207(self, mock_settings):
        mock_settings.return_value = MagicMock(
            MASTER_API_KEY="test", SECRET_KEY="test", ENVIRONMENT="test"
        )
        svc = AsyncMock()
        from app.core.exceptions import CommandNotFoundError

        svc.delete_command.side_effect = [None, CommandNotFoundError("not found")]
        app = self._app_commands(svc)
        async with AsyncClient(
            transport=ASGITransport(app=app, raise_app_exceptions=False),
            base_url="http://test",
        ) as ac:
            resp = await ac.post(
                "/commands/deletions",
                json={"ids": [str(uuid4()), str(uuid4())]},
                headers={"Authorization": "Bearer token"},
            )
        assert resp.status_code == 207

    @patch("app.api.deps.get_settings")
    async def test_bulk_update_param_conversion(self, mock_settings):
        mock_settings.return_value = MagicMock(
            MASTER_API_KEY="test", SECRET_KEY="test", ENVIRONMENT="test"
        )
        svc = AsyncMock()
        from app.application.dto.command_management import CommandViewDTO

        view = CommandViewDTO(
            id=uuid4(),
            name="n",
            description=None,
            command="echo hi",
            parameters=(),
            tags=(),
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        svc.update_command.return_value = view
        app = self._app_commands(svc)
        cid = uuid4()
        async with AsyncClient(
            transport=ASGITransport(app=app, raise_app_exceptions=False),
            base_url="http://test",
        ) as ac:
            resp = await ac.patch(
                "/commands/",
                json={
                    "updates": [
                        {
                            "id": str(cid),
                            "changes": {
                                "parameters": [
                                    {"name": "p", "type": "string", "required": True}
                                ],
                                "tags": ["t"],
                            },
                        }
                    ]
                },
                headers={"Authorization": "Bearer token"},
            )
        assert resp.status_code == 200
        # Ensure service called with tuple conversion
        assert svc.update_command.called

    def _app_scripts(self, mock_script: AsyncMock) -> FastAPI:
        from app.api.v2.scripts import router as scripts_router
        from app.application.services.script_management_service import (
            ScriptManagementService,
        )

        app = FastAPI()
        app.add_exception_handler(DomainError, domain_error_handler)
        app.include_router(scripts_router)

        class P(Provider):
            @provide(scope=Scope.REQUEST)
            def get_script(self) -> ScriptManagementService:
                from tests.typing import as_typed_mock

                return as_typed_mock(ScriptManagementService, mock_script)

            @provide(scope=Scope.APP)
            def get_jwt(self) -> JWTHandler:
                from tests.typing import as_typed_mock

                return as_typed_mock(JWTHandler, _mock_jwt())

            @provide(scope=Scope.APP)
            def get_api_key(self) -> APIKeyAuthenticationService:
                from tests.typing import as_typed_mock

                return as_typed_mock(
                    APIKeyAuthenticationService,
                    AsyncMock(spec=APIKeyAuthenticationService),
                )

        c = make_async_container(P())
        setup_dishka(c, app)
        return app

    @patch("app.api.deps.get_settings")
    async def test_bulk_update_scripts_207(self, mock_settings):
        mock_settings.return_value = MagicMock(
            MASTER_API_KEY="test", SECRET_KEY="test", ENVIRONMENT="test"
        )
        svc = AsyncMock()
        from app.application.dto.script_management import ScriptViewDTO
        from app.core.exceptions import ScriptNotFoundError

        view = ScriptViewDTO(
            id=uuid4(),
            name="n",
            description=None,
            steps=(),
            tags=(),
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        svc.update_script.side_effect = [view, ScriptNotFoundError("not found")]
        app = self._app_scripts(svc)
        sid1, sid2 = uuid4(), uuid4()
        async with AsyncClient(
            transport=ASGITransport(app=app, raise_app_exceptions=False),
            base_url="http://test",
        ) as ac:
            resp = await ac.patch(
                "/scripts/",
                json={
                    "updates": [
                        {"id": str(sid1), "changes": {"name": "a"}},
                        {"id": str(sid2), "changes": {"name": "b"}},
                    ]
                },
                headers={"Authorization": "Bearer token"},
            )
        assert resp.status_code == 207

    @patch("app.api.deps.get_settings")
    async def test_bulk_delete_scripts_success(self, mock_settings):
        mock_settings.return_value = MagicMock(
            MASTER_API_KEY="test", SECRET_KEY="test", ENVIRONMENT="test"
        )
        svc = AsyncMock()
        svc.delete_script.return_value = None
        app = self._app_scripts(svc)
        async with AsyncClient(
            transport=ASGITransport(app=app, raise_app_exceptions=False),
            base_url="http://test",
        ) as ac:
            resp = await ac.post(
                "/scripts/deletions",
                json={"ids": [str(uuid4())]},
                headers={"Authorization": "Bearer token"},
            )
        assert resp.status_code == 200
        assert resp.json()["succeeded"] == 1

    @patch("app.api.deps.get_settings")
    async def test_bulk_update_scripts_with_steps(self, mock_settings):
        mock_settings.return_value = MagicMock(
            MASTER_API_KEY="test", SECRET_KEY="test", ENVIRONMENT="test"
        )
        svc = AsyncMock()
        from app.application.dto.script_management import ScriptViewDTO

        view = ScriptViewDTO(
            id=uuid4(),
            name="n",
            description=None,
            steps=(),
            tags=(),
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        svc.update_script.return_value = view
        app = self._app_scripts(svc)
        sid = uuid4()
        async with AsyncClient(
            transport=ASGITransport(app=app, raise_app_exceptions=False),
            base_url="http://test",
        ) as ac:
            resp = await ac.patch(
                "/scripts/",
                json={
                    "updates": [
                        {
                            "id": str(sid),
                            "changes": {
                                "steps": [
                                    {
                                        "label": "Step 1",
                                        "type": "inline",
                                        "command": "echo hi",
                                        "params": {},
                                        "on_failure": "stop",
                                    }
                                ],
                                "tags": ["t"],
                            },
                        }
                    ]
                },
                headers={"Authorization": "Bearer token"},
            )
        assert resp.status_code == 200
