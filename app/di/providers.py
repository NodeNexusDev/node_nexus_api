"""DI providers facade — delegates to split modules."""

from __future__ import annotations

from app.di.providers_modules.config import ConfigProvider
from app.di.providers_modules.connector import ConnectorProvider
from app.di.providers_modules.db import DbProvider
from app.di.providers_modules.repository import RepositoryProvider
from app.di.providers_modules.scheduler import SchedulerProvider
from app.di.providers_modules.service import ServiceProvider

__all__ = [
    "ConfigProvider",
    "ConnectorProvider",
    "DbProvider",
    "RepositoryProvider",
    "SchedulerProvider",
    "ServiceProvider",
    "AppProvider",
]


class AppProvider(
    ConfigProvider,
    DbProvider,
    RepositoryProvider,
    ConnectorProvider,
    SchedulerProvider,
    ServiceProvider,
):
    """Main application provider — composition of split providers."""

    pass
