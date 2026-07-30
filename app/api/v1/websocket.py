"""WebSocket endpoint for streaming command output."""

import asyncio
import hmac
import json
from collections.abc import Mapping
from uuid import UUID

import structlog
from dishka.integrations.fastapi import DishkaRoute, FromDishka, inject
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import ValidationError

from app.application.services.api_key_authentication import (
    APIKeyAuthenticationService,
)
from app.application.services.streaming_command_service import (
    StreamingCommandService,
    StreamingCommandSession,
)
from app.core.config import get_settings
from app.core.exceptions import ConnectionFailedError, NodeNotFoundError
from app.schemas.websocket import WebSocketCommandMessage, WebSocketSignalMessage

logger = structlog.get_logger()
audit = structlog.get_logger("audit")

router = APIRouter(tags=["websocket"], route_class=DishkaRoute)
_MAX_WS_MESSAGE_SIZE = 16_384


async def _validate_ws_token(
    websocket: WebSocket,
    token: str | None,
    api_key_service: APIKeyAuthenticationService,
) -> bool:
    """Validate WebSocket API key token against the API key service.

    Returns True if authenticated, False and closes the socket otherwise.
    """
    if not token:
        await websocket.close(code=4001, reason="Missing token")
        return False
    settings = get_settings()
    if settings.MASTER_API_KEY and hmac.compare_digest(token, settings.MASTER_API_KEY):
        audit.info("ws.auth.ok", key_type="master")
        return True
    try:
        principal = await api_key_service.authenticate(token)
        if principal.scope != "read-write":
            await websocket.close(code=4003, reason="Insufficient scope")
            return False
        audit.info(
            "ws.auth.ok",
            key_prefix=principal.key_prefix,
        )
        return True
    except (ConnectionError, ValueError):
        audit.warning(
            "ws.auth.failed",
            key_prefix=token[:8] if len(token) >= 8 else "short",
        )
        await websocket.close(code=4003, reason="Invalid API key")
        return False
    except Exception:
        audit.warning("ws.auth.failed", error_type="authentication_error")
        await websocket.close(code=4003, reason="Invalid API key")
        return False


async def _send_command_events(
    websocket: WebSocket,
    session: StreamingCommandSession,
    command: str,
    node_id: UUID,
) -> None:
    """Forward typed remote process events without exposing internal errors."""
    try:
        async for event in session.execute_events(command):
            payload = {"version": "1", "type": event.type}
            if event.data is not None:
                payload["data"] = event.data
            if event.exit_code is not None:
                payload["exit_code"] = event.exit_code
            await websocket.send_json(payload)
    except ConnectionFailedError:
        await websocket.send_json(
            {"version": "1", "type": "error", "message": "Remote execution failed"}
        )
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        audit.exception(
            "ws.exec.failed",
            node_id=str(node_id),
            error_type=type(exc).__name__,
        )
        await websocket.send_json(
            {"version": "1", "type": "error", "message": "Internal error"}
        )


@router.websocket("/nodes/{node_id}/exec-stream")
@inject
async def exec_stream(
    websocket: WebSocket,
    node_id: UUID,
    streaming_service: FromDishka[StreamingCommandService],
    api_key_service: FromDishka[APIKeyAuthenticationService],
) -> None:
    """Stream command output via WebSocket.

    Authentication: ?token=<api_key>
    Client sends JSON: {"command": "ls -la"}
    Server sends: {"type": "stdout", "data": "..."} or
                  {"type": "done", "exit_code": 0}

    On disconnect, the SSH process is killed.
    """
    header_token = (
        websocket.headers.get("x-api-key")
        if isinstance(websocket.headers, Mapping)
        else None
    )
    token = (
        header_token
        if isinstance(header_token, str)
        else websocket.query_params.get("token")
    )
    if websocket.query_params.get("token"):
        logger.warning("ws.auth.query_token.deprecated")
    if not await _validate_ws_token(websocket, token, api_key_service):
        return

    await websocket.accept()

    try:
        try:
            connection = streaming_service.connect(node_id)
            async with connection as streaming_session:
                audit.info("ws.exec.connected", node_id=str(node_id))
                active_task: asyncio.Task[None] | None = None
                while True:
                    try:
                        data = await websocket.receive_json()
                    except (json.JSONDecodeError, ValueError):
                        await websocket.send_json(
                            {"version": "1", "type": "error", "message": "Invalid JSON"}
                        )
                        continue
                    if len(json.dumps(data)) > _MAX_WS_MESSAGE_SIZE:
                        await websocket.close(code=1009, reason="Message too large")
                        return

                    if data.get("type") == "signal":
                        try:
                            message = WebSocketSignalMessage.model_validate(data)
                            await streaming_session.send_signal(message.signal)
                        except (ValidationError, ValueError, RuntimeError):
                            await websocket.send_json(
                                {
                                    "version": "1",
                                    "type": "error",
                                    "message": "Signal rejected",
                                }
                            )
                            continue
                        audit.info(
                            "ws.exec.signal",
                            node_id=str(node_id),
                            signal=message.signal,
                        )
                        await websocket.send_json(
                            {
                                "version": "1",
                                "type": "signal_ack",
                                "signal": message.signal,
                            }
                        )
                        continue

                    try:
                        message = WebSocketCommandMessage.model_validate(data)
                    except ValidationError:
                        await websocket.send_json(
                            {
                                "version": "1",
                                "type": "error",
                                "message": "Invalid command message",
                            }
                        )
                        continue
                    if active_task is not None and not active_task.done():
                        await websocket.send_json(
                            {
                                "version": "1",
                                "type": "error",
                                "message": "A command is already running",
                            }
                        )
                        continue
                    audit.info(
                        "ws.exec.command",
                        node_id=str(node_id),
                        command_length=len(message.command),
                    )
                    active_task = asyncio.create_task(
                        _send_command_events(
                            websocket,
                            streaming_session,
                            message.command,
                            node_id,
                        )
                    )
                    await asyncio.sleep(0)
        except NodeNotFoundError:
            await websocket.send_json(
                {"type": "error", "message": f"Node {node_id} not found"}
            )
            await websocket.close(code=4004, reason="Node not found")
            return
        finally:
            if "active_task" in locals() and active_task is not None:
                active_task.cancel()
                await asyncio.gather(active_task, return_exceptions=True)
            audit.info("ws.exec.disconnected", node_id=str(node_id))

    except WebSocketDisconnect:
        audit.info("ws.exec.client_disconnect", node_id=str(node_id))
    except Exception as exc:
        audit.exception(
            "ws.exec.unexpected_error",
            node_id=str(node_id),
            error_type=type(exc).__name__,
        )
        try:
            await websocket.close(code=1011, reason="Internal error")
        except RuntimeError as close_exc:
            logger.debug(
                "ws.exec.close_failed",
                node_id=str(node_id),
                error_type=type(close_exc).__name__,
            )
