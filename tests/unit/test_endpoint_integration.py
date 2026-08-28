"""Tests for @inject endpoints with dishka mocks."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

from dishka import Provider, Scope, make_async_container
from dishka.integrations.fastapi import setup_dishka
from fastapi import FastAPI
from httpx2 import ASGITransport, AsyncClient, Response

from app.api.v1 import (
    commands,
    favorites,
    notes,
    scripts,
    search,
)
from app.application.dto.command_management import CommandViewDTO
from app.application.dto.execution_stats import ExecutionStatsDTO
from app.application.dto.favorite import FavoriteDTO
from app.application.dto.global_search import GlobalSearchResultDTO
from app.application.dto.note import NoteDTO
from app.application.dto.script_management import ScriptViewDTO
from app.application.ports.jwt_handler import JWTHandler
from app.application.services.api_key_authentication import (
    APIKeyAuthenticationService,
)
from app.application.services.command_management_service import (
    CommandManagementService,
)
from app.application.services.execution_stats_service import ExecutionStatsService
from app.application.services.favorite_service import FavoriteService
from app.application.services.global_search_service import GlobalSearchService
from app.application.services.note_service import NoteService
from app.application.services.script_management_service import (
    ScriptManagementService,
)


async def _noop_auth(*a, **kw):  # noqa: ANN001, ANN002, ANN003
    return "test"


_MODULE_IMPORTS: dict[str, list[str]] = {
    "app.api.v1.commands": ["get_current_principal", "require_write_or_jwt_scope"],
    "app.api.v1.events": ["get_current_principal"],
    "app.api.v1.favorites": ["get_current_principal", "require_write_or_jwt_scope"],
    "app.api.v1.notes": ["get_current_principal", "require_write_or_jwt_scope"],
    "app.api.v1.scripts": ["get_current_principal", "require_write_or_jwt_scope"],
    "app.api.v1.search": ["get_current_principal"],
    "app.api.v1.nodes": ["get_current_principal", "require_write_or_jwt_scope"],
}


def _patch_auth():
    """Patch all auth deps at every module level where they're imported."""
    patches = []
    for mod, attrs in _MODULE_IMPORTS.items():
        for attr in attrs:
            patches.append(patch(f"{mod}.{attr}", _noop_auth))
    for p in patches:
        p.start()
    return patches


def _stop_patches(patches):
    for p in patches:
        p.stop()


def _build_app_with_service(service_type, service_mock):
    """Build a test app with dishka container providing one mock service + auth."""
    app = FastAPI()

    class P(Provider):
        pass

    p = P()
    p.provide(lambda: service_mock, provides=service_type, scope=Scope.REQUEST)

    auth_mock = AsyncMock(spec=APIKeyAuthenticationService)
    p.provide(
        lambda: auth_mock,
        provides=APIKeyAuthenticationService,
        scope=Scope.REQUEST,
    )
    p.provide(
        lambda: MagicMock(spec=JWTHandler),
        provides=JWTHandler,
        scope=Scope.REQUEST,
    )

    container = make_async_container(p)
    setup_dishka(container, app)
    return app


async def _request(app: FastAPI, method: str, path: str, **kwargs) -> Response:
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        return await client.request(method, path, **kwargs)


class TestNoteEndpoints:
    async def test_list(self) -> None:
        mock_svc = AsyncMock(spec=NoteService)
        mock_svc.list_notes.return_value = []

        app = _build_app_with_service(NoteService, mock_svc)
        app.include_router(notes.router)

        patches = _patch_auth()
        try:
            resp = await _request(
                app,
                "GET",
                f"/notes/command/{uuid.uuid4()}",
                headers={"X-API-Key": "test"},
            )
        finally:
            _stop_patches(patches)
        assert resp.status_code == 200

    async def test_create(self) -> None:
        mock_svc = AsyncMock(spec=NoteService)
        target_id = uuid.uuid4()
        mock_svc.create_note.return_value = NoteDTO(
            id=uuid.uuid4(),
            target_type="command",
            target_id=target_id,
            content="note",
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )

        app = _build_app_with_service(NoteService, mock_svc)
        app.include_router(notes.router)

        patches = _patch_auth()
        try:
            resp = await _request(
                app,
                "POST",
                f"/notes/command/{target_id}",
                json={
                    "target_type": "command",
                    "target_id": str(target_id),
                    "content": "note",
                },
                headers={"X-API-Key": "test"},
            )
        finally:
            _stop_patches(patches)
        assert resp.status_code == 201
        assert resp.json()["content"] == "note"

    async def test_update(self) -> None:
        mock_svc = AsyncMock(spec=NoteService)
        mock_svc.update_note.return_value = NoteDTO(
            id=uuid.uuid4(),
            target_type="command",
            target_id=uuid.uuid4(),
            content="updated",
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )

        app = _build_app_with_service(NoteService, mock_svc)
        app.include_router(notes.router)

        patches = _patch_auth()
        try:
            resp = await _request(
                app,
                "PUT",
                f"/notes/{uuid.uuid4()}",
                json={"content": "updated"},
                headers={"X-API-Key": "test"},
            )
        finally:
            _stop_patches(patches)
        assert resp.status_code == 200
        assert resp.json()["content"] == "updated"

    async def test_delete(self) -> None:
        mock_svc = AsyncMock(spec=NoteService)
        mock_svc.delete_note.return_value = True

        app = _build_app_with_service(NoteService, mock_svc)
        app.include_router(notes.router)

        patches = _patch_auth()
        try:
            resp = await _request(
                app,
                "DELETE",
                f"/notes/{uuid.uuid4()}",
                headers={"X-API-Key": "test"},
            )
        finally:
            _stop_patches(patches)
        assert resp.status_code == 204


