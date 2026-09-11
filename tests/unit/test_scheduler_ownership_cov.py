"""Coverage tests for SQLAlchemy scheduler ownership adapter."""

from unittest.mock import AsyncMock, MagicMock, patch

from app.adapters.persistence import scheduler_ownership
from app.adapters.persistence.scheduler_ownership import SqlAlchemySchedulerOwnership


def _pg_engine() -> MagicMock:
    engine = MagicMock()
    engine.dialect.name = "postgresql"
    engine.connect = AsyncMock()
    return engine


def _non_pg_engine() -> MagicMock:
    engine = MagicMock()
    engine.dialect.name = "sqlite"
    engine.connect = AsyncMock()
    return engine


def _pg_conn(**overrides: object) -> AsyncMock:
    conn = AsyncMock()
    for key, value in overrides.items():
        setattr(conn, key, value)
    return conn


async def test_non_postgres_acquire_probe_release() -> None:
    owner = SqlAlchemySchedulerOwnership(_non_pg_engine())
    assert owner.is_postgres is False
    assert owner.is_acquired is False
    assert await owner.try_acquire() is True
    assert owner.is_acquired is True
    assert await owner.probe() is True
    await owner.release()
    assert owner.is_acquired is False


async def test_acquire_success_postgres() -> None:
    engine = _pg_engine()
    conn = _pg_conn()
    conn.scalar.return_value = True
    engine.connect.return_value = conn
    owner = SqlAlchemySchedulerOwnership(engine)
    assert await owner.try_acquire() is True
    assert owner.is_acquired is True
    assert await owner.try_acquire() is True  # fast path: already acquired
    engine.connect.assert_awaited_once()
    conn.scalar.assert_awaited_once()
    conn.close.assert_not_called()


async def test_acquire_returns_truthy_int() -> None:
    engine = _pg_engine()
    conn = _pg_conn()
    conn.scalar.return_value = 1
    engine.connect.return_value = conn
    owner = SqlAlchemySchedulerOwnership(engine)
    assert await owner.try_acquire() is True
    assert owner.is_acquired is True


async def test_acquire_rejected_closes_connection() -> None:
    engine = _pg_engine()
    conn = _pg_conn()
    conn.scalar.return_value = False
    engine.connect.return_value = conn
    owner = SqlAlchemySchedulerOwnership(engine)
    with patch.object(scheduler_ownership.logger, "info") as info:
        assert await owner.try_acquire() is False
    assert owner.is_acquired is False
    conn.close.assert_awaited_once()
    info.assert_called_once_with("scheduler.owner.rejected")


async def test_acquire_scalar_raises_closes_and_reraises() -> None:
    engine = _pg_engine()
    conn = _pg_conn()
    conn.scalar.side_effect = RuntimeError("db down")
    engine.connect.return_value = conn
    owner = SqlAlchemySchedulerOwnership(engine)
    try:
        await owner.try_acquire()
    except RuntimeError:
        pass
    else:  # pragma: no cover
        raise AssertionError("expected RuntimeError")
    conn.close.assert_awaited_once()
    assert owner.is_acquired is False


async def test_acquire_when_flag_set_but_no_connection_reconnects() -> None:
    engine = _non_pg_engine()
    owner = SqlAlchemySchedulerOwnership(engine)
    await owner.try_acquire()
    assert owner.is_acquired is True
    # Simulate non-pg flag set path is covered; now pg path with stale flag.
    pg_engine = _pg_engine()
    conn = _pg_conn()
    conn.scalar.return_value = True
    pg_engine.connect.return_value = conn
    owner2 = SqlAlchemySchedulerOwnership(pg_engine)
    owner2._acquired = True  # stale flag without connection
    assert await owner2.try_acquire() is True
    assert owner2.is_acquired is True


async def test_probe_no_connection_returns_false() -> None:
    owner = SqlAlchemySchedulerOwnership(_pg_engine())
    assert await owner.probe() is False


async def test_probe_alive_and_dead() -> None:
    engine = _pg_engine()
    owner = SqlAlchemySchedulerOwnership(engine)
    conn = _pg_conn()
    owner._connection = conn  # type: ignore[attr-defined]
    assert await owner.probe() is True
    conn.execute.assert_awaited_once()

    bad = _pg_conn()
    bad.execute.side_effect = RuntimeError("lost")
    owner._connection = bad  # type: ignore[attr-defined]
    assert await owner.probe() is False


async def test_release_with_held_lock() -> None:
    engine = _pg_engine()
    conn = _pg_conn()
    conn.scalar.return_value = True
    engine.connect.return_value = conn
    owner = SqlAlchemySchedulerOwnership(engine)
    assert await owner.try_acquire() is True
    await owner.release()
    assert owner.is_acquired is False
    conn.execute.assert_awaited_once()
    conn.close.assert_awaited_once()


async def test_release_without_connection_only_clears_flag() -> None:
    owner = SqlAlchemySchedulerOwnership(_pg_engine())
    owner._acquired = True  # type: ignore[attr-defined]
    await owner.release()
    assert owner.is_acquired is False


async def test_release_unlock_failure_still_closes() -> None:
    engine = _pg_engine()
    conn = _pg_conn()
    conn.execute.side_effect = RuntimeError("unlock boom")
    owner = SqlAlchemySchedulerOwnership(engine)
    owner._connection = conn  # type: ignore[attr-defined]
    owner._acquired = True  # type: ignore[attr-defined]
    with patch.object(scheduler_ownership.logger, "warning") as warn:
        await owner.release()
    assert owner.is_acquired is False
    conn.close.assert_awaited_once()
    assert warn.call_count == 1
    assert warn.call_args[0][0] == "scheduler.owner.unlock_failed"


async def test_release_close_failure_warns() -> None:
    engine = _pg_engine()
    conn = _pg_conn()
    conn.close.side_effect = RuntimeError("close boom")
    owner = SqlAlchemySchedulerOwnership(engine)
    owner._connection = conn  # type: ignore[attr-defined]
    owner._acquired = True  # type: ignore[attr-defined]
    with patch.object(scheduler_ownership.logger, "warning") as warn:
        await owner.release()
    assert owner.is_acquired is False
    assert warn.call_count == 1
    assert warn.call_args[0][0] == "scheduler.owner.close_failed"


async def test_release_both_fail_warns_twice() -> None:
    engine = _pg_engine()
    conn = _pg_conn()
    conn.execute.side_effect = RuntimeError("unlock boom")
    conn.close.side_effect = RuntimeError("close boom")
    owner = SqlAlchemySchedulerOwnership(engine)
    owner._connection = conn  # type: ignore[attr-defined]
    owner._acquired = True  # type: ignore[attr-defined]
    with patch.object(scheduler_ownership.logger, "warning") as warn:
        await owner.release()
    assert owner.is_acquired is False
    assert warn.call_count == 2


async def test_acquire_logs_acquired() -> None:
    engine = _pg_engine()
    conn = _pg_conn()
    conn.scalar.return_value = True
    engine.connect.return_value = conn
    owner = SqlAlchemySchedulerOwnership(engine)
    with patch.object(scheduler_ownership.logger, "info") as info:
        assert await owner.try_acquire() is True
    info.assert_called_once_with("scheduler.owner.acquired")


async def test_non_postgres_release_when_not_acquired() -> None:
    owner = SqlAlchemySchedulerOwnership(_non_pg_engine())
    await owner.release()
    assert owner.is_acquired is False
