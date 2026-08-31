"""Tests for remaining low-coverage code — node_management, services, events."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.adapters.persistence.node_management import (
    SqlAlchemyNodeManagementGateway,
)
from app.application.dto.node_management import (
    NodeCursorPageDTO,
    NodeCursorQueryDTO,
)
from app.application.dto.value_objects import NodeCredentials, NodeEndpoint

# ─── NodeManagementGateway ───


class TestNodeManagementGateway:
    def _make_gw(self):
        sm = MagicMock()
        return SqlAlchemyNodeManagementGateway(sm)

    @pytest.mark.asyncio
    async def test_list_nodes_cursor(self) -> None:
        gw = self._make_gw()
        session = AsyncMock()
        session_ctx = AsyncMock()
        session_ctx.__aenter__.return_value = session
        session_ctx.__aexit__.return_value = False
        gw._sessionmaker.return_value = session_ctx

        model = MagicMock()
        model.id = uuid.uuid4()
        model.name = "web"
        model.host = "10.0.0.1"
        model.port = 22
        model.connection_type = "ssh"
        model.status = "active"
        model.username = "root"
        model.docker_host = None
        model.tags = ["prod"]
        model.created_at = datetime.now(UTC)
        model.updated_at = datetime.now(UTC)

        with patch(
            "app.adapters.persistence.node_management.NodeRepository"
        ) as mock_repo:
            repo = mock_repo.return_value
            repo.get_list_cursor = AsyncMock(return_value=[model])

            query = NodeCursorQueryDTO(cursor=None, limit=10)
            result = await gw.list_nodes_cursor(query)
            assert isinstance(result, NodeCursorPageDTO)
            assert len(result.items) == 1

    @pytest.mark.asyncio
    async def test_list_tags(self) -> None:
        gw = self._make_gw()
        session = AsyncMock()
        session_ctx = AsyncMock()
        session_ctx.__aenter__.return_value = session
        session_ctx.__aexit__.return_value = False
        gw._sessionmaker.return_value = session_ctx

        with patch(
            "app.adapters.persistence.node_management.NodeRepository"
        ) as mock_repo:
            repo = mock_repo.return_value
            repo.get_all_tags = AsyncMock(return_value=["prod", "dev"])
            result = await gw.list_tags()
            assert result == ["prod", "dev"]

    @pytest.mark.asyncio
    async def test_create_node(self) -> None:
        gw = self._make_gw()
        session = AsyncMock()
        session_ctx = AsyncMock()
        session_ctx.__aenter__.return_value = session
        session_ctx.__aexit__.return_value = False
        gw._sessionmaker.begin.return_value = session_ctx

        from app.application.dto.node_management import NodeCreateDTO

        model = MagicMock()
        model.id = uuid.uuid4()
        model.name = "new-node"
        model.host = "10.0.0.2"
        model.port = 22
        model.connection_type = "ssh"
        model.status = "active"
        model.username = "root"
        model.docker_host = None
        model.tags = []
        model.created_at = datetime.now(UTC)
        model.updated_at = datetime.now(UTC)

        with patch(
            "app.adapters.persistence.node_management.NodeRepository"
        ) as mock_repo:
            repo = mock_repo.return_value
            repo.create = AsyncMock(return_value=model)

            data = NodeCreateDTO(
                name="new-node",
                tags=(),
                endpoint=NodeEndpoint(
                    host="10.0.0.2", port=22, connection_type="ssh", docker_host=None
                ),
                credentials=NodeCredentials(
                    username="root", password=None, ssh_key=None
                ),
            )
            result = await gw.create_node(data)
            assert result.name == "new-node"

    @pytest.mark.asyncio
    async def test_update_node(self) -> None:
        gw = self._make_gw()
        session = AsyncMock()
        session_ctx = AsyncMock()
        session_ctx.__aenter__.return_value = session
        session_ctx.__aexit__.return_value = False
        gw._sessionmaker.begin.return_value = session_ctx

        model = MagicMock()
        model.id = uuid.uuid4()
        model.name = "updated"
        model.host = "10.0.0.1"
        model.port = 22
        model.connection_type = "ssh"
        model.status = "active"
        model.username = "root"
        model.docker_host = None
        model.tags = []
        model.created_at = datetime.now(UTC)
        model.updated_at = datetime.now(UTC)

        with patch(
            "app.adapters.persistence.node_management.NodeRepository"
        ) as mock_repo:
            repo = mock_repo.return_value
            repo.update = AsyncMock(return_value=model)

            from app.application.dto.node_management import NodeUpdateDTO

            data = NodeUpdateDTO(changes=(("name", "updated"),))
            result = await gw.update_node(model.id, data)
            assert result is not None
            assert result.name == "updated"

    @pytest.mark.asyncio
    async def test_delete_node_found(self) -> None:
        gw = self._make_gw()
        session = AsyncMock()
        session_ctx = AsyncMock()
        session_ctx.__aenter__.return_value = session
        session_ctx.__aexit__.return_value = False
        gw._sessionmaker.begin.return_value = session_ctx

        model = MagicMock()

        with patch(
            "app.adapters.persistence.node_management.NodeRepository"
        ) as mock_repo:
            repo = mock_repo.return_value
            repo.get_by_id = AsyncMock(return_value=model)
            result = await gw.delete_node(uuid.uuid4())
            assert result is True

    @pytest.mark.asyncio
    async def test_delete_node_not_found(self) -> None:
        gw = self._make_gw()
        session = AsyncMock()
        session_ctx = AsyncMock()
        session_ctx.__aenter__.return_value = session
        session_ctx.__aexit__.return_value = False
        gw._sessionmaker.begin.return_value = session_ctx

        with patch(
            "app.adapters.persistence.node_management.NodeRepository"
        ) as mock_repo:
            repo = mock_repo.return_value
            repo.get_by_id = AsyncMock(return_value=None)
            result = await gw.delete_node(uuid.uuid4())
            assert result is False

    @pytest.mark.asyncio
    async def test_update_node_status(self) -> None:
        gw = self._make_gw()
        session = AsyncMock()
        session_ctx = AsyncMock()
        session_ctx.__aenter__.return_value = session
        session_ctx.__aexit__.return_value = False
        gw._sessionmaker.begin.return_value = session_ctx

        model = MagicMock()
        model.id = uuid.uuid4()
        model.name = "node"
        model.host = "10.0.0.1"
        model.port = 22
        model.connection_type = "ssh"
        model.status = "unreachable"
        model.username = "root"
        model.docker_host = None
        model.tags = []
        model.created_at = datetime.now(UTC)
        model.updated_at = datetime.now(UTC)

        with patch(
            "app.adapters.persistence.node_management.NodeRepository"
        ) as mock_repo:
            repo = mock_repo.return_value
            repo.update = AsyncMock(return_value=model)
            result = await gw.update_node_status(model.id, "unreachable")
            assert result is not None
            assert result.status == "unreachable"


# ─── SSE events endpoint ───


class TestSseEvents:
    @pytest.mark.asyncio
    async def test_event_generator_yields_keepalive(self) -> None:
        from app.application.services.sse_broadcaster import SseBroadcaster

        bc = SseBroadcaster()
        sub_id, queue = bc.subscribe()

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr("app.api.v2.events.get_sse_broadcaster", lambda: bc)

            from app.api.v2.events import _event_generator

            gen = _event_generator(sub_id, queue)
            first = await gen.__anext__()
            assert ": keepalive" in first or ":" in first
            await gen.aclose()

    @pytest.mark.asyncio
    async def test_event_generator_yields_event(self) -> None:
        from app.application.services.sse_broadcaster import SseBroadcaster

        bc = SseBroadcaster()
        sub_id, queue = bc.subscribe()
        bc.publish("test.event", {"key": "value"})

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr("app.api.v2.events.get_sse_broadcaster", lambda: bc)

            from app.api.v2.events import _event_generator

            gen = _event_generator(sub_id, queue)
            await gen.__anext__()  # initial comment
            second = await gen.__anext__()  # the actual event
            assert "test.event" in second
            await gen.aclose()

    @pytest.mark.asyncio
    async def test_event_generator_handles_none_event(self) -> None:
        from app.application.services.sse_broadcaster import SseBroadcaster

        bc = SseBroadcaster()
        sub_id, queue = bc.subscribe()
        queue.put_nowait(None)

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr("app.api.v2.events.get_sse_broadcaster", lambda: bc)

            from app.api.v2.events import _event_generator

            gen = _event_generator(sub_id, queue)
            first = await gen.__anext__()
            assert ":" in first
            # The generator should stop after None
            with pytest.raises(StopAsyncIteration):
                await gen.__anext__()
