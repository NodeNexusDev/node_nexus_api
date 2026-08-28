"""Comprehensive unit tests for app.api.v1.websocket — coverage gaps.

Targets untested branches in _validate_ws_token, _send_command_events,
and exec_stream to push coverage from 43% to 80%+.
"""

import asyncio
import json
from collections.abc import AsyncGenerator, AsyncIterator
from contextlib import asynccontextmanager
from types import SimpleNamespace
from typing import Literal
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from fastapi import WebSocketDisconnect

from app.api.v1.websocket import (
    _send_command_events,
    _validate_ws_token,
    exec_stream,
)
from app.application.dto.remote_stream import RemoteStreamEventDTO
from app.core.exceptions import ConnectionFailedError, NodeNotFoundError
from tests.typing import as_unvalidated

_exec = getattr(exec_stream, "__dishka_orig_func__")

_NODE_ID = uuid4()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_ws(token: str | None = "test-key") -> AsyncMock:
    ws = AsyncMock()
    ws.headers = {"x-api-key": token} if token else {}
    return ws


def _api_key_service() -> AsyncMock:
    service = AsyncMock()
    service.authenticate.return_value = SimpleNamespace(
        scope="read-write",
        key_prefix="nnk_test",
    )
    return service


class _TrackableAsyncIterator:
    """Async iterator that records whether aclose() was called."""

    def __init__(self, items: list[RemoteStreamEventDTO]) -> None:
        self._items = items
        self._index = 0
        self.aclose_called = False

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self._index < len(self._items):
            item = self._items[self._index]
            self._index += 1
            return item
        raise StopAsyncIteration

    async def aclose(self):
        self.aclose_called = True


class _SlowStreamingSession:
    """Session whose execute_events hangs until released by abort."""

    def __init__(self) -> None:
        self._started = asyncio.Event()
        self._done = asyncio.Event()
        self.aborted = False

    async def execute_events(
        self, command: str
    ) -> AsyncGenerator[RemoteStreamEventDTO]:
        self._started.set()
        yield RemoteStreamEventDTO(type="stdout", data="running\n")
        await self._done.wait()
        yield RemoteStreamEventDTO(type="exit", exit_code=0)

    async def send_signal(self, signal: str) -> None:
        pass

    async def abort_active_process(self) -> None:
        self.aborted = True
        self._done.set()


class _SlowStreamingService:
    """StreamingService that yields a _SlowStreamingSession."""

    def __init__(self, session: _SlowStreamingSession | None = None) -> None:
        self._session = session or _SlowStreamingSession()

    @asynccontextmanager
    async def connect(self, node_id: object) -> AsyncIterator[_SlowStreamingSession]:
        yield self._session


class _FailingStreamingService:
    """StreamingService whose connect() raises before yielding."""

    def __init__(self, error: Exception) -> None:
        self._error = error

    @asynccontextmanager
    async def connect(self, node_id: object) -> AsyncIterator[object]:
        raise self._error
        if False:
            yield object()  # pragma: no cover


class _FakeStreamingSession:
    def __init__(self, error: Exception | None = None) -> None:
        self._error = error
        self._sent_signals: list[str] = []

    async def execute_events(
        self, command: str
    ) -> AsyncGenerator[RemoteStreamEventDTO]:
        if self._error:
            raise self._error
        yield RemoteStreamEventDTO(type="stdout", data="ok\n")
        yield RemoteStreamEventDTO(type="exit", exit_code=0)

    async def send_signal(self, signal: str) -> None:
        self._sent_signals.append(signal)
        if signal not in ("SIGINT", "SIGTERM"):
            raise ValueError("bad signal")

    async def abort_active_process(self) -> None:
        return None


class _FakeStreamingService:
    def __init__(self, error: Exception | None = None) -> None:
        self._error = error
        self.closed = False

    @asynccontextmanager
    async def connect(self, node_id: object) -> AsyncIterator[_FakeStreamingSession]:
        if isinstance(self._error, (NodeNotFoundError, ConnectionFailedError)):
            raise self._error
        try:
            yield _FakeStreamingSession(self._error)
        finally:
            self.closed = True


