"""Coverage – node services (metrics, management, bulk command)."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.application.dto.node_connection import NodeConnectionDTO
from app.application.dto.node_management import NodeCreateDTO, NodeUpdateDTO
from app.application.dto.node_metrics import NodeMetricsDTO
from app.application.dto.node_view import NodeViewDTO
from app.application.dto.value_objects import NodeCredentials, NodeEndpoint
from app.application.services.node_bulk_command_service import NodeBulkCommandService
from app.application.services.node_management_service import NodeManagementService
from app.application.services.node_metrics_service import NodeMetricsService
from app.core.exceptions import NodeNotFoundError


class TestNodeMetricsService:
    @pytest.mark.asyncio
    async def test_collect_success(self) -> None:
        node = NodeConnectionDTO(
            id=uuid.uuid4(),
            name="n",
            endpoint=NodeEndpoint(host="h", port=22, connection_type="ssh"),
            credentials=NodeCredentials(
                username="root", password="p", ssh_key="", passphrase=""
            ),
        )
        reader = AsyncMock()
        reader.get_connection.return_value = node
        cipher = MagicMock()
        cipher.decrypt.side_effect = lambda v: v or ""
        connector = AsyncMock()
        # cpu vmstat, nproc, mem, disk, load, uptime
        connector.execute_command = AsyncMock(
            side_effect=[
                ("50.0\n", "", 0),  # vmstat
                ("4\n", "", 0),  # nproc
                ("100 50 50\n", "", 0),  # mem
                ("100 50 50\n", "", 0),  # disk
                ("0.1 0.2 0.3\n", "", 0),  # load
                ("2026-01-01 00:00:00\n", "", 0),  # uptime
            ]
        )
        connector.__aenter__ = AsyncMock(return_value=connector)
        connector.__aexit__ = AsyncMock(return_value=False)
        factory = MagicMock()
        factory.create_ssh.return_value = connector
        svc = NodeMetricsService(reader, cipher, factory)
        result = await svc.collect(node.id)
        assert isinstance(result, NodeMetricsDTO)
        assert result.cpu.cores == 4

    @pytest.mark.asyncio
    async def test_collect_fallback_cpu(self) -> None:
        node = NodeConnectionDTO(
            id=uuid.uuid4(),
            name="n",
            endpoint=NodeEndpoint(host="h", port=22, connection_type="ssh"),
            credentials=NodeCredentials(username="root"),
        )
        reader = AsyncMock()
        reader.get_connection.return_value = node
        cipher = MagicMock()
        cipher.decrypt.return_value = ""
        connector = AsyncMock()
        # vmstat fails, fallback proc_stat, nproc invalid, etc.
        connector.execute_command = AsyncMock(
            side_effect=[
                ("", "", 1),  # vmstat fails
                ("cpu  100 0 50 200 10 0 0\n", "", 0),  # proc stat s1
                ("", "", 0),  # sleep 1
                ("cpu  110 0 55 210 10 0 0\n", "", 0),  # proc stat s2
                ("notanint\n", "", 0),  # nproc invalid
                ("100 50 50\n", "", 0),  # mem
                ("100 50 50\n", "", 0),  # disk
                ("bad\n", "", 0),  # load bad
                ("\n", "", 0),  # uptime empty
            ]
        )
        connector.__aenter__ = AsyncMock(return_value=connector)
        connector.__aexit__ = AsyncMock(return_value=False)
        factory = MagicMock()
        factory.create_ssh.return_value = connector
        svc = NodeMetricsService(reader, cipher, factory)
        result = await svc.get_node_metrics(node.id)
        assert result.uptime_since == "unknown"

    @pytest.mark.asyncio
    async def test_collect_node_not_found(self) -> None:
        reader = AsyncMock()
        reader.get_connection.return_value = None
        svc = NodeMetricsService(reader, MagicMock(), MagicMock())

        with pytest.raises(NodeNotFoundError):
            await svc.collect(uuid.uuid4())


class TestNodeManagementService:
    @pytest.mark.asyncio
    async def test_create_node_encrypts_and_logs(self) -> None:
        reader = AsyncMock()
        writer = AsyncMock()
        cipher = MagicMock()
        cipher.encrypt.side_effect = lambda v: f"enc_{v}" if v else v
        audit = AsyncMock()
        known = AsyncMock()
        known.ensure_host = AsyncMock()
        svc = NodeManagementService(reader, writer, cipher, audit, None, known)
        node = NodeViewDTO(
            id=uuid.uuid4(),
            name="n",
            status="active",
            username="root",
            tags=(),
            created_at=__import__("datetime").datetime.now(__import__("datetime").UTC),
            updated_at=__import__("datetime").datetime.now(__import__("datetime").UTC),
            endpoint=NodeEndpoint(host="h", port=22, connection_type="ssh"),
        )
        writer.create_node.return_value = node
        dto = NodeCreateDTO(
            name="n",
            endpoint=NodeEndpoint(host="h", port=22, connection_type="ssh"),
            credentials=NodeCredentials(
                username="root", password="secret", ssh_key="key", passphrase="pp"
            ),
            tags=(),
        )
        res = await svc.create_node(dto)
        assert res.name == "n"
        writer.create_node.assert_awaited_once()
        # check encrypt called
        assert cipher.encrypt.called

    @pytest.mark.asyncio
    async def test_update_node_with_host_change(self) -> None:
        reader = AsyncMock()
        writer = AsyncMock()
        cipher = MagicMock()
        cipher.encrypt.side_effect = lambda v: v
        known = AsyncMock()
        known.ensure_host = AsyncMock()
        status_writer = AsyncMock()
        svc = NodeManagementService(reader, writer, cipher, None, status_writer, known)
        existing = NodeViewDTO(
            id=uuid.uuid4(),
            name="n",
            status="active",
            username="root",
            tags=(),
            created_at=__import__("datetime").datetime.now(__import__("datetime").UTC),
            updated_at=__import__("datetime").datetime.now(__import__("datetime").UTC),
            endpoint=NodeEndpoint(host="old", port=22, connection_type="ssh"),
        )
        reader.get_node.return_value = existing
        updated = NodeViewDTO(
            id=existing.id,
            name="n",
            status="active",
            username="root",
            tags=(),
            created_at=existing.created_at,
            updated_at=existing.updated_at,
            endpoint=NodeEndpoint(host="new", port=2222, connection_type="ssh"),
        )
        writer.update_node.return_value = updated
        dto = NodeUpdateDTO(
            changes=(
                ("host", "new"),
                ("port", 2222),
                ("status", "active"),
                ("password", "secret"),
            )
        )
        res = await svc.update_node(existing.id, dto)
        assert res.id == existing.id
        status_writer.save.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_delete_node(self) -> None:
        reader = AsyncMock()
        writer = AsyncMock()
        cipher = MagicMock()
        svc = NodeManagementService(reader, writer, cipher)
        node = NodeViewDTO(
            id=uuid.uuid4(),
            name="n",
            status="active",
            username="root",
            tags=(),
            created_at=__import__("datetime").datetime.now(__import__("datetime").UTC),
            updated_at=__import__("datetime").datetime.now(__import__("datetime").UTC),
            endpoint=NodeEndpoint(host="h", port=22, connection_type="ssh"),
        )
        reader.get_node.return_value = node
        res = await svc.delete_node(node.id)
        assert res is True

    @pytest.mark.asyncio
    async def test_add_and_remove_tag(self) -> None:
        reader = AsyncMock()
        writer = AsyncMock()
        cipher = MagicMock()
        svc = NodeManagementService(reader, writer, cipher)
        node = NodeViewDTO(
            id=uuid.uuid4(),
            name="n",
            status="active",
            username="root",
            tags=("a",),
            created_at=__import__("datetime").datetime.now(__import__("datetime").UTC),
            updated_at=__import__("datetime").datetime.now(__import__("datetime").UTC),
            endpoint=NodeEndpoint(host="h", port=22, connection_type="ssh"),
        )
        reader.get_node.return_value = node
        from app.application.dto.node_management import NodeTagDTO

        writer.update_node.return_value = node
        await svc.add_tag(node.id, NodeTagDTO(tag="b"))
        await svc.remove_tag(node.id, NodeTagDTO(tag="a"))
        assert writer.update_node.await_count == 2

    @pytest.mark.asyncio
    async def test_get_node_and_list(self) -> None:
        reader = AsyncMock()
        writer = AsyncMock()
        cipher = MagicMock()
        svc = NodeManagementService(reader, writer, cipher)
        node = NodeViewDTO(
            id=uuid.uuid4(),
            name="n",
            status="active",
            username="root",
            tags=(),
            created_at=__import__("datetime").datetime.now(__import__("datetime").UTC),
            updated_at=__import__("datetime").datetime.now(__import__("datetime").UTC),
            endpoint=NodeEndpoint(host="h", port=22, connection_type="ssh"),
        )
        reader.get_node.return_value = node
        res = await svc.get_node(node.id)
        assert res.id == node.id

        reader.list_nodes.return_value = MagicMock(items=[node], total=1)
        reader.list_tags.return_value = ["a", "b"]
        reader.list_nodes_cursor.return_value = MagicMock(
            items=[node], next_cursor=None, has_more=False
        )
        items, total = await svc.get_all_nodes(page=1, size=10, tags=["a"], search="n")
        assert total == 1
        items2, nxt, has_more = await svc.get_nodes_cursor(limit=5)
        assert len(items2) == 1
        items3, total3 = await svc.get_nodes_by_tags(["a"])
        assert total3 == 1
        tags = await svc.get_all_tags()
        assert tags == ["a", "b"]

    @pytest.mark.asyncio
    async def test_get_node_not_found(self) -> None:
        reader = AsyncMock()
        writer = AsyncMock()
        cipher = MagicMock()
        svc = NodeManagementService(reader, writer, cipher)
        reader.get_node.return_value = None

        with pytest.raises(NodeNotFoundError):
            await svc.get_node(uuid.uuid4())
        with pytest.raises(NodeNotFoundError):
            await svc.delete_node(uuid.uuid4())
        with pytest.raises(NodeNotFoundError):
            await svc.add_tag(
                uuid.uuid4(),
                __import__(
                    "app.application.dto.node_management", fromlist=["NodeTagDTO"]
                ).NodeTagDTO(tag="x"),
            )
        with pytest.raises(NodeNotFoundError):
            await svc.remove_tag(
                uuid.uuid4(),
                __import__(
                    "app.application.dto.node_management", fromlist=["NodeTagDTO"]
                ).NodeTagDTO(tag="x"),
            )

    @pytest.mark.asyncio
    async def test_has_docker_false_clears_host(self) -> None:
        reader = AsyncMock()
        writer = AsyncMock()
        cipher = MagicMock()
        svc = NodeManagementService(reader, writer, cipher)
        node = NodeViewDTO(
            id=uuid.uuid4(),
            name="n",
            status="active",
            username="root",
            tags=(),
            created_at=__import__("datetime").datetime.now(__import__("datetime").UTC),
            updated_at=__import__("datetime").datetime.now(__import__("datetime").UTC),
            endpoint=NodeEndpoint(
                host="h", port=22, connection_type="ssh", docker_host="tcp://x"
            ),
        )
        writer.update_node.return_value = node
        # has_docker False without docker_host should set docker_host None
        dto = NodeUpdateDTO(changes=(("has_docker", False),))
        await svc.update_node(node.id, dto)
        # check that writer was called with docker_host None
        call = writer.update_node.call_args[0][1]
        d = dict(call.changes)
        assert d["docker_host"] is None
        assert d["has_docker"] is False


class TestNodeBulkCommandService:
    @pytest.mark.asyncio
    async def test_execute_and_validate(self) -> None:
        from app.application.dto.command_execution import BulkCommandRequestDTO

        node = NodeConnectionDTO(
            id=uuid.uuid4(),
            name="n",
            endpoint=NodeEndpoint(host="h", port=22, connection_type="ssh"),
            credentials=NodeCredentials(username="root"),
        )
        reader = AsyncMock()
        reader.get_connection.return_value = node
        # mock resolve_targets to return node
        with patch(
            "app.application.services.node_bulk_command_service.resolve_targets",
            new=AsyncMock(return_value=[node]),
        ):
            cipher = MagicMock()
            cipher.decrypt.return_value = ""
            factory = MagicMock()
            connector = AsyncMock()
            connector.__aenter__ = AsyncMock(return_value=connector)
            connector.__aexit__ = AsyncMock(return_value=False)
            connector.execute_command = AsyncMock(return_value=("ok", "", 0))
            factory.create_ssh.return_value = connector
            # mock execute_ssh and build_ssh_connector
            with patch(
                "app.application.services.node_bulk_command_service.build_ssh_connector",
                return_value=connector,
            ):
                with patch(
                    "app.application.services.node_bulk_command_service.execute_ssh",
                    new=AsyncMock(
                        return_value=MagicMock(stdout="ok", stderr="", exit_code=0)
                    ),
                ):
                    svc = NodeBulkCommandService(reader, cipher, factory, None, None)
                    req = BulkCommandRequestDTO(
                        command="echo hi", node_ids=(node.id,), tags=()
                    )
                    res = await svc.execute(req)
                    assert res.total == 1
                    # validate bulk
                    with patch(
                        "app.application.services.node_bulk_command_service.resolve_targets",
                        new=AsyncMock(return_value=[node]),
                    ):
                        vals = await svc.validate_credentials_bulk(node_ids=[node.id])
                        assert len(vals) == 1
