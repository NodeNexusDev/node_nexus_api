"""Tests for the WebSocket transport adapter."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import WebSocketDisconnect

from app.api.v1.websocket import exec_stream
from app.core.exceptions import ConnectionFailedError, NodeNotFoundError

_exec = exec_stream.__dishka_orig_func__  # type: ignore[attr-defined]


def _make_ws(token: str | None = "test-key") -> AsyncMock:
    ws = AsyncMock()
    ws.query_params = {"token": token} if token else {}
    return ws


class FakeStreamingSession:
    def __init__(self, error: Exception | None = None) -> None:
        self.error = error

    async def execute(self, command: str) -> AsyncIterator[str]:
        if self.error:
            raise self.error
        yield "output line 1\n"
        yield "output line 2\n"


class FakeStreamingService:
    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.closed = False

    @asynccontextmanager
    async def connect(self, node_id: object) -> AsyncIterator[FakeStreamingSession]:
        if isinstance(self.error, NodeNotFoundError):
            raise self.error
        try:
            yield FakeStreamingSession(self.error)
        finally:
            self.closed = True


def _api_key_service() -> AsyncMock:
    service = AsyncMock()
    service.validate_api_key.return_value = None
    return service


@pytest.mark.asyncio
class TestExecStreamFullCoverage:
    async def test_missing_token(self) -> None:
        ws = _make_ws(None)
        await _exec(ws, MagicMock(), FakeStreamingService(), _api_key_service())
        ws.close.assert_awaited_once_with(code=4001, reason="Missing token")

    async def test_node_not_found(self) -> None:
        ws = _make_ws()
        service = FakeStreamingService(NodeNotFoundError("not found"))
        await _exec(ws, MagicMock(), service, _api_key_service())
        ws.close.assert_awaited_once_with(code=4004, reason="Node not found")

    async def test_command_execution_success(self) -> None:
        ws = _make_ws()
        ws.receive_json.side_effect = [
            {"command": "ls -la"},
            WebSocketDisconnect(),
        ]
        await _exec(ws, MagicMock(), FakeStreamingService(), _api_key_service())
        payloads = [call.args[0] for call in ws.send_json.await_args_list]
        assert {"type": "stdout", "data": "output line 1\n"} in payloads
        assert {"type": "done", "exit_code": 0} in payloads

    async def test_signal_handling(self) -> None:
        ws = _make_ws()
        ws.receive_json.side_effect = [
            {"type": "signal", "signal": "SIGINT"},
            WebSocketDisconnect(),
        ]
        await _exec(ws, MagicMock(), FakeStreamingService(), _api_key_service())
        ws.send_json.assert_any_await({"type": "signal_ack", "signal": "SIGINT"})

    async def test_missing_command_field(self) -> None:
        ws = _make_ws()
        ws.receive_json.side_effect = [{"type": "data"}, WebSocketDisconnect()]
        await _exec(ws, MagicMock(), FakeStreamingService(), _api_key_service())
        ws.send_json.assert_any_await({"type": "error", "message": "Missing 'command'"})

    @pytest.mark.parametrize(
        "error",
        [ConnectionFailedError("SSH failed"), ValueError("unexpected")],
    )
    async def test_command_error(self, error: Exception) -> None:
        ws = _make_ws()
        ws.receive_json.side_effect = [{"command": "ls"}, WebSocketDisconnect()]
        await _exec(
            ws,
            MagicMock(),
            FakeStreamingService(error),
            _api_key_service(),
        )
        payloads = [call.args[0] for call in ws.send_json.await_args_list]
        assert {"type": "error", "message": str(error)} in payloads
        assert {"type": "done", "exit_code": 1} in payloads

    async def test_websocket_disconnect_closes_application_session(self) -> None:
        ws = _make_ws()
        ws.receive_json.side_effect = WebSocketDisconnect()
        service = FakeStreamingService()
        await _exec(ws, MagicMock(), service, _api_key_service())
        assert service.closed is True

    async def test_unexpected_receive_error_closes_application_session(self) -> None:
        ws = _make_ws()
        ws.receive_json.side_effect = RuntimeError("disconnect")
        service = FakeStreamingService()
        await _exec(ws, MagicMock(), service, _api_key_service())
        assert service.closed is True
        ws.close.assert_awaited_once_with(code=1011, reason="Internal error")