# ===========================================================================
# _validate_ws_token
# ===========================================================================


class TestValidateWsToken:
    """Tests for _validate_ws_token edge cases."""

    @pytest.mark.asyncio
    async def test_connection_error_returns_false(self) -> None:
        """ConnectionError during authenticate → code 4003, Invalid API key."""
        ws = _make_ws()
        service = _api_key_service()
        service.authenticate.side_effect = ConnectionError("refused")

        result = await _validate_ws_token(ws, "nnk_badkey", service)

        assert result is False
        ws.close.assert_awaited_once_with(code=4003, reason="Invalid API key")

    @pytest.mark.asyncio
    async def test_generic_exception_returns_false(self) -> None:
        """Unexpected Exception during authenticate → code 4003, Invalid API key."""
        ws = _make_ws()
        service = _api_key_service()
        service.authenticate.side_effect = RuntimeError("db timeout")

        result = await _validate_ws_token(ws, "nnk_abcdef", service)

        assert result is False
        ws.close.assert_awaited_once_with(code=4003, reason="Invalid API key")


# ===========================================================================
# _send_command_events
# ===========================================================================


class TestSendCommandEvents:
    """Tests for _send_command_events as a standalone async function."""

    @pytest.mark.asyncio
    async def test_success_sends_all_fields(self) -> None:
        """Events with data and exit_code are forwarded with version/type."""
        ws = _make_ws()
        events = _TrackableAsyncIterator(
            [
                RemoteStreamEventDTO(type="stdout", data="hello\n"),
                RemoteStreamEventDTO(type="stderr", data="warn\n"),
                RemoteStreamEventDTO(type="exit", exit_code=0),
            ]
        )
        session = MagicMock()
        session.execute_events.return_value = events

        await _send_command_events(ws, session, "ls", _NODE_ID)

        payloads = [call.args[0] for call in ws.send_json.await_args_list]
        assert payloads == [
            {"version": "1", "type": "stdout", "data": "hello\n"},
            {"version": "1", "type": "stderr", "data": "warn\n"},
            {"version": "1", "type": "exit", "exit_code": 0},
        ]
        assert events.aclose_called is True

    @pytest.mark.asyncio
    async def test_connection_failed_error_sends_remote_error(self) -> None:
        """ConnectionFailedError → 'Remote execution failed' message."""
        ws = _make_ws()

        class _ErrorIterator:
            def __init__(self):
                self.aclose_called = False

            def __aiter__(self):
                return self

            async def __anext__(self):
                raise ConnectionFailedError("ssh down")

            async def aclose(self):
                self.aclose_called = True

        err_events = _ErrorIterator()
        session = MagicMock()
        session.execute_events.return_value = err_events

        await _send_command_events(ws, session, "ls", _NODE_ID)

        ws.send_json.assert_awaited_once_with(
            {"version": "1", "type": "error", "message": "Remote execution failed"},
        )
        assert err_events.aclose_called is True

    @pytest.mark.asyncio
    async def test_generic_exception_sends_internal_error(self) -> None:
        """Unexpected exception → 'Internal error' message."""
        ws = _make_ws()

        class _ErrorIterator:
            def __init__(self):
                self.aclose_called = False

            def __aiter__(self):
                return self

            async def __anext__(self):
                raise ValueError("something broke")

            async def aclose(self):
                self.aclose_called = True

        err_events = _ErrorIterator()
        session = MagicMock()
        session.execute_events.return_value = err_events

        await _send_command_events(ws, session, "ls", _NODE_ID)

        ws.send_json.assert_awaited_once_with(
            {"version": "1", "type": "error", "message": "Internal error"},
        )
        assert err_events.aclose_called is True

    @pytest.mark.asyncio
    async def test_aclose_called_on_success(self) -> None:
        """aclose() is called in finally even on successful iteration."""
        ws = _make_ws()
        events = _TrackableAsyncIterator(
            [
                RemoteStreamEventDTO(
                    type=as_unvalidated(Literal["stdout", "stderr", "exit"], "done"),
                    exit_code=0,
                ),
            ]
        )
        session = MagicMock()
        session.execute_events.return_value = events

        await _send_command_events(ws, session, "echo hi", _NODE_ID)

        assert events.aclose_called is True

    @pytest.mark.asyncio
    async def test_aclose_called_on_error(self) -> None:
        """aclose() is called even when iteration raises."""
        ws = _make_ws()

        class _ErrorIterator:
            def __init__(self):
                self.aclose_called = False

            def __aiter__(self):
                return self

            async def __anext__(self):
                raise RuntimeError("boom")

            async def aclose(self):
                self.aclose_called = True

        err_events = _ErrorIterator()
        session = MagicMock()
        session.execute_events.return_value = err_events

        await _send_command_events(ws, session, "ls", _NODE_ID)

        assert err_events.aclose_called is True

    @pytest.mark.asyncio
    async def test_cancelled_error_propagates(self) -> None:
        """CancelledError is re-raised, not swallowed."""
        ws = _make_ws()

        class _CancelIterator:
            def __aiter__(self):
                return self

            async def __anext__(self):
                raise asyncio.CancelledError

            async def aclose(self):
                pass

        session = MagicMock()
        session.execute_events.return_value = _CancelIterator()

        with pytest.raises(asyncio.CancelledError):
            await _send_command_events(ws, session, "ls", _NODE_ID)

    @pytest.mark.asyncio
    async def test_event_without_data_or_exit_code(self) -> None:
        """Events with only type are forwarded without extra keys."""
        ws = _make_ws()
        events = _TrackableAsyncIterator(
            [
                RemoteStreamEventDTO(
                    type=as_unvalidated(Literal["stdout", "stderr", "exit"], "started")
                ),
            ]
        )
        session = MagicMock()
        session.execute_events.return_value = events

        await _send_command_events(ws, session, "cmd", _NODE_ID)

        ws.send_json.assert_awaited_once_with({"version": "1", "type": "started"})


