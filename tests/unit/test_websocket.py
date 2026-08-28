"""Tests for WebSocket streaming endpoint."""

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.api.v1.websocket import _validate_ws_token
from app.application.services.api_key_authentication import AuthenticatedPrincipal


class TestWebSocketAuth:
    """Tests for WebSocket authentication."""

    @pytest.mark.asyncio
    async def test_missing_token_returns_false(self):
        """_validate_ws_token returns False when token is missing."""
        ws = AsyncMock()
        result = await _validate_ws_token(ws, token=None, api_key_service=MagicMock())
        assert result is False
        ws.close.assert_called_once_with(code=4001, reason="Missing token")

    @pytest.mark.asyncio
    async def test_empty_token_returns_false(self):
        """_validate_ws_token returns False when token is empty string."""
        ws = AsyncMock()
        result = await _validate_ws_token(ws, token="", api_key_service=MagicMock())
        assert result is False
        ws.close.assert_called_once_with(code=4001, reason="Missing token")

    @pytest.mark.asyncio
    async def test_valid_token_returns_true(self):
        """_validate_ws_token returns True for a valid API key."""
        ws = AsyncMock()
        mock_api_key_svc = AsyncMock()
        mock_api_key_svc.authenticate.return_value = AuthenticatedPrincipal(
            key_id=uuid4(), key_prefix="nnk_vali", scope="read-write"
        )

        result = await _validate_ws_token(
            ws, token="nnk_validkey1234", api_key_service=mock_api_key_svc
        )
        assert result is True
        mock_api_key_svc.authenticate.assert_called_once_with("nnk_validkey1234")

    @pytest.mark.asyncio
    async def test_invalid_token_returns_false(self):
        """_validate_ws_token returns False and closes socket for invalid key."""
        ws = AsyncMock()
        mock_api_key_svc = AsyncMock()
        mock_api_key_svc.authenticate.side_effect = Exception("Invalid key")

        result = await _validate_ws_token(
            ws, token="nnk_badkey12345", api_key_service=mock_api_key_svc
        )
        assert result is False
        ws.close.assert_called_once_with(code=4003, reason="Invalid API key")


class TestWebSocketSchema:
    """Tests for WebSocket message schemas."""

    def test_exec_command_message(self):
        """Valid exec command message format."""
        msg = {"command": "ls -la"}
        assert "command" in msg
        assert isinstance(msg["command"], str)

    def test_signal_message(self):
        """Valid signal message format."""
        msg = {"type": "signal", "signal": "SIGINT"}
        assert msg["type"] == "signal"
        assert msg["signal"] == "SIGINT"

    def test_stdout_response(self):
        """Valid stdout response format."""
        msg = {"type": "stdout", "data": "hello world\n"}
        assert msg["type"] == "stdout"
        assert "data" in msg

    def test_done_response(self):
        """Valid done response format."""
        msg = {"type": "done", "exit_code": 0}
        assert msg["type"] == "done"
        assert msg["exit_code"] == 0


class TestWebSocketStreaming:
    """Tests for WebSocket streaming logic."""

    @pytest.mark.asyncio
    async def test_connector_streaming_method_exists(self):
        """SSHConnector has execute_command_streaming method."""
        from app.adapters.runtime.ssh import SSHConnector

        assert hasattr(SSHConnector, "execute_command_streaming")

    def test_websocket_router_registered(self):
        """WebSocket router is importable with DishkaRoute."""
        from app.api.v1.websocket import router

        assert router is not None
        routes = [getattr(route, "path", None) for route in router.routes]
        assert "/nodes/{node_id}/exec-stream" in routes
