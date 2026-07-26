"""Tests for WebSocket exec_stream handler — covers more code paths.

Uses exec_stream.__wrapped__ to bypass the @inject decorator and
pass mock dependencies directly.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.api.v1.websocket import exec_stream
from app.core.exceptions import ConnectionFailedError

# The @inject decorator wraps exec_stream; __dishka_orig_func__ is the original
_exec = exec_stream.__dishka_orig_func__  # type: ignore[attr-defined]


def _make_ws(token: str = "test-key"):
    ws = AsyncMock()
    ws.query_params = {"token": token} if token else {}
    ws.accept = AsyncMock()
    ws.send_json = AsyncMock()
    ws.close = AsyncMock()
    return ws


def _make_node():
    node = MagicMock()
    node.host = "10.0.0.1"
    node.port = 22
    node.username = "root"
    node.password = None
    node.ssh_key = None
    return node


def _make_connector():
    conn = AsyncMock()
    conn.connect = AsyncMock()
    conn.disconnect = AsyncMock()
    conn.execute_command_streaming = AsyncMock()
    return conn


def _make_services():
    node_svc = AsyncMock()
    node_svc.get_node.return_value = MagicMock()
    api_key_svc = AsyncMock()
    api_key_svc.validate_api_key.return_value = None
    return node_svc, api_key_svc


def _setup_container(node, connector):
    """Create a mock DI container that returns repo and factory."""
    mock_node_repo = AsyncMock()
    mock_node_repo.get_by_id.return_value = node

    mock_factory = MagicMock()
    mock_factory.create_ssh.return_value = connector

    mock_container = AsyncMock()
    mock_container.__aenter__ = AsyncMock(return_value=mock_container)
    mock_container.__aexit__ = AsyncMock(return_value=False)

    async def _fake_get(cls):
        if cls.__name__ == "NodeRepository":
            return mock_node_repo
        if "SSHConnectorFactory" in str(cls):
            return mock_factory
        return MagicMock()

    mock_container.get = _fake_get
    return mock_container


@pytest.mark.asyncio
class TestExecStreamFullCoverage:
    async def test_missing_token(self):
        ws = _make_ws(token=None)
        node_svc, api_key_svc = _make_services()
        await _exec(
            ws, node_id=MagicMock(), node_service=node_svc, api_key_service=api_key_svc
        )
        ws.close.assert_called_once_with(code=4001, reason="Missing token")

    async def test_node_not_found(self):
        ws = _make_ws()
        node_svc, api_key_svc = _make_services()
        node_svc.get_node.side_effect = Exception("Not found")
        await _exec(
            ws, node_id=MagicMock(), node_service=node_svc, api_key_service=api_key_svc
        )
        ws.accept.assert_called_once()
        calls = [str(c) for c in ws.send_json.call_args_list]
        assert any("not found" in c.lower() for c in calls)

    async def test_command_execution_success(self):
        ws = _make_ws()
        node = _make_node()
        connector = _make_connector()

        async def mock_stream(cmd):
            yield "output line 1\n"
            yield "output line 2\n"

        connector.execute_command_streaming = mock_stream
        node_svc, api_key_svc = _make_services()
        mock_container = _setup_container(node, connector)

        ws.receive_json = AsyncMock(
            side_effect=[{"command": "ls -la"}, Exception("disconnect")]
        )

        with (
            patch("app.di.container.container", return_value=mock_container),
            patch("app.api.v1.websocket.decrypt_value", return_value=None),
        ):
            try:
                await _exec(
                    ws,
                    node_id=MagicMock(),
                    node_service=node_svc,
                    api_key_service=api_key_svc,
                )
            except Exception:
                pass

        calls = [str(c) for c in ws.send_json.call_args_list]
        assert any("stdout" in c for c in calls)
        assert any("done" in c for c in calls)

    async def test_signal_handling(self):
        ws = _make_ws()
        node = _make_node()
        connector = _make_connector()
        node_svc, api_key_svc = _make_services()
        mock_container = _setup_container(node, connector)

        ws.receive_json = AsyncMock(
            side_effect=[
                {"type": "signal", "signal": "SIGINT"},
                Exception("disconnect"),
            ]
        )

        with (
            patch("app.di.container.container", return_value=mock_container),
            patch("app.api.v1.websocket.decrypt_value", return_value=None),
        ):
            try:
                await _exec(
                    ws,
                    node_id=MagicMock(),
                    node_service=node_svc,
                    api_key_service=api_key_svc,
                )
            except Exception:
                pass

        calls = [str(c) for c in ws.send_json.call_args_list]
        assert any("signal_ack" in c for c in calls)

    async def test_missing_command_field(self):
        ws = _make_ws()
        node = _make_node()
        connector = _make_connector()
        node_svc, api_key_svc = _make_services()
        mock_container = _setup_container(node, connector)

        ws.receive_json = AsyncMock(
            side_effect=[{"type": "data"}, Exception("disconnect")]
        )

        with (
            patch("app.di.container.container", return_value=mock_container),
            patch("app.api.v1.websocket.decrypt_value", return_value=None),
        ):
            try:
                await _exec(
                    ws,
                    node_id=MagicMock(),
                    node_service=node_svc,
                    api_key_service=api_key_svc,
                )
            except Exception:
                pass

        calls = [str(c) for c in ws.send_json.call_args_list]
        assert any("Missing" in c for c in calls)

    async def test_connection_failed_error(self):
        ws = _make_ws()
        node = _make_node()
        connector = _make_connector()

        async def failing_stream(cmd):
            raise ConnectionFailedError("SSH connection failed")
            yield  # pragma: no cover

        connector.execute_command_streaming = failing_stream
        node_svc, api_key_svc = _make_services()
        mock_container = _setup_container(node, connector)

        ws.receive_json = AsyncMock(
            side_effect=[{"command": "ls"}, Exception("disconnect")]
        )

        with (
            patch("app.di.container.container", return_value=mock_container),
            patch("app.api.v1.websocket.decrypt_value", return_value=None),
        ):
            try:
                await _exec(
                    ws,
                    node_id=MagicMock(),
                    node_service=node_svc,
                    api_key_service=api_key_svc,
                )
            except Exception:
                pass

        calls = [str(c) for c in ws.send_json.call_args_list]
        assert any("error" in c for c in calls)
        assert any("done" in c for c in calls)

    async def test_unexpected_exception(self):
        ws = _make_ws()
        node = _make_node()
        connector = _make_connector()

        async def failing_stream(cmd):
            raise ValueError("unexpected error")
            yield  # pragma: no cover

        connector.execute_command_streaming = failing_stream
        node_svc, api_key_svc = _make_services()
        mock_container = _setup_container(node, connector)

        ws.receive_json = AsyncMock(
            side_effect=[{"command": "ls"}, Exception("disconnect")]
        )

        with (
            patch("app.di.container.container", return_value=mock_container),
            patch("app.api.v1.websocket.decrypt_value", return_value=None),
        ):
            try:
                await _exec(
                    ws,
                    node_id=MagicMock(),
                    node_service=node_svc,
                    api_key_service=api_key_svc,
                )
            except Exception:
                pass

        calls = [str(c) for c in ws.send_json.call_args_list]
        assert any("error" in c for c in calls)

    async def test_websocket_disconnect(self):
        from fastapi import WebSocketDisconnect

        ws = _make_ws()
        node = _make_node()
        connector = _make_connector()
        node_svc, api_key_svc = _make_services()
        mock_container = _setup_container(node, connector)

        ws.receive_json = AsyncMock(side_effect=WebSocketDisconnect())

        with (
            patch("app.di.container.container", return_value=mock_container),
            patch("app.api.v1.websocket.decrypt_value", return_value=None),
        ):
            await _exec(
                ws,
                node_id=MagicMock(),
                node_service=node_svc,
                api_key_service=api_key_svc,
            )

    async def test_connector_disconnect_in_finally(self):
        ws = _make_ws()
        node = _make_node()
        connector = _make_connector()
        node_svc, api_key_svc = _make_services()
        mock_container = _setup_container(node, connector)

        ws.receive_json = AsyncMock(side_effect=Exception("disconnect"))

        with (
            patch("app.di.container.container", return_value=mock_container),
            patch("app.api.v1.websocket.decrypt_value", return_value=None),
        ):
            try:
                await _exec(
                    ws,
                    node_id=MagicMock(),
                    node_service=node_svc,
                    api_key_service=api_key_svc,
                )
            except Exception:
                pass

        connector.disconnect.assert_called_once()
