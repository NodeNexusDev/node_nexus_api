"""WebSocket endpoint for streaming command output."""

import json
from uuid import UUID

import structlog
from dishka.integrations.fastapi import DishkaRoute, FromDishka, inject
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.core.exceptions import ConnectionFailedError
from app.core.ssh_utils import decrypt_value
from app.services.api_key_service import APIKeyService
from app.services.node_service import NodeService

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
    node_service: FromDishka[NodeService],
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
        # Resolve node via service layer (avoids direct repo access)
        try:
            await node_service.get_node(node_id)
        except Exception:
            await websocket.send_json(
                {"type": "error", "message": f"Node {node_id} not found"}
            )
            await websocket.close(code=4004, reason="Node not found")
            return

        # Get the node model for credentials (service only returns safe response)
        from app.di.container import container
        from app.repositories.node_repo import NodeRepository

        async with container() as request_container:
            node_repo = await request_container.get(NodeRepository)
            node = await node_repo.get_by_id(node_id)
            if node is None:
                await websocket.send_json(
                    {"type": "error", "message": f"Node {node_id} not found"}
                )
                await websocket.close(code=4004, reason="Node not found")
                return

            password = decrypt_value(node.password)
            ssh_key = decrypt_value(node.ssh_key)

            from app.core.connectors.ssh import SSHConnectorFactory

            connector_factory: SSHConnectorFactory = await request_container.get(
                SSHConnectorFactory
            )
            connector = connector_factory.create_ssh(
                host=node.host,
                port=node.port,
                username=node.username,
                password=password,
                ssh_key=ssh_key,
            )

        try:
            await connector.connect()
            audit.info(
                "ws.exec.connected",
                node_id=str(node_id),
                host=node.host,
            )

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
                        "ws.exec.signal",
                        node_id=str(node_id),
                        signal=signal,
                    )
                    await websocket.send_json({"type": "signal_ack", "signal": signal})
                    continue

                if not command:
                    await websocket.send_json(
                        {"type": "error", "message": "Missing 'command'"}
                    )
                    continue

                audit.info(
                    "ws.exec.command",
                    node_id=str(node_id),
                    command=command,
                )

                try:
                    async for chunk in connector.execute_command_streaming(command):
                        await websocket.send_json({"type": "stdout", "data": chunk})
                    await websocket.send_json({"type": "done", "exit_code": 0})
                except ConnectionFailedError as exc:
                    await websocket.send_json({"type": "error", "message": str(exc)})
                    await websocket.send_json({"type": "done", "exit_code": 1})
                except Exception as exc:
                    audit.error(
                        "ws.exec.failed",
                        node_id=str(node_id),
                        command=command,
                        error=str(exc),
                    )
                    await websocket.send_json({"type": "error", "message": str(exc)})
                    await websocket.send_json({"type": "done", "exit_code": 1})

        finally:
            await connector.disconnect()
            audit.info("ws.exec.disconnected", node_id=str(node_id))

    except WebSocketDisconnect:
        audit.info("ws.exec.client_disconnect", node_id=str(node_id))
    except Exception as exc:
        audit.error("ws.exec.unexpected_error", node_id=str(node_id), error=str(exc))
        try:
            await websocket.close(code=1011, reason="Internal error")
        except Exception:
            pass