# ===========================================================================
# exec_stream
# ===========================================================================


class TestExecStreamHeaderParsing:
    """Tests for header extraction in exec_stream."""

    @pytest.mark.asyncio
    async def test_non_mapping_headers_yields_token_none(self) -> None:
        """When websocket.headers is not a Mapping, token defaults to None."""
        ws = _make_ws("dummy")
        setattr(ws, "headers", "not-a-mapping")

        await _exec(ws, uuid4(), MagicMock(), _api_key_service())

        ws.close.assert_awaited_once_with(code=4001, reason="Missing token")


class TestExecStreamDisconnectCleanup:
    """Tests for WebSocketDisconnect during active task handling."""

    @pytest.mark.asyncio
    async def test_disconnect_during_active_task_aborts_process(self) -> None:
        """Disconnect while command is running → abort_active_process called."""
        ws = _make_ws()
        session = _SlowStreamingSession()
        service = _SlowStreamingService(session)

        ws.receive_json.side_effect = [
            {"command": "long-running"},
            WebSocketDisconnect(),
        ]

        await _exec(ws, _NODE_ID, service, _api_key_service())

        assert session.aborted is True

    @pytest.mark.asyncio
    async def test_disconnect_without_active_task_no_abort(self) -> None:
        """Disconnect with no active task → no abort call."""
        ws = _make_ws()
        session = _SlowStreamingSession()
        service = _SlowStreamingService(session)

        ws.receive_json.side_effect = WebSocketDisconnect()

        await _exec(ws, _NODE_ID, service, _api_key_service())

        assert session.aborted is False


