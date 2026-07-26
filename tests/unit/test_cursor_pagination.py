"""Tests for cursor-based pagination."""

import base64
import json
from datetime import UTC, datetime
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.models.base import Base
from app.models.node import NodeModel
from app.repositories.node_repo import NodeRepository
from app.schemas.common import CursorPage, decode_cursor, encode_cursor


@pytest_asyncio.fixture
async def engine():
    eng = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def session(engine):
    sm = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with sm() as s:
        async with s.begin():
            yield s


class TestCursorEncoding:
    """Tests for cursor encode/decode."""

    def test_encode_decode_roundtrip(self):
        """Encoded cursor can be decoded back."""
        ts = datetime(2026, 1, 15, 10, 30, 0, tzinfo=UTC)
        node_id = uuid4()
        encoded = encode_cursor(ts, node_id)
        decoded_ts, decoded_id = decode_cursor(encoded)
        assert decoded_id == node_id
        assert decoded_ts.replace(tzinfo=None) == ts.replace(tzinfo=None)

    def test_encode_returns_base64(self):
        """Encoded cursor is valid base64."""
        ts = datetime(2026, 6, 15, tzinfo=UTC)
        node_id = uuid4()
        encoded = encode_cursor(ts, node_id)
        raw = base64.urlsafe_b64decode(encoded)
        data = json.loads(raw)
        assert "ts" in data
        assert "id" in data

    def test_decode_invalid_base64(self):
        """Invalid base64 raises ValueError."""
        with pytest.raises(ValueError, match="Invalid cursor"):
            decode_cursor("not-valid-base64!!!")

    def test_decode_valid_base64_invalid_json(self):
        """Valid base64 but invalid JSON raises ValueError."""
        encoded = base64.urlsafe_b64encode(b"not json").decode()
        with pytest.raises(ValueError, match="Invalid cursor"):
            decode_cursor(encoded)

    def test_decode_missing_fields(self):
        """JSON missing required fields raises ValueError."""
        encoded = base64.urlsafe_b64encode(json.dumps({"ts": "bad"}).encode()).decode()
        with pytest.raises(ValueError, match="Invalid cursor"):
            decode_cursor(encoded)


class TestCursorPageSchema:
    """Tests for CursorPage response schema."""

    def test_cursor_page_creation(self):
        """CursorPage can be created with required fields."""
        page = CursorPage(items=[], has_more=False, limit=20)
        assert page.items == []
        assert page.next_cursor is None
        assert page.has_more is False
        assert page.limit == 20

    def test_cursor_page_with_next(self):
        """CursorPage with next_cursor."""
        page = CursorPage(
            items=["a", "b"],
            next_cursor="abc123",
            has_more=True,
            limit=2,
        )
        assert len(page.items) == 2
        assert page.next_cursor == "abc123"
        assert page.has_more is True


class TestNodeRepoCursor:
    """Tests for NodeRepository.get_list_cursor with in-memory SQLite."""

    async def test_cursor_first_page(self, session):
        """First page without cursor returns most recent nodes."""
        for i in range(5):
            node = NodeModel(
                id=uuid4(),
                name=f"server-{i}",
                host=f"10.0.0.{i}",
                port=22,
                connection_type="ssh",
                status="active",
            )
            session.add(node)
        await session.flush()

        repo = NodeRepository(session)
        nodes = await repo.get_list_cursor(cursor=None, limit=3)

        assert len(nodes) == 4  # 5 nodes exist, limit=3 → fetches limit+1=4
        assert all(isinstance(n.name, str) for n in nodes)

    async def test_cursor_pagination(self, session):
        """Second page via cursor returns next batch without duplicates."""
        for i in range(5):
            node = NodeModel(
                id=uuid4(),
                name=f"server-{i}",
                host=f"10.0.0.{i}",
                port=22,
                connection_type="ssh",
                status="active",
                created_at=datetime(2026, 1, i + 1, tzinfo=UTC),
            )
            session.add(node)
        await session.flush()

        repo = NodeRepository(session)

        # First page (limit=2, but 5 exist → fetches 3)
        page1 = await repo.get_list_cursor(cursor=None, limit=2)
        assert len(page1) >= 2

        # Create cursor from last item of page1
        last = page1[-1]
        cursor_tuple = (last.created_at, last.id)

        # Second page
        page2 = await repo.get_list_cursor(cursor=cursor_tuple, limit=2)
        page1_ids = {n.id for n in page1}
        page2_ids = {n.id for n in page2}
        assert not page1_ids & page2_ids, "No duplicates between pages"

    async def test_cursor_has_more_detection(self, session):
        """has_more is True when there are more items than limit."""
        for i in range(3):
            node = NodeModel(
                id=uuid4(),
                name=f"server-{i}",
                host=f"10.0.0.{i}",
                port=22,
                connection_type="ssh",
                status="active",
                created_at=datetime(2026, 1, i + 1, tzinfo=UTC),
            )
            session.add(node)
        await session.flush()

        repo = NodeRepository(session)
        nodes = await repo.get_list_cursor(cursor=None, limit=2)
        assert len(nodes) == 3  # fetched limit+1

    async def test_cursor_empty_result(self, session):
        """Empty result when no nodes exist."""
        repo = NodeRepository(session)
        nodes = await repo.get_list_cursor(cursor=None, limit=10)
        assert nodes == []
