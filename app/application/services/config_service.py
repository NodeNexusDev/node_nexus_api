"""Configuration export and import application use cases."""

from dataclasses import replace
from datetime import UTC, datetime
from importlib.metadata import PackageNotFoundError, version

from app.application.dto.config import (
    CONFIG_FORMAT_VERSION,
    LEGACY_CONFIG_VERSION,
    ConfigImportResultDTO,
    ConfigTransferDTO,
)
from app.application.ports.config_persistence import (
    ConfigurationExporter,
    ConfigurationImporter,
)
from app.core.exceptions import UnsupportedConfigFormatError


class ConfigService:
    """Coordinate configuration transfer through focused outbound ports."""

    def __init__(
        self,
        exporter: ConfigurationExporter,
        importer: ConfigurationImporter,
    ) -> None:
        self._exporter = exporter
        self._importer = importer

    async def export_all(self) -> ConfigTransferDTO:
        """Export all configuration and add application-owned metadata."""
        snapshot = await self._exporter.export_config()
        return replace(
            snapshot,
            format_version=CONFIG_FORMAT_VERSION,
            application_version=_application_version(),
            legacy_version=LEGACY_CONFIG_VERSION,
            exported_at=datetime.now(UTC),
        )

    async def import_config(self, data: ConfigTransferDTO) -> ConfigImportResultDTO:
        """Validate the transfer format and delegate the coordinated import."""
        if data.format_version is not None:
            received_major = data.format_version.split(".", maxsplit=1)[0]
            supported_major = CONFIG_FORMAT_VERSION.split(".", maxsplit=1)[0]
            if received_major != supported_major:
                raise UnsupportedConfigFormatError(
                    "Unsupported configuration format "
                    f"{data.format_version}; supported major is {supported_major}"
                )
        return await self._importer.import_config(data)


def _application_version() -> str:
    try:
        return version("node-nexus-api")
    except PackageNotFoundError:
        return "unknown"
