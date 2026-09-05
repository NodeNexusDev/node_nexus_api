# ruff: noqa: E501
"""Extra coverage for node status audithonest branches."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.application.dto.node_connection import NodeConnectionDTO
from app.application.dto.node_management import NodeUpdateDTO
from app.application.dto.node_view import NodeViewDTO
from app.application.dto.value_objects import NodeCredentials, NodeEndpoint
from app.application.services.node_bulk_operation_service import (
    NodeBulkOperationService,
)
from app.application.services.node_command_service import NodeCommandService
from app.application.services.node_management_service import NodeManagementService
from app.core.exceptions import CredentialDecryptionError


def _make_bulk_service(**overrides):
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


def _make_node_conn(uid):
    return NodeConnectionDTO(
        id=uid,
        name="n",
        endpoint=NodeEndpoint(host="1.2.3.4", port=22),
        credentials=NodeCredentials(username="u", password="p"),
    )


class TestBulkCheckExtra:
    @pytest.mark.asyncio
    async def test_credential_error_maps_to_error_status(self):
        svc = _make_bulk_service()
        uid = uuid.uuid4()
        svc._node_reader.get_connection = AsyncMock(return_value=_make_node_conn(uid))
        svc._node_view_reader.get_node = AsyncMock(
            return_value=MagicMock(status="active")
        )
        svc._status_writer.update_node_status = AsyncMock(return_value=MagicMock())
        mock_conn = AsyncMock()
        mock_conn.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_conn.__aexit__ = AsyncMock(return_value=None)
        mock_conn.execute_command = AsyncMock(
            side_effect=CredentialDecryptionError("bad cred")
        )
        with patch(
            "app.application.services.ssh_executor.build_ssh_connector",
            return_value=mock_conn,
        ):
            res = await svc.bulk_check(node_ids=(str(uid),), mode="ssh")
            assert res.failed == 1
            assert res.details[0].new_status == "error"
            assert "bad cred" in (res.details[0].error or "")

    @pytest.mark.asyncio
    async def test_history_skipped_noop(self):
        svc = _make_bulk_service()
        uid = uuid.uuid4()
        svc._node_reader.get_connection = AsyncMock(return_value=_make_node_conn(uid))
        # old status same as new (active)
        svc._node_view_reader.get_node = AsyncMock(
            return_value=MagicMock(status="active")
        )
        svc._status_writer.update_node_status = AsyncMock(return_value=MagicMock())
        svc._status_history_writer.save = AsyncMock()
        mock_conn = AsyncMock()
        mock_conn.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_conn.__aexit__ = AsyncMock(return_value=None)
        mock_conn.execute_command = AsyncMock(
            return_value=MagicMock(stdout="ok", stderr="", exit_code=0)
        )
        with patch(
            "app.application.services.ssh_executor.build_ssh_connector",
            return_value=mock_conn,
        ):
            res = await svc.bulk_check(node_ids=(str(uid),), mode="ssh")
            assert res.succeeded == 1
            # history should not be saved when old==new
            svc._status_history_writer.save.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_status_not_found(self):
        svc = _make_bulk_service()
        uid = uuid.uuid4()
        svc._node_reader.get_connection = AsyncMock(return_value=_make_node_conn(uid))
        svc._node_view_reader.get_node = AsyncMock(
            return_value=MagicMock(status="active")
        )
        svc._status_writer.update_node_status = AsyncMock(return_value=None)
        mock_conn = AsyncMock()
        mock_conn.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_conn.__aexit__ = AsyncMock(return_value=None)
        mock_conn.execute_command = AsyncMock(
            return_value=MagicMock(stdout="ok", stderr="", exit_code=0)
        )
        with patch(
            "app.application.services.ssh_executor.build_ssh_connector",
            return_value=mock_conn,
        ):
            res = await svc.bulk_check(node_ids=(str(uid),), mode="ssh")
            assert res.failed == 1
            assert "Node not found on status update" in (res.details[0].error or "")

    @pytest.mark.asyncio
    async def test_status_update_failed_exception(self):
        svc = _make_bulk_service()
        uid = uuid.uuid4()
        svc._node_reader.get_connection = AsyncMock(return_value=_make_node_conn(uid))
        svc._node_view_reader.get_node = AsyncMock(
            return_value=MagicMock(status="active")
        )
        svc._status_writer.update_node_status = AsyncMock(
            side_effect=RuntimeError("db down")
        )
        mock_conn = AsyncMock()
        mock_conn.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_conn.__aexit__ = AsyncMock(return_value=None)
        mock_conn.execute_command = AsyncMock(
            return_value=MagicMock(stdout="ok", stderr="", exit_code=0)
        )
        with patch(
            "app.application.services.ssh_executor.build_ssh_connector",
            return_value=mock_conn,
        ):
            res = await svc.bulk_check(node_ids=(str(uid),), mode="ssh")
            assert res.failed == 1
            assert "Status update failed" in (res.details[0].error or "")

    @pytest.mark.asyncio
    async def test_history_save_failed(self):
        svc = _make_bulk_service()
        uid = uuid.uuid4()
        svc._node_reader.get_connection = AsyncMock(return_value=_make_node_conn(uid))
        # old unreachable -> new active => should attempt history save
        svc._node_view_reader.get_node = AsyncMock(
            return_value=MagicMock(status="unreachable")
        )
        svc._status_writer.update_node_status = AsyncMock(return_value=MagicMock())
        svc._status_history_writer.save = AsyncMock(
            side_effect=RuntimeError("history fail")
        )
        mock_conn = AsyncMock()
        mock_conn.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_conn.__aexit__ = AsyncMock(return_value=None)
        mock_conn.execute_command = AsyncMock(
            return_value=MagicMock(stdout="ok", stderr="", exit_code=0)
        )
        with patch(
            "app.application.services.ssh_executor.build_ssh_connector",
            return_value=mock_conn,
        ):
            res = await svc.bulk_check(node_ids=(str(uid),), mode="ssh")
            # still succeeded despite history fail (best-effort)
            assert res.succeeded == 1

    @pytest.mark.asyncio
    async def test_old_status_fetch_exception(self):
        svc = _make_bulk_service()
        uid = uuid.uuid4()
        svc._node_reader.get_connection = AsyncMock(return_value=_make_node_conn(uid))
        svc._node_view_reader.get_node = AsyncMock(
            side_effect=RuntimeError("view fail")
        )
        svc._status_writer.update_node_status = AsyncMock(return_value=MagicMock())
        svc._status_history_writer.save = AsyncMock()
        mock_conn = AsyncMock()
        mock_conn.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_conn.__aexit__ = AsyncMock(return_value=None)
        mock_conn.execute_command = AsyncMock(
            return_value=MagicMock(stdout="ok", stderr="", exit_code=0)
        )
        with patch(
            "app.application.services.ssh_executor.build_ssh_connector",
            return_value=mock_conn,
        ):
            res = await svc.bulk_check(node_ids=(str(uid),), mode="ssh")
            assert res.succeeded == 1
            # old_status None, new active => should save history with old None
            svc._status_history_writer.save.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_invalid_uuid_detail(self):
        svc = _make_bulk_service()
        res = await svc.bulk_check(node_ids=("not-a-uuid",), mode="ssh")
        assert res.failed == 1
        assert res.details[0].error == "Invalid node id"
        assert res.details[0].new_status is None

    @pytest.mark.asyncio
    async def test_node_not_found_detail(self):
        svc = _make_bulk_service()
        uid = str(uuid.uuid4())
        svc._node_reader.get_connection = AsyncMock(return_value=None)
        res = await svc.bulk_check(node_ids=(uid,), mode="ssh")
        assert res.failed == 1
        assert res.details[0].error == "Node not found"


class TestNodeCommandExtra:
    @pytest.mark.asyncio
    async def test_credential_error_maps_to_error(self):
        reader = AsyncMock()
        writer = AsyncMock()
        nid = uuid.uuid4()
        from tests.unit.conftest import make_orm_node

        node = make_orm_node(id=nid)
        reader.get_connection.return_value = node
        from unittest.mock import MagicMock

        cipher = MagicMock()
        factory = MagicMock()
        mock_conn = AsyncMock()
        mock_conn.__aenter__ = AsyncMock(side_effect=CredentialDecryptionError("bad"))
        mock_conn.__aexit__ = AsyncMock(return_value=False)
        factory.create_ssh.return_value = mock_conn
        # need build_ssh_connector to return mock_conn; it uses cipher etc.
        # Instead patch build_ssh_connector
        with patch(
            "app.application.services.node_command_service.build_ssh_connector",
            return_value=mock_conn,
        ):
            view = NodeViewDTO(
                id=nid,
                name="n",
                status="error",
                username="root",
                tags=(),
                created_at=__import__("datetime").datetime.now(
                    __import__("datetime").UTC
                ),
                updated_at=__import__("datetime").datetime.now(
                    __import__("datetime").UTC
                ),
                endpoint=NodeEndpoint(host="h", port=22, connection_type="ssh"),
            )
            writer.update_node_status = AsyncMock(return_value=view)
            svc = NodeCommandService(
                reader, writer, cipher, factory, None, None, AsyncMock(), AsyncMock()
            )
            svc._node_view_reader = AsyncMock()
            svc._node_view_reader.get_node = AsyncMock(
                return_value=MagicMock(status="active")
            )
            res = await svc.check_connectivity(nid)
            assert res.status == "error"
            writer.update_node_status.assert_awaited_once_with(nid, "error")

    @pytest.mark.asyncio
    async def test_history_skipped_noop(self):
        reader = AsyncMock()
        writer = AsyncMock()
        nid = uuid.uuid4()
        from tests.unit.conftest import make_orm_node

        node = make_orm_node(id=nid)
        reader.get_connection.return_value = node
        cipher = MagicMock()
        factory = MagicMock()
        mock_conn = AsyncMock()
        mock_conn.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_conn.__aexit__ = AsyncMock(return_value=False)
        mock_conn.execute_command = AsyncMock(return_value=("", "", 0))
        factory.create_ssh.return_value = mock_conn
        with patch(
            "app.application.services.node_command_service.build_ssh_connector",
            return_value=mock_conn,
        ):
            view = NodeViewDTO(
                id=nid,
                name="n",
                status="active",
                username="root",
                tags=(),
                created_at=__import__("datetime").datetime.now(
                    __import__("datetime").UTC
                ),
                updated_at=__import__("datetime").datetime.now(
                    __import__("datetime").UTC
                ),
                endpoint=NodeEndpoint(host="h", port=22, connection_type="ssh"),
            )
            writer.update_node_status = AsyncMock(return_value=view)
            hist = AsyncMock()
            reader_view = AsyncMock()
            reader_view.get_node = AsyncMock(return_value=MagicMock(status="active"))
            svc = NodeCommandService(
                reader, writer, cipher, factory, None, None, hist, reader_view
            )
            res = await svc.check_connectivity(nid)
            assert res.status == "active"
            hist.save.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_history_failed_best_effort(self):
        reader = AsyncMock()
        writer = AsyncMock()
        nid = uuid.uuid4()
        from tests.unit.conftest import make_orm_node

        node = make_orm_node(id=nid)
        reader.get_connection.return_value = node
        cipher = MagicMock()
        factory = MagicMock()
        mock_conn = AsyncMock()
        mock_conn.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_conn.__aexit__ = AsyncMock(return_value=False)
        mock_conn.execute_command = AsyncMock(return_value=("", "", 0))
        factory.create_ssh.return_value = mock_conn
        with patch(
            "app.application.services.node_command_service.build_ssh_connector",
            return_value=mock_conn,
        ):
            view = NodeViewDTO(
                id=nid,
                name="n",
                status="active",
                username="root",
                tags=(),
                created_at=__import__("datetime").datetime.now(
                    __import__("datetime").UTC
                ),
                updated_at=__import__("datetime").datetime.now(
                    __import__("datetime").UTC
                ),
                endpoint=NodeEndpoint(host="h", port=22, connection_type="ssh"),
            )
            writer.update_node_status = AsyncMock(return_value=view)
            hist = AsyncMock()
            hist.save = AsyncMock(side_effect=RuntimeError("hist fail"))
            reader_view = AsyncMock()
            reader_view.get_node = AsyncMock(
                return_value=MagicMock(status="unreachable")
            )
            svc = NodeCommandService(
                reader, writer, cipher, factory, None, None, hist, reader_view
            )
            res = await svc.check_connectivity(nid)
            assert res.status == "active"
            hist.save.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_update_node_status_not_found_raises(self):
        reader = AsyncMock()
        writer = AsyncMock()
        nid = uuid.uuid4()
        from tests.unit.conftest import make_orm_node

        node = make_orm_node(id=nid)
        reader.get_connection.return_value = node
        cipher = MagicMock()
        factory = MagicMock()
        mock_conn = AsyncMock()
        mock_conn.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_conn.__aexit__ = AsyncMock(return_value=False)
        mock_conn.execute_command = AsyncMock(return_value=("", "", 0))
        factory.create_ssh.return_value = mock_conn
        with patch(
            "app.application.services.node_command_service.build_ssh_connector",
            return_value=mock_conn,
        ):
            writer.update_node_status = AsyncMock(return_value=None)
            svc = NodeCommandService(
                reader, writer, cipher, factory, None, None, None, AsyncMock()
            )
            from app.core.exceptions import NodeNotFoundError

            with pytest.raises(NodeNotFoundError):
                await svc.check_connectivity(nid)


class TestManagementHistorySkip:
    @pytest.mark.asyncio
    async def test_history_skipped_when_same_status(self):
        reader = AsyncMock()
        writer = AsyncMock()
        cipher = MagicMock()
        cipher.encrypt.side_effect = lambda v: v
        hist = AsyncMock()
        nid = uuid.uuid4()
        existing = NodeViewDTO(
            id=nid,
            name="n",
            status="active",
            username="root",
            tags=(),
            created_at=__import__("datetime").datetime.now(__import__("datetime").UTC),
            updated_at=__import__("datetime").datetime.now(__import__("datetime").UTC),
            endpoint=NodeEndpoint(host="h", port=22, connection_type="ssh"),
        )
        reader.get_node.return_value = existing
        updated = NodeViewDTO(
            id=nid,
            name="n",
            status="active",
            username="root",
            tags=(),
            created_at=existing.created_at,
            updated_at=existing.updated_at,
            endpoint=NodeEndpoint(host="h", port=22, connection_type="ssh"),
        )
        writer.update_node.return_value = updated
        svc = NodeManagementService(reader, writer, cipher, None, hist)
        dto = NodeUpdateDTO(changes=(("status", "active"),))
        res = await svc.update_node(nid, dto)
        assert res.status == "active"
        hist.save.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_history_failed_best_effort(self):
        reader = AsyncMock()
        writer = AsyncMock()
        cipher = MagicMock()
        cipher.encrypt.side_effect = lambda v: v
        hist = AsyncMock()
        hist.save = AsyncMock(side_effect=RuntimeError("fail"))
        nid = uuid.uuid4()
        existing = NodeViewDTO(
            id=nid,
            name="n",
            status="active",
            username="root",
            tags=(),
            created_at=__import__("datetime").datetime.now(__import__("datetime").UTC),
            updated_at=__import__("datetime").datetime.now(__import__("datetime").UTC),
            endpoint=NodeEndpoint(host="h", port=22, connection_type="ssh"),
        )
        reader.get_node.return_value = existing
        updated = NodeViewDTO(
            id=nid,
            name="n",
            status="error",
            username="root",
            tags=(),
            created_at=existing.created_at,
            updated_at=existing.updated_at,
            endpoint=NodeEndpoint(host="h", port=22, connection_type="ssh"),
        )
        writer.update_node.return_value = updated
        svc = NodeManagementService(reader, writer, cipher, None, hist)
        dto = NodeUpdateDTO(changes=(("status", "error"),))
        res = await svc.update_node(nid, dto)
        assert res.status == "error"
        hist.save.assert_awaited_once()