class TestExecStreamCommandExecution:
    """Tests for command execution flow inside exec_stream."""

    @pytest.mark.asyncio
    async def test_command_success(self) -> None:
        """Valid command → events forwarded, then disconnect closes cleanly."""
        ws = _make_ws()
        ws.receive_json.side_effect = [
            {"command": "ls -la"},
            WebSocketDisconnect(),
        ]
        service = _FakeStreamingService()

        await _exec(ws, _NODE_ID, service, _api_key_service())

        payloads = [call.args[0] for call in ws.send_json.await_args_list]
        assert {"version": "1", "type": "stdout", "data": "ok\n"} in payloads
        assert {"version": "1", "type": "exit", "exit_code": 0} in payloads
        assert service.closed is True

    @pytest.mark.asyncio
    async def test_active_task_collision(self) -> None:
        """Second command while first is running → 'already running' error."""
        ws = _make_ws()
        session = _SlowStreamingSession()
        service = _SlowStreamingService(session)

        ws.receive_json.side_effect = [
            {"command": "first"},
            {"command": "second"},
            WebSocketDisconnect(),
        ]

        await _exec(ws, _NODE_ID, service, _api_key_service())

        messages = [call.args[0] for call in ws.send_json.await_args_list]
        assert any(m.get("message") == "A command is already running" for m in messages)

    @pytest.mark.asyncio
    async def test_no_error_when_no_active_task(self) -> None:
        """Command when no task exists → no collision error."""
        ws = _make_ws()
        service = _FakeStreamingService()

        ws.receive_json.side_effect = [
            {"command": "echo hi"},
            WebSocketDisconnect(),
        ]

        await _exec(ws, _NODE_ID, service, _api_key_service())

        messages = [call.args[0] for call in ws.send_json.await_args_list]
        assert not any(
            m.get("message") == "A command is already running" for m in messages
        )


class TestExecStreamErrorHandling:
    """Tests for error paths in exec_stream."""

    @pytest.mark.asyncio
    async def test_json_decode_error_continues_loop(self) -> None:
        """Invalid JSON → error message, loop continues."""
        ws = _make_ws()
        ws.receive_json.side_effect = [
            json.JSONDecodeError("err", "", 0),
            {"command": "ls"},
            WebSocketDisconnect(),
        ]
        service = _FakeStreamingService()

        await _exec(ws, _NODE_ID, service, _api_key_service())

        messages = [call.args[0] for call in ws.send_json.await_args_list]
        assert any(m.get("message") == "Invalid JSON" for m in messages)

    @pytest.mark.asyncio
    async def test_oversized_message_closes_socket(self) -> None:
        """Message larger than 16384 bytes → close code 1009."""
        ws = _make_ws()
        ws.receive_json.return_value = {"command": "x" * 20_000}

        await _exec(ws, _NODE_ID, _FakeStreamingService(), _api_key_service())

        ws.close.assert_awaited_with(code=1009, reason="Message too large")

    @pytest.mark.asyncio
    async def test_signal_sends_ack(self) -> None:
        """Valid signal message → signal_ack response."""
        ws = _make_ws()
        ws.receive_json.side_effect = [
            {"type": "signal", "signal": "SIGINT"},
            WebSocketDisconnect(),
        ]

        await _exec(ws, _NODE_ID, _FakeStreamingService(), _api_key_service())

        payloads = [call.args[0] for call in ws.send_json.await_args_list]
        assert {"version": "1", "type": "signal_ack", "signal": "SIGINT"} in payloads

    @pytest.mark.asyncio
    async def test_invalid_signal_sends_error(self) -> None:
        """Signal rejected by session → 'Signal rejected' error."""
        ws = _make_ws()
        ws.receive_json.side_effect = [
            {"type": "signal", "signal": "SIGKILL"},
            WebSocketDisconnect(),
        ]

        await _exec(ws, _NODE_ID, _FakeStreamingService(), _api_key_service())

        messages = [call.args[0] for call in ws.send_json.await_args_list]
        assert any(m.get("message") == "Signal rejected" for m in messages)

    @pytest.mark.asyncio
    async def test_invalid_command_message(self) -> None:
        """Message without 'command' field → 'Invalid command message' error."""
        ws = _make_ws()
        ws.receive_json.side_effect = [
            {"type": "data", "payload": "x"},
            WebSocketDisconnect(),
        ]

        await _exec(ws, _NODE_ID, _FakeStreamingService(), _api_key_service())

        messages = [call.args[0] for call in ws.send_json.await_args_list]
        assert any(m.get("message") == "Invalid command message" for m in messages)


