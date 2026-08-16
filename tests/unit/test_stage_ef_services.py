"""Tests for Stage E/F services: favorite, note, tag, stats, export, sse."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest

from app.application.dto.execution_stats import ExecutionStatsDTO
from app.application.dto.favorite import FavoriteCreateDTO, FavoriteDTO
from app.application.dto.global_search import (
    GlobalSearchResultDTO,
    SearchResultItemDTO,
)
from app.application.dto.note import NoteCreateDTO, NoteDTO, NoteUpdateDTO
from app.application.services.dashboard_metrics_service import (
    DashboardMetricsService,
)
from app.application.services.execution_stats_service import ExecutionStatsService
from app.application.services.export_service import ExportService
from app.application.services.favorite_service import FavoriteService
from app.application.services.global_search_service import GlobalSearchService
from app.application.services.note_service import NoteService
from app.application.services.sse_broadcaster import SseBroadcaster, SseEvent
from app.application.services.tag_management_service import TagManagementService
from app.core.exceptions import FavoriteNotFoundError, NoteNotFoundError

# ─── FavoriteService ───


class TestFavoriteService:
    @pytest.mark.asyncio
    async def test_list_favorites(self) -> None:
        reader = AsyncMock()
        reader.list_favorites.return_value = ([], 0)
        writer = AsyncMock()
        svc = FavoriteService(reader=reader, writer=writer)

        items, total = await svc.list_favorites(target_type="command", page=1, size=10)
        assert total == 0
        reader.list_favorites.assert_awaited_once_with(
            target_type="command", offset=0, limit=10
        )

    @pytest.mark.asyncio
    async def test_list_favorites_page2(self) -> None:
        reader = AsyncMock()
        reader.list_favorites.return_value = ([], 0)
        writer = AsyncMock()
        svc = FavoriteService(reader=reader, writer=writer)

        await svc.list_favorites(page=2, size=5)
        reader.list_favorites.assert_awaited_once_with(
            target_type=None, offset=5, limit=5
        )

    @pytest.mark.asyncio
    async def test_add_favorite(self) -> None:
        reader = AsyncMock()
        writer = AsyncMock()
        expected = FavoriteDTO(
            id=uuid.uuid4(),
            target_type="command",
            target_id=uuid.uuid4(),
            note=None,
            created_at=datetime.now(UTC),
        )
        writer.add_favorite.return_value = expected
        svc = FavoriteService(reader=reader, writer=writer)

        data = FavoriteCreateDTO(target_type="command", target_id=uuid.uuid4())
        result = await svc.add_favorite(data)
        assert result == expected

    @pytest.mark.asyncio
    async def test_remove_favorite_success(self) -> None:
        reader = AsyncMock()
        writer = AsyncMock()
        writer.remove_favorite.return_value = True
        svc = FavoriteService(reader=reader, writer=writer)

        result = await svc.remove_favorite("command", str(uuid.uuid4()))
        assert result is True

    @pytest.mark.asyncio
    async def test_remove_favorite_not_found(self) -> None:
        reader = AsyncMock()
        writer = AsyncMock()
        writer.remove_favorite.return_value = False
        svc = FavoriteService(reader=reader, writer=writer)

        with pytest.raises(FavoriteNotFoundError):
            await svc.remove_favorite("command", str(uuid.uuid4()))


# ─── NoteService ───


class TestNoteService:
    @pytest.mark.asyncio
    async def test_list_notes(self) -> None:
        reader = AsyncMock()
        reader.list_notes.return_value = []
        writer = AsyncMock()
        svc = NoteService(reader=reader, writer=writer)

        result = await svc.list_notes("command", str(uuid.uuid4()))
        assert result == []

    @pytest.mark.asyncio
    async def test_get_note_found(self) -> None:
        reader = AsyncMock()
        expected = NoteDTO(
            id=uuid.uuid4(),
            target_type="command",
            target_id=uuid.uuid4(),
            content="hi",
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        reader.get_note.return_value = expected
        writer = AsyncMock()
        svc = NoteService(reader=reader, writer=writer)

        result = await svc.get_note(str(expected.id))
        assert result == expected

    @pytest.mark.asyncio
    async def test_get_note_not_found(self) -> None:
        reader = AsyncMock()
        reader.get_note.return_value = None
        writer = AsyncMock()
        svc = NoteService(reader=reader, writer=writer)

        with pytest.raises(NoteNotFoundError):
            await svc.get_note(str(uuid.uuid4()))

    @pytest.mark.asyncio
    async def test_create_note(self) -> None:
        reader = AsyncMock()
        writer = AsyncMock()
        expected = NoteDTO(
            id=uuid.uuid4(),
            target_type="node",
            target_id=uuid.uuid4(),
            content="test",
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        writer.create_note.return_value = expected
        svc = NoteService(reader=reader, writer=writer)

        result = await svc.create_note(
            NoteCreateDTO(target_type="node", target_id=uuid.uuid4(), content="test")
        )
        assert result == expected

    @pytest.mark.asyncio
    async def test_update_note_found(self) -> None:
        reader = AsyncMock()
        writer = AsyncMock()
        expected = NoteDTO(
            id=uuid.uuid4(),
            target_type="node",
            target_id=uuid.uuid4(),
            content="updated",
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        writer.update_note.return_value = expected
        svc = NoteService(reader=reader, writer=writer)

        result = await svc.update_note(
            str(expected.id), NoteUpdateDTO(content="updated")
        )
        assert result.content == "updated"

    @pytest.mark.asyncio
    async def test_update_note_not_found(self) -> None:
        reader = AsyncMock()
        writer = AsyncMock()
        writer.update_note.return_value = None
        svc = NoteService(reader=reader, writer=writer)

        with pytest.raises(NoteNotFoundError):
            await svc.update_note(str(uuid.uuid4()), NoteUpdateDTO(content="x"))

    @pytest.mark.asyncio
    async def test_delete_note_found(self) -> None:
        reader = AsyncMock()
        writer = AsyncMock()
        writer.delete_note.return_value = True
        svc = NoteService(reader=reader, writer=writer)

        result = await svc.delete_note(str(uuid.uuid4()))
        assert result is True

    @pytest.mark.asyncio
    async def test_delete_note_not_found(self) -> None:
        reader = AsyncMock()
        writer = AsyncMock()
        writer.delete_note.return_value = False
        svc = NoteService(reader=reader, writer=writer)

        with pytest.raises(NoteNotFoundError):
            await svc.delete_note(str(uuid.uuid4()))


# ─── TagManagementService ───


class TestTagManagementService:
    @pytest.mark.asyncio
    async def test_rename_tag(self) -> None:
        tag_manager = AsyncMock()
        tag_manager.rename_tag.return_value = 5
        svc = TagManagementService(tag_manager=tag_manager)

        result = await svc.rename_tag("old", "new")
        assert result == 5
        tag_manager.rename_tag.assert_awaited_once_with("old", "new")

    @pytest.mark.asyncio
    async def test_delete_tag(self) -> None:
        tag_manager = AsyncMock()
        tag_manager.delete_tag.return_value = 3
        svc = TagManagementService(tag_manager=tag_manager)

        result = await svc.delete_tag("toremove")
        assert result == 3
        tag_manager.delete_tag.assert_awaited_once_with("toremove")


# ─── ExecutionStatsService ───


class TestExecutionStatsService:
    @pytest.mark.asyncio
    async def test_get_command_stats(self) -> None:
        reader = AsyncMock()
        expected = ExecutionStatsDTO(
            total=10,
            successful=8,
            failed=2,
            success_rate=0.8,
            avg_duration_ms=100,
            min_duration_ms=50,
            max_duration_ms=200,
            last_executed_at=datetime.now(UTC),
        )
        reader.get_command_stats.return_value = expected
        svc = ExecutionStatsService(reader=reader)

        result = await svc.get_command_stats(
            command_id=uuid.uuid4(),
            date_from=datetime(2026, 1, 1, tzinfo=UTC),
            date_to=datetime(2026, 12, 31, tzinfo=UTC),
        )
        assert result.total == 10
        reader.get_command_stats.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_get_script_stats(self) -> None:
        reader = AsyncMock()
        expected = ExecutionStatsDTO(
            total=5,
            successful=5,
            failed=0,
            success_rate=1.0,
            avg_duration_ms=80,
            min_duration_ms=60,
            max_duration_ms=100,
            last_executed_at=None,
        )
        reader.get_script_stats.return_value = expected
        svc = ExecutionStatsService(reader=reader)

        result = await svc.get_script_stats(script_id=uuid.uuid4())
        assert result.total == 5

    @pytest.mark.asyncio
    async def test_get_node_command_stats(self) -> None:
        reader = AsyncMock()
        expected = ExecutionStatsDTO(
            total=3,
            successful=2,
            failed=1,
            success_rate=0.667,
            avg_duration_ms=150,
            min_duration_ms=100,
            max_duration_ms=200,
            last_executed_at=None,
        )
        reader.get_node_command_stats.return_value = expected
        svc = ExecutionStatsService(reader=reader)

        result = await svc.get_node_command_stats(node_id=uuid.uuid4())
        assert result.total == 3

    @pytest.mark.asyncio
    async def test_get_node_script_stats(self) -> None:
        reader = AsyncMock()
        expected = ExecutionStatsDTO(
            total=7,
            successful=6,
            failed=1,
            success_rate=0.857,
            avg_duration_ms=90,
            min_duration_ms=40,
            max_duration_ms=150,
            last_executed_at=None,
        )
        reader.get_node_script_stats.return_value = expected
        svc = ExecutionStatsService(reader=reader)

        result = await svc.get_node_script_stats(node_id=uuid.uuid4())
        assert result.total == 7


# ─── ExportService ───


class TestExportService:
    @pytest.mark.asyncio
    async def test_export_audit(self) -> None:
        exporter = AsyncMock()
        exporter.export_audit.return_value = []
        svc = ExportService(audit_exporter=exporter)

        result = await svc.export_audit(fmt="csv")
        assert result == []
        exporter.export_audit.assert_awaited_once()


# ─── GlobalSearchService ───


class TestGlobalSearchService:
    @pytest.mark.asyncio
    async def test_search(self) -> None:
        reader = AsyncMock()
        expected = GlobalSearchResultDTO(
            nodes=(
                SearchResultItemDTO(id=uuid.uuid4(), name="web", entity_type="node"),
            ),
            commands=(),
            scripts=(),
            tags=("web",),
        )
        reader.search.return_value = expected
        svc = GlobalSearchService(reader=reader)

        result = await svc.search(q="web", limit=5)
        assert len(result.nodes) == 1
        assert len(result.tags) == 1


# ─── DashboardMetricsService ───


class TestDashboardMetricsService:
    @pytest.mark.asyncio
    async def test_get_metrics(self) -> None:
        from app.application.dto.dashboard_metrics import (
            DashboardMetricsDTO,
            MetricsBucketDTO,
        )

        reader = AsyncMock()
        expected = DashboardMetricsDTO(
            command_metrics=(
                MetricsBucketDTO(
                    period="2026-08-01",
                    total=10,
                    successful=8,
                    failed=2,
                    avg_duration_ms=100,
                ),
            ),
            script_metrics=(),
        )
        reader.get_metrics.return_value = expected
        svc = DashboardMetricsService(reader=reader)

        result = await svc.get_metrics(group_by="day")
        assert len(result.command_metrics) == 1


# ─── SseBroadcaster ───


class TestSseBroadcaster:
    def test_subscribe_and_publish(self) -> None:
        bc = SseBroadcaster()
        sub_id, queue = bc.subscribe()
        assert bc.active_subscribers == 1

        bc.publish("test.event", {"key": "value"})
        assert not queue.empty()

        event = queue.get_nowait()
        assert isinstance(event, SseEvent)
        assert event.event == "test.event"
        assert event.data == {"key": "value"}

    def test_unsubscribe(self) -> None:
        bc = SseBroadcaster()
        sub_id, _ = bc.subscribe()
        assert bc.active_subscribers == 1

        bc.unsubscribe(sub_id)
        assert bc.active_subscribers == 0

    def test_unsubscribe_nonexistent(self) -> None:
        bc = SseBroadcaster()
        bc.unsubscribe("nonexistent")  # should not raise

    def test_publish_to_dead_queue_removes_subscriber(self) -> None:
        bc = SseBroadcaster()
        sub_id, queue = bc.subscribe()

        # fill the queue to capacity
        for _ in range(256):
            queue.put_nowait(SseEvent(event="fill", data={}))

        # next publish should remove the dead subscriber
        bc.publish("test", {"k": "v"})
        assert bc.active_subscribers == 0

    def test_history_replay(self) -> None:
        bc = SseBroadcaster()
        bc.publish("past.event", {"n": 1})
        bc.publish("past.event", {"n": 2})

        sub_id, queue = bc.subscribe()
        assert queue.qsize() == 2

    def test_history_limit(self) -> None:
        bc = SseBroadcaster()
        bc._max_history = 5
        for i in range(10):
            bc.publish("event", {"i": i})
        assert len(bc._history) == 5

    def test_singleton(self) -> None:
        from app.application.services.sse_broadcaster import get_sse_broadcaster

        a = get_sse_broadcaster()
        b = get_sse_broadcaster()
        assert a is b
