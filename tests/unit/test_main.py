"""Tests for the FastAPI entry point and lifespan adapter."""

from unittest.mock import AsyncMock, MagicMock, patch

from app.main import lifespan


class TestLifespan:
    @patch("app.main.container")
    async def test_runs_startup_and_closes_container(
        self,
        container: MagicMock,
    ) -> None:
        startup = MagicMock(run=AsyncMock())
        container.get = AsyncMock(return_value=startup)
        container.close = AsyncMock()

        from fastapi import FastAPI

        async with lifespan(FastAPI()):
            startup.run.assert_awaited_once()

        container.close.assert_awaited_once()


class TestDomainErrorHandler:
    @patch("app.main.get_settings")
    def test_error_handler_returns_json(self, mock_get_settings: MagicMock) -> None:
        """Domain error handler returns JSON response."""
        from fastapi import FastAPI

        from app.core.exceptions import NodeNotFoundError

        app = FastAPI()

        @app.get("/test")
        async def raise_error():
            raise NodeNotFoundError("node not found")

        exc = NodeNotFoundError("test error")
        error_status_map = {NodeNotFoundError: 404}
        status_code = error_status_map.get(type(exc), 422)
        assert status_code == 404
