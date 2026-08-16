"""Node status history ports."""

from __future__ import annotations

from typing import Protocol

from app.application.dto.node_status_history import (
    NodeStatusChangeDTO,
    NodeStatusHistoryPageDTO,
    NodeStatusHistoryQueryDTO,
)


class NodeStatusHistoryWriter(Protocol):
    async def save(self, data: NodeStatusChangeDTO) -> None: ...


class NodeStatusHistoryReader(Protocol):
    async def list_by_node(
        self, query: NodeStatusHistoryQueryDTO
    ) -> NodeStatusHistoryPageDTO: ...
