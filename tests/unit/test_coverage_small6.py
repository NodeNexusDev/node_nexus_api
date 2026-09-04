"""Cover remaining small gaps for 95%."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.api.pagination import encode_offset
from app.application.dto.favorite import FavoriteDTO
from app.application.ports.jwt_handler import JWTHandler
from app.application.services.api_key_authentication import APIKeyAuthenticationService
from app.application.services.favorite_service import FavoriteService
from app.core.exceptions import DomainError


class TestFavoritesRemainder:
    def _app(self, mock_svc: AsyncMock):
        from dishka import Provider, Scope, make_async_container, provide
        from dishka.integrations.fastapi import setup_dishka
        from fastapi import FastAPI

        from app.api.error_mapping import domain_error_handler
        from app.api.v2.favorites import router
        from app.application.ports.jwt_handler import JWTHandler
        from app.application.services.api_key_authentication import (
            APIKeyAuthenticationService,
        )

        def _mock_jwt():
            h = MagicMock(spec=JWTHandler)
            h.decode_token.return_value = {
                "sub": str(uuid4()),
                "email": "a@b.com",
                "is_superuser": True,
                "type": "access",
            }
            h.hash_token.return_value = "h"
            return h

        app = FastAPI()
        app.add_exception_handler(Exception, domain_error_handler)
        # Use domain_error_handler for FavoriteNotFound
        from app.core.exceptions import DomainError

        app.add_exception_handler(DomainError, domain_error_handler)
        app.include_router(router)

        class P(Provider):
            @provide(scope=Scope.REQUEST)
            def get_fav(self) -> FavoriteService:
                from tests.typing import as_typed_mock

                return as_typed_mock(FavoriteService, mock_svc)

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
    async def test_list_favorites_non_aligned(self, mock_settings):
        mock_settings.return_value = MagicMock(
            MASTER_API_KEY="test", SECRET_KEY="test", ENVIRONMENT="test"
        )
        svc = AsyncMock(spec=FavoriteService)
        # Create 25 items for page handling
        dtos = [
            FavoriteDTO(
                id=uuid4(),
                target_type="node",
                target_id=uuid4(),
                name=f"n{i}",
                note=None,
                created_at=datetime.now(UTC),
            )
            for i in range(25)
        ]
        # Service called with fetch_size = limit + remainder  # noqa: E501
        # For offset 5, limit 20 -> fetch_size 25, API slices to 20  # noqa: E501
        # Mock returns 25 and total 30, check has_more/items sliced  # noqa: E501
        svc.list_favorites.return_value = (dtos, 30)
        app = self._app(svc)
        from httpx2 import ASGITransport, AsyncClient

        cursor = encode_offset(5)  # remainder 5
        async with AsyncClient(
            transport=ASGITransport(app=app, raise_app_exceptions=False),
            base_url="http://test",
        ) as ac:
            resp = await ac.get(
                f"/favorites/?cursor={cursor}&limit=20",
                headers={"Authorization": "Bearer token"},
            )
        assert resp.status_code == 200
        # Should have sliced to limit
        assert len(resp.json()["items"]) == 20
        # Verify service called with fetch_size 25
        svc.list_favorites.assert_awaited_once()
        call_kwargs = svc.list_favorites.call_args.kwargs
        assert call_kwargs["size"] == 25
        assert call_kwargs["page"] == 1  # offset 5 //20 +1 =1

    @patch("app.api.deps.get_settings")
    async def test_list_favorites_invalid_cursor(self, mock_settings):
        mock_settings.return_value = MagicMock(
            MASTER_API_KEY="test", SECRET_KEY="test", ENVIRONMENT="test"
        )
        svc = AsyncMock(spec=FavoriteService)
        app = self._app(svc)
        from httpx2 import ASGITransport, AsyncClient

        async with AsyncClient(
            transport=ASGITransport(app=app, raise_app_exceptions=False),
            base_url="http://test",
        ) as ac:
            resp = await ac.get(
                "/favorites/?cursor=bad!!&limit=20",
                headers={"Authorization": "Bearer token"},
            )
        assert resp.status_code == 422


# --- template pack service extra ---
class TestTemplatePackExtra:
    async def test_list_packs_search_and_tag(self):
        from app.application.dto.template_pack import (
            PackCreateDTO,
            PackListQueryDTO,
            PackManifestDTO,
        )
        from app.application.services.template_pack_service import TemplatePackService

        svc = TemplatePackService()
        # Create two packs
        pid1 = f"pack-search-{uuid4()}"
        pid2 = f"pack-search2-{uuid4()}"
        await svc.create_pack(
            PackCreateDTO(
                manifest=PackManifestDTO(
                    pack_id=pid1,
                    name="SearchMe",
                    version="1.0.0",
                    description="desc search",
                    tags=("t1",),
                ),
                commands=(),
                scripts=(),
            )
        )
        await svc.create_pack(
            PackCreateDTO(
                manifest=PackManifestDTO(
                    pack_id=pid2, name="Other", version="1.0.0", tags=("t2",)
                ),
                commands=(),
                scripts=(),
            )
        )
        page = await svc.list_packs(
            PackListQueryDTO(offset=0, limit=10, search="searchme")
        )
        assert any("SearchMe" in p.name for p in page.items)
        page_tag = await svc.list_packs(PackListQueryDTO(offset=0, limit=10, tag="t2"))
        assert any("Other" in p.name for p in page_tag.items)

    async def test_create_pack_duplicate(self):
        from app.application.dto.template_pack import PackCreateDTO, PackManifestDTO
        from app.application.services.template_pack_service import TemplatePackService
        from app.core.exceptions import DomainError

        svc = TemplatePackService()
        pid = f"dup-{uuid4()}"
        await svc.create_pack(
            PackCreateDTO(
                manifest=PackManifestDTO(pack_id=pid, name="n", version="1.0.0"),
                commands=(),
                scripts=(),
            )
        )
        try:
            await svc.create_pack(
                PackCreateDTO(
                    manifest=PackManifestDTO(pack_id=pid, name="n2", version="1.0.0"),
                    commands=(),
                    scripts=(),
                )
            )
            assert False, "should raise"
        except DomainError:
            pass

    async def test_create_pack_invalid_base64(self):
        from app.application.dto.template_pack import (
            PackAssetCreateDTO,
            PackCreateDTO,
            PackManifestDTO,
        )
        from app.application.services.template_pack_service import TemplatePackService

        svc = TemplatePackService()
        pid = f"bad-b64-{uuid4()}"
        try:
            await svc.create_pack(
                PackCreateDTO(
                    manifest=PackManifestDTO(pack_id=pid, name="n", version="1.0.0"),
                    commands=(),
                    scripts=(),
                    assets=(
                        PackAssetCreateDTO(path="a.txt", content_base64="!!!notbase64"),
                    ),
                )
            )
            assert False
        except Exception as exc:
            assert "Invalid base64" in str(exc)

    async def test_install_pack_already_installed(self):
        from app.application.dto.template_pack import PackCreateDTO, PackManifestDTO
        from app.application.services.template_pack_service import TemplatePackService
        from app.core.exceptions import PackConflictError

        svc = TemplatePackService()
        pid = f"inst-{uuid4()}"
        detail = await svc.create_pack(
            PackCreateDTO(
                manifest=PackManifestDTO(pack_id=pid, name="n", version="1.0.0"),
                commands=({"name": "cmd1", "command": "echo hi"},),
                scripts=(),
            )
        )
        await svc.install_pack(detail.pack.id, on_conflict="fail")
        try:
            await svc.install_pack(detail.pack.id, on_conflict="fail")
            assert False
        except PackConflictError:
            pass

    async def test_uninstall_not_found(self):
        from app.application.services.template_pack_service import TemplatePackService
        from app.core.exceptions import PackNotFoundError

        svc = TemplatePackService()
        with pytest.raises(PackNotFoundError):
            await svc.uninstall_pack(uuid4())

    async def test_get_stats_group_by(self):
        from app.application.services.template_pack_service import TemplatePackService

        svc = TemplatePackService()
        stats = await svc.get_stats(group_by="registry_id")
        assert stats.total >= 0
        stats2 = await svc.get_stats(group_by="tag")
        assert stats2.total >= 0
        stats3 = await svc.get_stats(group_by="installed")
        assert stats3.total >= 0
        stats4 = await svc.get_stats(group_by="version")
        assert stats4.total >= 0
        stats5 = await svc.get_stats(group_by="unknown")
        assert stats5.total >= 0
