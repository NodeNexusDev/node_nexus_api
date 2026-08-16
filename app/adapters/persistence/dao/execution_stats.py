from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import case, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.command_execution import CommandExecutionModel
from app.models.script_execution import ScriptExecutionModel

_DUR = (
    func.extract(
        text("epoch"),
        CommandExecutionModel.finished_at - CommandExecutionModel.started_at,
    )
    * 1000
)


class ExecutionStatsRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def command_stats(
        self,
        command_id: uuid.UUID | None = None,
        node_id: uuid.UUID | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
    ) -> dict:
        cmd = CommandExecutionModel
        dur = (
            func.extract(
                text("epoch"),
                cmd.finished_at - cmd.started_at,
            )
            * 1000
        )
        ok = case((cmd.exit_code == 0, 1), else_=0)
        fail = case((cmd.exit_code != 0, 1), else_=0)
        stmt = select(
            func.count().label("total"),
            func.sum(ok).label("successful"),
            func.sum(fail).label("failed"),
            func.avg(dur).label("avg_duration_ms"),
            func.min(dur).label("min_duration_ms"),
            func.max(dur).label("max_duration_ms"),
            func.max(cmd.finished_at).label("last_executed_at"),
        )
        if command_id is not None:
            stmt = stmt.where(cmd.command_id == command_id)
        if node_id is not None:
            stmt = stmt.where(cmd.node_id == node_id)
        if date_from is not None:
            stmt = stmt.where(cmd.started_at >= date_from)
        if date_to is not None:
            stmt = stmt.where(cmd.started_at <= date_to)

        row = (await self._session.execute(stmt)).one()
        return dict(row._mapping)

    async def script_stats(
        self,
        script_id: uuid.UUID | None = None,
        node_id: uuid.UUID | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
    ) -> dict:
        scr = ScriptExecutionModel
        dur = (
            func.extract(
                text("epoch"),
                scr.finished_at - scr.started_at,
            )
            * 1000
        )
        ok = case((scr.status == "completed", 1), else_=0)
        fail = case((scr.status != "completed", 1), else_=0)
        stmt = select(
            func.count().label("total"),
            func.sum(ok).label("successful"),
            func.sum(fail).label("failed"),
            func.avg(dur).label("avg_duration_ms"),
            func.min(dur).label("min_duration_ms"),
            func.max(dur).label("max_duration_ms"),
            func.max(scr.finished_at).label("last_executed_at"),
        )
        if script_id is not None:
            stmt = stmt.where(scr.script_id == script_id)
        if node_id is not None:
            stmt = stmt.where(scr.node_id == node_id)
        if date_from is not None:
            stmt = stmt.where(scr.started_at >= date_from)
        if date_to is not None:
            stmt = stmt.where(scr.started_at <= date_to)

        row = (await self._session.execute(stmt)).one()
        return dict(row._mapping)
