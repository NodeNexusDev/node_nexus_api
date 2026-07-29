"""Focused outbound ports for configuration transfer."""

from typing import Protocol

from app.application.dto.config import ConfigImportResultDTO, ConfigTransferDTO


class ConfigurationExporter(Protocol):
    """Export the complete application configuration."""

    async def export_config(self) -> ConfigTransferDTO: ...


class ConfigurationImporter(Protocol):
    """Import one configuration payload as a coordinated operation."""

    async def import_config(self, data: ConfigTransferDTO) -> ConfigImportResultDTO: ...
