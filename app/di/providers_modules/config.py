# ruff: noqa: I001
"""DI providers for the application."""

from __future__ import annotations


from dishka import Provider, Scope, provide

from app.core.config import Settings, get_settings


class ConfigProvider(Provider):
    """Configuration provider."""

    @provide(scope=Scope.APP)
    def get_settings(self) -> Settings:
        """Get application settings."""
        return get_settings()
