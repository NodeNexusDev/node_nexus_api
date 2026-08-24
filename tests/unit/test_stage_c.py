"""Tests for Stage C: dry-run import and credential validation."""

from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    create_async_engine,
)

from app.adapters.persistence.config import SqlAlchemyConfigGateway
from app.application.dto.config import (
    CommandConfigDTO,
    ConfigTransferDTO,
    DryRunPreviewDTO,
    NodeConfigDTO,
    ScriptConfigDTO,
)
from app.application.dto.node_validation import (
    NodeValidationRequestDTO,
    NodeValidationResultDTO,
)
from app.application.services.config_service import ConfigService
from app.application.services.node_validation_service import NodeValidationService
from app.core.exceptions import ConnectionFailedError, UnsupportedConfigFormatError
from app.models.base import Base


@pytest_asyncio.fixture
async def engine() -> AsyncGenerator[AsyncEngine]:
    database = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with database.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    yield database
    await database.dispose()


# --- C.1 Dry-run import tests ---


@pytest.mark.asyncio
async def test_preview_import_does_not_write() -> None:
    """preview_import should return a DryRunPreviewDTO without writing."""
    sessionmaker_mock = MagicMock()
    session = AsyncMock()
    context = AsyncMock()
    context.__aenter__.return_value = session
    sessionmaker_mock.return_value = context

    node_repository = AsyncMock()
    node_repository.get_all.return_value = []
    command_repository = AsyncMock()
    command_repository.get_all.return_value = []
    script_repository = AsyncMock()
    script_repository.get_all.return_value = []

    data = ConfigTransferDTO(
        nodes=(NodeConfigDTO("new-node", "10.0.0.1", 22, "ssh"),),
        commands=(CommandConfigDTO("uptime", "uptime"),),
        scripts=(ScriptConfigDTO("deploy", steps=({"cmd": "echo"},)),),
    )

    with (
        patch(
            "app.adapters.persistence.config.NodeRepository",
            return_value=node_repository,
        ),
        patch(
            "app.adapters.persistence.config.CommandRepository",
            return_value=command_repository,
        ),
        patch(
            "app.adapters.persistence.config.ScriptRepository",
            return_value=script_repository,
        ),
    ):
        result = await SqlAlchemyConfigGateway(sessionmaker_mock).preview_import(data)

    assert isinstance(result, DryRunPreviewDTO)
    assert len(result.would_create_nodes) == 1
    assert result.would_create_nodes[0].name == "new-node"
    assert len(result.would_create_commands) == 1
    assert len(result.would_create_scripts) == 1
    assert result.duplicates == ()
    assert result.errors == ()
    node_repository.create.assert_not_awaited()
    command_repository.create.assert_not_awaited()
    script_repository.create.assert_not_awaited()


@pytest.mark.asyncio
async def test_preview_import_reports_duplicates() -> None:
    """preview_import should report existing items as duplicates."""
    sessionmaker_mock = MagicMock()
    session = AsyncMock()
    context = AsyncMock()
    context.__aenter__.return_value = session
    sessionmaker_mock.return_value = context

    existing_node = MagicMock()
    existing_node.name = "existing-node"
    node_repository = AsyncMock()
    node_repository.get_all.return_value = [existing_node]
    command_repository = AsyncMock()
    command_repository.get_all.return_value = []
    script_repository = AsyncMock()
    script_repository.get_all.return_value = []

    data = ConfigTransferDTO(
        nodes=(
            NodeConfigDTO("existing-node", "10.0.0.1", 22, "ssh"),
            NodeConfigDTO("new-node", "10.0.0.2", 22, "ssh"),
        ),
    )

    with (
        patch(
            "app.adapters.persistence.config.NodeRepository",
            return_value=node_repository,
        ),
        patch(
            "app.adapters.persistence.config.CommandRepository",
            return_value=command_repository,
        ),
        patch(
            "app.adapters.persistence.config.ScriptRepository",
            return_value=script_repository,
        ),
    ):
        result = await SqlAlchemyConfigGateway(sessionmaker_mock).preview_import(data)

    assert len(result.would_create_nodes) == 1
    assert result.would_create_nodes[0].name == "new-node"
    assert len(result.duplicates) == 1
    assert "already exists" in result.duplicates[0]