class TestFavoriteEndpoints:
    async def test_list(self) -> None:
        mock_svc = AsyncMock(spec=FavoriteService)
        mock_svc.list_favorites.return_value = ([], 0)

        app = _build_app_with_service(FavoriteService, mock_svc)
        app.include_router(favorites.router)

        patches = _patch_auth()
        try:
            resp = await _request(
                app, "GET", "/favorites", headers={"X-API-Key": "test"}
            )
        finally:
            _stop_patches(patches)
        assert resp.status_code == 200

    async def test_add(self) -> None:
        mock_svc = AsyncMock(spec=FavoriteService)
        mock_svc.add_favorite.return_value = FavoriteDTO(
            id=uuid.uuid4(),
            target_type="command",
            target_id=uuid.uuid4(),
            name=None,
            note=None,
            created_at=datetime.now(UTC),
        )

        app = _build_app_with_service(FavoriteService, mock_svc)
        app.include_router(favorites.router)

        patches = _patch_auth()
        try:
            resp = await _request(
                app,
                "POST",
                "/favorites",
                json={"target_type": "command", "target_id": str(uuid.uuid4())},
                headers={"X-API-Key": "test"},
            )
        finally:
            _stop_patches(patches)
        assert resp.status_code == 201

    async def test_remove(self) -> None:
        mock_svc = AsyncMock(spec=FavoriteService)
        mock_svc.remove_favorite.return_value = True

        app = _build_app_with_service(FavoriteService, mock_svc)
        app.include_router(favorites.router)

        patches = _patch_auth()
        try:
            resp = await _request(
                app,
                "DELETE",
                f"/favorites/command/{uuid.uuid4()}",
                headers={"X-API-Key": "test"},
            )
        finally:
            _stop_patches(patches)
        assert resp.status_code == 204


class TestSearchEndpoint:
    async def test_search(self) -> None:
        mock_svc = AsyncMock(spec=GlobalSearchService)
        mock_svc.search.return_value = GlobalSearchResultDTO(
            nodes=(),
            commands=(),
            scripts=(),
            tags=("web",),
        )

        app = _build_app_with_service(GlobalSearchService, mock_svc)
        app.include_router(search.router)

        patches = _patch_auth()
        try:
            resp = await _request(
                app, "GET", "/search?q=web", headers={"X-API-Key": "test"}
            )
        finally:
            _stop_patches(patches)
        assert resp.status_code == 200
        assert resp.json()["tags"] == ["web"]


class TestCommandEndpoints:
    async def test_stats(self) -> None:
        mock_svc = AsyncMock(spec=ExecutionStatsService)
        mock_svc.get_command_stats.return_value = ExecutionStatsDTO(
            total=10,
            successful=8,
            failed=2,
            success_rate=0.8,
            avg_duration_ms=100,
            min_duration_ms=50,
            max_duration_ms=200,
            last_executed_at=datetime.now(UTC),
        )

        app = _build_app_with_service(ExecutionStatsService, mock_svc)
        app.include_router(commands.router)

        patches = _patch_auth()
        try:
            resp = await _request(
                app,
                "GET",
                f"/commands/{uuid.uuid4()}/stats",
                headers={"X-API-Key": "test"},
            )
        finally:
            _stop_patches(patches)
        assert resp.status_code == 200
        assert resp.json()["total"] == 10

    async def test_clone(self) -> None:
        mock_svc = AsyncMock(spec=CommandManagementService)
        mock_svc.clone_command.return_value = CommandViewDTO(
            id=uuid.uuid4(),
            name="copy",
            description=None,
            command="echo ok",
            parameters=(),
            tags=(),
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )

        app = _build_app_with_service(CommandManagementService, mock_svc)
        app.include_router(commands.router)

        patches = _patch_auth()
        try:
            resp = await _request(
                app,
                "POST",
                f"/commands/{uuid.uuid4()}/clone",
                headers={"X-API-Key": "test"},
            )
        finally:
            _stop_patches(patches)
        assert resp.status_code == 200
        assert resp.json()["name"] == "copy"


class TestScriptEndpoints:
    async def test_clone(self) -> None:
        mock_svc = AsyncMock(spec=ScriptManagementService)
        mock_svc.clone_script.return_value = ScriptViewDTO(
            id=uuid.uuid4(),
            name="copy",
            description=None,
            steps=(),
            tags=(),
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )

        app = _build_app_with_service(ScriptManagementService, mock_svc)
        app.include_router(scripts.router)

        patches = _patch_auth()
        try:
            resp = await _request(
                app,
                "POST",
                f"/scripts/{uuid.uuid4()}/clone",
                headers={"X-API-Key": "test"},
            )
        finally:
            _stop_patches(patches)
        assert resp.status_code == 200
        assert resp.json()["name"] == "copy"


class TestEventsEndpoint:
    def test_stream_imports(self) -> None:
        """Verify the event_stream endpoint module loads and router exists."""
        from app.api.v1.events import router as events_router

        assert any(
            getattr(route, "path", None) == "/events/stream"
            for route in events_router.routes
        )
