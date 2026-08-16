"""Dashboard overview application service."""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.application.dto.dashboard import DashboardDTO

if TYPE_CHECKING:
    from app.application.ports.dashboard import DashboardReader


class DashboardService:
    """Aggregate dashboard statistics through a single reader port."""

    def __init__(self, reader: DashboardReader) -> None:
        self._reader = reader

    async def get_dashboard(self) -> DashboardDTO:
        """Return aggregated dashboard statistics."""
        return await self._reader.get_dashboard()