class TestExecStreamServiceErrors:
    """Tests for service-level errors raised by streaming_service.connect()."""

    @pytest.mark.asyncio
    async def test_node_not_found(self) -> None:
        """NodeNotFoundError → error message + close code 4004."""
        ws = _make_ws()
        service = _FailingStreamingService(NodeNotFoundError("missing"))

        await _exec(ws, _NODE_ID, service, _api_key_service())

        ws.close.assert_awaited_once_with(code=4004, reason="Node not found")
        payloads = [call.args[0] for call in ws.send_json.await_args_list]
        assert any(m.get("message") == f"Node {_NODE_ID} not found" for m in payloads)

    @pytest.mark.asyncio
    async def test_connection_failed_from_connect(self) -> None:
        """ConnectionFailedError from connect() → 'Remote connection failed'."""
        ws = _make_ws()
        service = _FailingStreamingService(ConnectionFailedError("timeout"))

        await _exec(ws, _NODE_ID, service, _api_key_service())

        payloads = [call.args[0] for call in ws.send_json.await_args_list]
        assert any(m.get("message") == "Remote connection failed" for m in payloads)


class TestExecStreamUnexpectedErrors:
    """Tests for unexpected exception handling in exec_stream."""

    @pytest.mark.asyncio
    async def test_unexpected_exception_closes_1011(self) -> None:
        """RuntimeError → close code 1011."""
        ws = _make_ws()
        ws.receive_json.side_effect = RuntimeError("kaboom")

        await _exec(ws, _NODE_ID, _FakeStreamingService(), _api_key_service())

        ws.close.assert_awaited_once_with(code=1011, reason="Internal error")

    @pytest.mark.asyncio
    async def test_close_failure_best_effort(self) -> None:
        """RuntimeError on close → debug log, no re-raise."""
        ws = _make_ws()
        ws.receive_json.side_effect = RuntimeError("disconnect")
        ws.close.side_effect = RuntimeError("already closed")

        await _exec(ws, _NODE_ID, _FakeStreamingService(), _api_key_service())

        ws.close.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_websocket_disconnect_outer_handler(self) -> None:
        """WebSocketDisconnect from inner loop → caught by outer handler."""
        ws = _make_ws()
        ws.receive_json.side_effect = WebSocketDisconnect()

        await _exec(ws, _NODE_ID, _FakeStreamingService(), _api_key_service())

        ws.close.assert_not_awaited()
        ws.send_json.assert_not_awaited()


class TestExecStreamDisconnectCleanupFinally:
    """Tests for the finally block cleanup logic."""

    @pytest.mark.asyncio
    async def test_active_task_cancelled_in_finally(self) -> None:
        """Active task is cancelled and gathered in the finally block."""
        ws = _make_ws()
        session = _SlowStreamingSession()
        service = _SlowStreamingService(session)

        ws.receive_json.side_effect = [
            {"command": "first"},
            WebSocketDisconnect(),
        ]

        await _exec(ws, _NODE_ID, service, _api_key_service())

        assert session.aborted is True

    @pytest.mark.asyncio
    async def test_abort_failure_in_disconnect_is_logged(self) -> None:
        """RuntimeError during abort in disconnect → debug log, no crash."""
        ws = _make_ws()
        session = _SlowStreamingSession()
        session.abort_active_process = AsyncMock(side_effect=RuntimeError("oops"))
        service = _SlowStreamingService(session)

        ws.receive_json.side_effect = [
            {"command": "first"},
            WebSocketDisconnect(),
        ]

        await _exec(ws, _NODE_ID, service, _api_key_service())