@pytest.mark.asyncio
async def test_service_dry_run_delegates_to_preview() -> None:
    """ConfigService.import_config with dry_run=True should call preview_import."""
    importer = AsyncMock()
    exporter = AsyncMock()
    expected = DryRunPreviewDTO(
        would_create_nodes=(NodeConfigDTO("n", "10.0.0.1", 22, "ssh"),),
    )
    importer.preview_import.return_value = expected

    service = ConfigService(exporter=exporter, importer=importer)
    data = ConfigTransferDTO(nodes=(NodeConfigDTO("n", "10.0.0.1", 22, "ssh"),))

    result = await service.import_config(data, dry_run=True)

    assert result is expected
    importer.preview_import.assert_awaited_once_with(data)
    importer.import_config.assert_not_awaited()


@pytest.mark.asyncio
async def test_service_import_without_dry_run_calls_importer() -> None:
    """ConfigService.import_config without dry_run should call import_config."""
    importer = AsyncMock()
    exporter = AsyncMock()
    from app.application.dto.config import ConfigImportResultDTO

    expected = ConfigImportResultDTO(nodes_created=1)
    importer.import_config.return_value = expected

    service = ConfigService(exporter=exporter, importer=importer)
    data = ConfigTransferDTO(nodes=(NodeConfigDTO("n", "10.0.0.1", 22, "ssh"),))

    result = await service.import_config(data, dry_run=False)

    assert result is expected
    importer.import_config.assert_awaited_once_with(data)
    importer.preview_import.assert_not_awaited()


@pytest.mark.asyncio
async def test_service_rejects_unsupported_version_on_dry_run() -> None:
    """dry_run should still reject unsupported format versions."""
    importer = AsyncMock()
    exporter = AsyncMock()
    service = ConfigService(exporter=exporter, importer=importer)
    data = ConfigTransferDTO(
        nodes=(NodeConfigDTO("n", "10.0.0.1", 22, "ssh"),),
        format_version="99.0",
    )

    with pytest.raises(UnsupportedConfigFormatError):
        await service.import_config(data, dry_run=True)

    importer.preview_import.assert_not_awaited()


# --- C.2 Credential validation tests ---


@pytest.mark.asyncio
async def test_node_validation_service_success() -> None:
    """NodeValidationService should delegate to the validator port."""
    validator = AsyncMock()
    expected = NodeValidationResultDTO(
        status="active", message="SSH connection successful"
    )
    validator.validate.return_value = expected

    service = NodeValidationService(validator=validator)
    request = NodeValidationRequestDTO(
        host="10.0.0.1", port=22, username="root", password="secret"
    )

    result = await service.validate_credentials(request)

    assert result is expected
    validator.validate.assert_awaited_once_with(request)


@pytest.mark.asyncio
async def test_node_validation_service_failure() -> None:
    """NodeValidationService should handle connection failures."""
    validator = AsyncMock()
    expected = NodeValidationResultDTO(
        status="unreachable", message="Connection refused"
    )
    validator.validate.return_value = expected

    service = NodeValidationService(validator=validator)
    request = NodeValidationRequestDTO(host="10.0.0.1", port=22)

    result = await service.validate_credentials(request)

    assert result.status == "unreachable"


@pytest.mark.asyncio
async def test_ssh_credential_validator_success() -> None:
    """SshCredentialValidator should return active on successful connection."""
    from app.adapters.runtime.node_validation import SshCredentialValidator

    connector = AsyncMock()
    connector.execute_command.return_value = ("ok", "", 0)
    connector.__aenter__ = AsyncMock(return_value=connector)
    connector.__aexit__ = AsyncMock(return_value=False)

    factory = MagicMock()
    factory.create_ssh.return_value = connector

    validator = SshCredentialValidator(factory)
    request = NodeValidationRequestDTO(
        host="10.0.0.1", port=22, username="root", password="secret"
    )

    result = await validator.validate(request)

    assert result.status == "active"
    assert "successful" in result.message
    factory.create_ssh.assert_called_once_with(
        host="10.0.0.1",
        port=22,
        username="root",
        password="secret",
        ssh_key=None,
        passphrase=None,
    )


