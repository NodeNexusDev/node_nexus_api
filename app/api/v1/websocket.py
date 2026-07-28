"""WebSocket endpoint for streaming command output."""

import json
from uuid import UUID

import structlog
from dishka.integrations.fastapi import DishkaRoute, FromDishka, inject
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.application.services.streaming_command_service import StreamingCommandService
from app.core.exceptions import ConnectionFailedError, NodeNotFoundError
from app.services.api_key_service import APIKeyService

logger = structlog.get_logger()
audit = structlog.get_logger("audit")

router = APIRouter(tags=["websocket"], route_class=DishkaRoute)


async def _validate_ws_token(
    websocket: WebSocket,
    token: str | None,
    api_key_service: APIKeyService,
) -> bool:
    """Validate WebSocket API key token against the API key service.

    Returns True if authenticated, False and closes the socket otherwise.
    """
    if not token:
        await websocket.close(code=4001, reason="Missing token")
        return False
    try:
        await api_key_service.validate_api_key(token)
        audit.info("ws.auth.ok", key_prefix=token[:8])
        return True
    except Exception:
        audit.warning(
            "ws.auth.failed",
            key_prefix=token[:8] if len(token) >= 8 else "short",
        )
        await websocket.close(code=4003, reason="Invalid API key")
        return False


@router.websocket("/nodes/{node_id}/exec-stream")
@inject
async def exec_stream(
    websocket: WebSocket,
    node_id: UUID,
    streaming_service: FromDishka[StreamingCommandService],
    api_key_service: FromDishka[APIKeyService],
) -> None:
    """Stream command output via WebSocket.

    Authentication: ?token=<api_key>
    Client sends JSON: {"command": "ls -la"}
    Server sends: {"type": "stdout", "data": "..."} or
                  {"type": "done", "exit_code": 0}

    On disconnect, the SSH process is killed.
    """
    token = websocket.query_params.get("token")
    if not await _validate_ws_token(websocket, token, api_key_service):
        return

    await websocket.accept()

    try:
        try:
            connection = streaming_service.connect(node_id)
            async with connection as streaming_session:
                audit.info("ws.exec.connected", node_id=str(node_id))

                while True:
                    try:
                        data = await websocket.receive_json()
                    except json.JSONDecodeError:
                        await websocket.send_json(
                            {"type": "error", "message": "Invalid JSON"}
                        )
                        continue

                    command = data.get("command")
                    signal_type = data.get("type")

                    if signal_type == "signal":
                        signal = data.get("signal", "SIGINT")
                        audit.info(
                            "ws.exec.signal", node_id=str(node_id), signal=signal
                        )
                        await websocket.send_json(
                            {"type": "signal_ack", "signal": signal}
                        )
                        continue

                    if not command:
                        await websocket.send_json(
                            {"type": "error", "message": "Missing 'command'"}
                        )
                        continue

                    audit.info("ws.exec.command", node_id=str(node_id), command=command)
                    try:
                        async for chunk in streaming_session.execute(command):
                            await websocket.send_json({"type": "stdout", "data": chunk})
                        await websocket.send_json({"type": "done", "exit_code": 0})
                    except ConnectionFailedError as exc:
                        await websocket.send_json(
                            {"type": "error", "message": str(exc)}
                        )
                        await websocket.send_json({"type": "done", "exit_code": 1})
                    except Exception as exc:
                        audit.error(
                            "ws.exec.failed",
                            node_id=str(node_id),
                            command=command,
                            error=str(exc),
                        )
                        await websocket.send_json(
                            {"type": "error", "message": str(exc)}
                        )
                        await websocket.send_json({"type": "done", "exit_code": 1})
        except NodeNotFoundError:
            await websocket.send_json(
                {"type": "error", "message": f"Node {node_id} not found"}
            )
            await websocket.close(code=4004, reason="Node not found")
            return
        finally:
            audit.info("ws.exec.disconnected", node_id=str(node_id))

    except WebSocketDisconnect:
        audit.info("ws.exec.client_disconnect", node_id=str(node_id))
    except Exception as exc:
        audit.error("ws.exec.unexpected_error", node_id=str(node_id), error=str(exc))
        try:
            await websocket.close(code=1011, reason="Internal error")
        except Exception as close_exc:
            logger.debug(
                "ws.exec.close_failed",
                node_id=str(node_id),
                error=str(close_exc),
            )
