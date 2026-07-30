"""Tests for the WebSocket transport adapter."""

import asyncio
import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import WebSocketDisconnect

from app.api.v1.websocket import _send_command_events, _validate_ws_token, exec_stream
from app.application.dto.remote_stream import RemoteStreamEventDTO
from app.core.exceptions import ConnectionFailedError, NodeNotFoundError

_exec = exec_stream.__dishka_orig_func__  # type: ignore[attr-defined]


def _make_ws(token: str | None = "test-key") -> AsyncMock:
    ws = AsyncMock()
    ws.query_params = {"token": token} if token else {}
    return ws


class FakeStreamingSession:
    def __init__(self, error: Exception | None = None) -> None:
        self.error = error

    async def execute_events(self, command: str) -> AsyncIterator[RemoteStreamEventDTO]:
        if self.error:
            raise self.error
        yield RemoteStreamEventDTO(type="stdout", data="output line 1\n")
        yield RemoteStreamEventDTO(type="stderr", data="warning\n")
        yield RemoteStreamEventDTO(type="exit", exit_code=7)

    async def send_signal(self, signal: str) -> None:
        if signal != "SIGINT":
            raise ValueError("rejected")


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
    service.authenticate.return_value = SimpleNamespace(
        scope="read-write", key_prefix="nnk_test"
    )
    return service


@pytest.mark.asyncio
class TestExecStreamFullCoverage:
    async def test_master_token_authentication(self) -> None:
        ws = _make_ws()
        settings = SimpleNamespace(MASTER_API_KEY="master")
        with patch("app.api.v1.websocket.get_settings", return_value=settings):
            assert await _validate_ws_token(ws, "master", _api_key_service()) is True

    async def test_read_only_and_invalid_token_are_rejected(self) -> None:
        ws = _make_ws()
        service = _api_key_service()
        service.authenticate.return_value = SimpleNamespace(
            scope="read-only", key_prefix="nnk_test"
        )
        assert await _validate_ws_token(ws, "read-only", service) is False
        service.authenticate.side_effect = ValueError("invalid")
        assert await _validate_ws_token(ws, "invalid", service) is False
        service.authenticate.side_effect = RuntimeError("database")
        assert await _validate_ws_token(ws, "broken", service) is False

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
        assert {
            "version": "1",
            "type": "stdout",
            "data": "output line 1\n",
        } in payloads
        assert {"version": "1", "type": "exit", "exit_code": 7} in payloads

    async def test_signal_handling(self) -> None:
        ws = _make_ws()
        ws.receive_json.side_effect = [
            {"type": "signal", "signal": "SIGINT"},
            WebSocketDisconnect(),
        ]
        await _exec(ws, MagicMock(), FakeStreamingService(), _api_key_service())
        ws.send_json.assert_any_await(
            {"version": "1", "type": "signal_ack", "signal": "SIGINT"}
        )

    async def test_invalid_json_and_rejected_signal(self) -> None:
        ws = _make_ws()
        ws.receive_json.side_effect = [
            json.JSONDecodeError("bad", "", 0),
            {"type": "signal", "signal": "SIGTERM"},
            WebSocketDisconnect(),
        ]
        await _exec(ws, MagicMock(), FakeStreamingService(), _api_key_service())
        messages = [call.args[0]["message"] for call in ws.send_json.await_args_list]
        assert "Invalid JSON" in messages
        assert "Signal rejected" in messages

    async def test_oversized_message_closes_socket(self) -> None:
        ws = _make_ws()
        ws.receive_json.return_value = {"command": "x" * 20_000}
        await _exec(ws, MagicMock(), FakeStreamingService(), _api_key_service())
        ws.close.assert_awaited_with(code=1009, reason="Message too large")

    async def test_missing_command_field(self) -> None:
        ws = _make_ws()
        ws.receive_json.side_effect = [{"type": "data"}, WebSocketDisconnect()]
        await _exec(ws, MagicMock(), FakeStreamingService(), _api_key_service())
        ws.send_json.assert_any_await(
            {
                "version": "1",
                "type": "error",
                "message": "Invalid command message",
            }
        )

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
        expected_message = (
            "Remote execution failed"
            if isinstance(error, ConnectionFailedError)
            else "Internal error"
        )
        assert {
            "version": "1",
            "type": "error",
            "message": expected_message,
        } in payloads

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

    async def test_close_failure_is_best_effort(self) -> None:
        ws = _make_ws()
        ws.receive_json.side_effect = RuntimeError("disconnect")
        ws.close.side_effect = RuntimeError("already closed")
        await _exec(ws, MagicMock(), FakeStreamingService(), _api_key_service())

    async def test_cancelled_command_forwarding_is_propagated(self) -> None:
        session = MagicMock()

        async def cancelled(command: str):
            raise asyncio.CancelledError
            yield

        session.execute_events = cancelled
        with pytest.raises(asyncio.CancelledError):
            await _send_command_events(_make_ws(), session, "run", MagicMock())
