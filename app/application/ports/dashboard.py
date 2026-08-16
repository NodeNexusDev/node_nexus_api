"""Dashboard reader port."""

from typing import Protocol

from app.application.dto.dashboard import DashboardDTO


class DashboardReader(Protocol):
    """Read aggregated dashboard statistics."""

    async def get_dashboard(self) -> DashboardDTO: ...
