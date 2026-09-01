"""Tests for configuration application service and transport schemas."""

from unittest.mock import AsyncMock

import pytest

from app.application.dto.config import (
    CONFIG_FORMAT_VERSION,
    ConfigImportResultDTO,
    ConfigTransferDTO,
    NodeConfigDTO,
)
from app.application.dto.value_objects import NodeEndpoint
from app.application.services.config_service import ConfigService
from app.core.exceptions import UnsupportedConfigFormatError
from app.schemas.config import ConfigExport, ImportResult, NodeExport


@pytest.mark.asyncio
async def test_export_enriches_adapter_snapshot_with_metadata() -> None:
    exporter = AsyncMock()
    importer = AsyncMock()
    snapshot = ConfigTransferDTO(
        nodes=(
            NodeConfigDTO(
                name="server-1",
                endpoint=NodeEndpoint(host="10.0.0.1", port=22, connection_type="ssh"),
            ),
        )
    )
    exporter.export_config.return_value = snapshot

    result = await ConfigService(exporter, importer).export_all()

    assert result.nodes == snapshot.nodes
    assert result.format_version == CONFIG_FORMAT_VERSION
    assert result.application_version
    assert result.exported_at is not None
    exporter.export_config.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_compatible_import_is_delegated() -> None:
    exporter = AsyncMock()
    importer = AsyncMock()
    data = ConfigTransferDTO(format_version="1.7")
    expected = ConfigImportResultDTO(nodes_created=2)
    importer.import_config.return_value = expected

    result = await ConfigService(exporter, importer).import_config(data)

    assert result is expected
    importer.import_config.assert_awaited_once_with(data)


@pytest.mark.asyncio
async def test_unknown_major_is_rejected_before_adapter_access() -> None:
    exporter = AsyncMock()
    importer = AsyncMock()

    with pytest.raises(UnsupportedConfigFormatError):
        await ConfigService(exporter, importer).import_config(
            ConfigTransferDTO(format_version="2.0")
        )

    importer.import_config.assert_not_awaited()


def test_config_export_schema_can_be_serialized() -> None:
    data = ConfigExport(
        exported_at="2026-01-01T00:00:00Z",
        nodes=[NodeExport(name="n", host="1.1.1.1", port=22, connection_type="ssh")],
    )

    dumped = data.model_dump()

    assert dumped["format_version"] == CONFIG_FORMAT_VERSION
    assert dumped["application_version"]
    assert len(dumped["nodes"]) == 1


def test_import_result_schema_has_correct_defaults() -> None:
    result = ImportResult()

    assert result.nodes_created == 0
    assert result.errors == []