@pytest.mark.asyncio
async def test_ssh_credential_validator_connection_failed() -> None:
    """SshCredentialValidator should return unreachable on ConnectionFailedError."""
    from app.adapters.runtime.node_validation import SshCredentialValidator

    connector = AsyncMock()
    connector.__aenter__ = AsyncMock(
        side_effect=ConnectionFailedError("Connection refused")
    )
    connector.__aexit__ = AsyncMock(return_value=False)

    factory = MagicMock()
    factory.create_ssh.return_value = connector

    validator = SshCredentialValidator(factory)
    request = NodeValidationRequestDTO(host="10.0.0.1", port=22)

    result = await validator.validate(request)

    assert result.status == "unreachable"
    assert "Connection refused" in result.message


@pytest.mark.asyncio
async def test_ssh_credential_validator_unexpected_error() -> None:
    """SshCredentialValidator should handle unexpected errors gracefully."""
    from app.adapters.runtime.node_validation import SshCredentialValidator

    connector = AsyncMock()
    connector.__aenter__ = AsyncMock(side_effect=RuntimeError("unexpected"))
    connector.__aexit__ = AsyncMock(return_value=False)

    factory = MagicMock()
    factory.create_ssh.return_value = connector

    validator = SshCredentialValidator(factory)
    request = NodeValidationRequestDTO(host="10.0.0.1", port=22)

    result = await validator.validate(request)

    assert result.status == "unreachable"
    assert "Connection failed" in result.message


# --- C.1 API schema tests ---


def test_config_import_schema_accepts_dry_run() -> None:
    """ConfigImport schema should accept dry_run field."""
    from app.schemas.config import ConfigImport

    data = ConfigImport(
        dry_run=True,
        nodes=[{"name": "n", "host": "10.0.0.1", "port": 22, "connection_type": "ssh"}],
    )
    assert data.dry_run is True


def test_config_import_schema_defaults_dry_run_false() -> None:
    """ConfigImport schema should default dry_run to False."""
    from app.schemas.config import ConfigImport

    data = ConfigImport()
    assert data.dry_run is False


def test_dry_run_import_result_schema() -> None:
    """DryRunImportResult should serialize correctly."""
    from app.schemas.config import (
        DryRunCommandPreview,
        DryRunImportResult,
        DryRunNodePreview,
        DryRunScriptPreview,
        DryRunWouldCreate,
    )

    result = DryRunImportResult(
        dry_run=True,
        would_create=DryRunWouldCreate(
            nodes=[
                DryRunNodePreview(
                    name="n", host="10.0.0.1", port=22, connection_type="ssh"
                )
            ],
            commands=[DryRunCommandPreview(name="c", command="uptime")],
            scripts=[DryRunScriptPreview(name="s")],
        ),
        duplicates=["Node 'old' already exists"],
        errors=[],
    )
    data = result.model_dump()
    assert data["dry_run"] is True
    assert len(data["would_create"]["nodes"]) == 1
    assert len(data["would_create"]["commands"]) == 1
    assert len(data["would_create"]["scripts"]) == 1
    assert len(data["duplicates"]) == 1


# --- C.2 API schema tests ---


def test_node_validate_request_schema() -> None:
    """NodeValidateRequest should validate correctly."""
    from app.schemas.node import NodeValidateRequest

    req = NodeValidateRequest(
        host="10.0.0.1", port=22, username="root", password="secret"
    )
    assert req.host == "10.0.0.1"
    assert req.port == 22
    assert req.connection_type == "ssh"


def test_node_validate_response_schema() -> None:
    """NodeValidateResponse should serialize correctly."""
    from app.schemas.node import NodeValidateResponse

    resp = NodeValidateResponse(status="active", message="OK")
    assert resp.status == "active"
    assert resp.message == "OK"
