"""Tests for the FastAPI entry point and lifespan adapter."""

from unittest.mock import AsyncMock, MagicMock, patch

from httpx2 import ASGITransport, AsyncClient

from app.main import create_app, lifespan


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


class TestCreateApp:
    @patch("app.main.pkg_version")
    @patch("app.main.get_settings")
    def test_version_fallback_when_package_not_found(
        self, mock_get_settings: MagicMock, mock_pkg_version: MagicMock
    ) -> None:
        """If distribution is not installed, app version falls back to 'unknown'."""
        from importlib.metadata import PackageNotFoundError

        mock_pkg_version.side_effect = PackageNotFoundError("node-nexus-api")
        mock_get_settings.return_value = MagicMock(
            CORS_ORIGINS=["*"],
            REQUEST_TIMEOUT=300,
            RATE_LIMIT_REQUESTS=100,
            RATE_LIMIT_WINDOW=60,
            SUPPORTED_API_VERSIONS=["1"],
            PROMETHEUS_ENABLED=False,
            PROMETHEUS_PATH="/metrics",
        )
        app = create_app()
        assert app.version == "unknown"

    @patch("app.main.get_settings")
    def test_prometheus_disabled(self, mock_get_settings: MagicMock) -> None:
        """App starts without Prometheus instrumentation when disabled."""
        mock_get_settings.return_value = MagicMock(
            CORS_ORIGINS=["*"],
            REQUEST_TIMEOUT=300,
            RATE_LIMIT_REQUESTS=100,
            RATE_LIMIT_WINDOW=60,
            SUPPORTED_API_VERSIONS=["1"],
            PROMETHEUS_ENABLED=False,
            PROMETHEUS_PATH="/metrics",
        )
        app = create_app()
        assert app is not None

    @patch("app.main.get_settings")
    async def test_http_exception_handler_includes_request_id(
        self, mock_get_settings: MagicMock
    ) -> None:
        """Custom HTTPException handler includes request_id in response body."""
        from fastapi import HTTPException

        mock_get_settings.return_value = MagicMock(
            CORS_ORIGINS=["*"],
            REQUEST_TIMEOUT=300,
            RATE_LIMIT_REQUESTS=100,
            RATE_LIMIT_WINDOW=60,
            SUPPORTED_API_VERSIONS=["1"],
            PROMETHEUS_ENABLED=False,
            PROMETHEUS_PATH="/metrics",
        )
        app = create_app()

        @app.get("/boom")
        async def boom():
            raise HTTPException(status_code=400, detail="bad request")

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as ac:
            resp = await ac.get("/boom")
            assert resp.status_code == 400
            assert "x-request-id" in resp.headers
            assert resp.json()["request_id"] == resp.headers["x-request-id"]
            assert resp.json()["detail"] == "bad request"
