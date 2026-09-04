"""Cover node_bulk_operation_service ssh branches."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

from app.application.dto.bulk_node_operation import BulkNodeCheckResultDTO
from app.application.dto.node_connection import NodeConnectionDTO
from app.application.dto.value_objects import NodeCredentials, NodeEndpoint
from app.application.services.node_bulk_operation_service import (
    NodeBulkOperationService,
)
from app.core.exceptions import ConnectionFailedError


def _make_service(**overrides):
    defaults = {
        "operator": AsyncMock(),
        "audit_service": None,
        "node_reader": AsyncMock(),
        "status_writer": AsyncMock(),
        "credential_cipher": MagicMock(),
        "connector_factory": MagicMock(),
        "status_history_writer": AsyncMock(),
        "node_view_reader": AsyncMock(),
    }
    defaults.update(overrides)
    return NodeBulkOperationService(**defaults)


class TestBulkCheck:
    async def test_db_mode(self):
        op = AsyncMock()
        op.bulk_check = AsyncMock(
            return_value=BulkNodeCheckResultDTO(
                total=1, succeeded=1, failed=0, node_ids=(uuid.uuid4(),)
            )
        )
        svc = _make_service(operator=op, audit_service=None)
        res = await svc.bulk_check(node_ids=(str(uuid.uuid4()),), mode="db")
        assert res.succeeded == 1

    async def test_db_mode_with_audit(self):
        op = AsyncMock()
        op.bulk_check = AsyncMock(
            return_value=BulkNodeCheckResultDTO(
                total=1, succeeded=1, failed=0, node_ids=()
            )
        )
        audit = AsyncMock()
        audit.log = AsyncMock(return_value=None)
        svc = _make_service(operator=op, audit_service=audit)
        await svc.bulk_check(node_ids=(str(uuid.uuid4()),), mode="db")
        audit.log.assert_awaited_once()

    async def test_ssh_fallback_missing_deps(self):
        svc = NodeBulkOperationService(
            operator=AsyncMock(),
            audit_service=None,
            node_reader=None,
            connector_factory=None,
            credential_cipher=None,
        )
        op = AsyncMock()
        op.bulk_check = AsyncMock(
            return_value=BulkNodeCheckResultDTO(
                total=0, succeeded=0, failed=0, node_ids=()
            )
        )
        svc._operator = op
        res = await svc.bulk_check(node_ids=(str(uuid.uuid4()),), mode="ssh")
        assert res.total == 0

    async def test_ssh_invalid_uuid(self):
        svc = _make_service()
        svc._node_reader.get_connection = AsyncMock(return_value=None)
        # Mock status writer to avoid DB
        svc._status_writer.update_node_status = AsyncMock(return_value=None)
        svc._status_history_writer.create_history = AsyncMock(return_value=None)
        # Mock node_view_reader for old_status
        svc._node_view_reader.get_node = AsyncMock(
            return_value=MagicMock(status="active")
        )
        with patch(
            "app.application.services.ssh_executor.build_ssh_connector"
        ):
            res = await svc.bulk_check(node_ids=("not-a-uuid",), mode="ssh")
            assert res.failed == 1

    async def test_ssh_node_not_found(self):
        svc = _make_service()
        svc._node_reader.get_connection = AsyncMock(return_value=None)
        svc._status_writer.update_node_status = AsyncMock(return_value=None)
        svc._status_history_writer.create_history = AsyncMock(return_value=None)
        svc._node_view_reader.get_node = AsyncMock(return_value=None)
        # Need to mock uuid parsing to succeed but node None
        uid = str(uuid.uuid4())
        svc._node_reader.get_connection = AsyncMock(return_value=None)
        res = await svc.bulk_check(node_ids=(uid,), mode="ssh")
        assert res.failed == 1

    async def test_ssh_success(self):

        svc = _make_service()
        uid = uuid.uuid4()
        dto = NodeConnectionDTO(
            id=uid,
            name="n",
            endpoint=NodeEndpoint(host="1.2.3.4", port=22),
            credentials=NodeCredentials(username="u", password="p"),
        )
        svc._node_reader.get_connection = AsyncMock(return_value=dto)
        svc._node_view_reader.get_node = AsyncMock(
            return_value=MagicMock(status="active")
        )
        svc._status_writer.update_node_status = AsyncMock(return_value=None)
        svc._status_history_writer.create_history = AsyncMock(return_value=None)
        mock_connector = AsyncMock()
        mock_connector.__aenter__ = AsyncMock(return_value=mock_connector)
        mock_connector.__aexit__ = AsyncMock(return_value=None)
        mock_connector.execute_command = AsyncMock(
            return_value=MagicMock(stdout="ok", stderr="", exit_code=0)
        )
        with patch(
            "app.application.services.ssh_executor.build_ssh_connector",
            return_value=mock_connector,
        ):
            cipher = MagicMock()
            cipher.decrypt_password = MagicMock(return_value="p")
            cipher.decrypt_private_key = MagicMock(return_value=None)
            cipher.decrypt_passphrase = MagicMock(return_value=None)
            svc._credential_cipher = cipher
            res = await svc.bulk_check(node_ids=(str(uid),), mode="ssh")
            assert res.succeeded == 1

    async def test_ssh_connection_failed(self):
        svc = _make_service()
        uid = uuid.uuid4()

        dto = NodeConnectionDTO(
            id=uid,
            name="n",
            endpoint=NodeEndpoint(host="1.2.3.4", port=22),
            credentials=NodeCredentials(username="u", password="p"),
        )
        svc._node_reader.get_connection = AsyncMock(return_value=dto)
        svc._node_view_reader.get_node = AsyncMock(
            return_value=MagicMock(status="active")
        )
        svc._status_writer.update_node_status = AsyncMock(return_value=None)
        svc._status_history_writer.create_history = AsyncMock(return_value=None)
        mock_connector = AsyncMock()
        mock_connector.__aenter__ = AsyncMock(return_value=mock_connector)
        mock_connector.__aexit__ = AsyncMock(return_value=None)
        mock_connector.execute_command = AsyncMock(
            side_effect=ConnectionFailedError("ssh fail")
        )
        with patch(
            "app.application.services.ssh_executor.build_ssh_connector",
            return_value=mock_connector,
        ):
            cipher = MagicMock()
            cipher.decrypt_password = MagicMock(return_value="p")
            cipher.decrypt_private_key = MagicMock(return_value=None)
            cipher.decrypt_passphrase = MagicMock(return_value=None)
            svc._credential_cipher = cipher
            res = await svc.bulk_check(node_ids=(str(uid),), mode="ssh")
            assert res.failed == 1

    async def test_ssh_generic_exception(self):
        svc = _make_service()
        uid = uuid.uuid4()

        dto = NodeConnectionDTO(
            id=uid,
            name="n",
            endpoint=NodeEndpoint(host="1.2.3.4", port=22),
            credentials=NodeCredentials(username="u", password="p"),
        )
        svc._node_reader.get_connection = AsyncMock(return_value=dto)
        svc._node_view_reader.get_node = AsyncMock(
            return_value=MagicMock(status="active")
        )
        svc._status_writer.update_node_status = AsyncMock(return_value=None)
        svc._status_history_writer.create_history = AsyncMock(return_value=None)
        mock_connector = AsyncMock()
        mock_connector.__aenter__ = AsyncMock(return_value=mock_connector)
        mock_connector.__aexit__ = AsyncMock(return_value=None)
        mock_connector.execute_command = AsyncMock(side_effect=RuntimeError("generic"))
        with patch(
            "app.application.services.ssh_executor.build_ssh_connector",
            return_value=mock_connector,
        ):
            cipher = MagicMock()
            cipher.decrypt_password = MagicMock(return_value="p")
            cipher.decrypt_private_key = MagicMock(return_value=None)
            cipher.decrypt_passphrase = MagicMock(return_value=None)
            svc._credential_cipher = cipher
            res = await svc.bulk_check(node_ids=(str(uid),), mode="ssh")
            assert res.failed == 1
