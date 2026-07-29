"""Tests for DI provider wiring — resolves all services from container."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.di.providers import (
    ConfigProvider,
    ConnectorProvider,
    DbProvider,
    RepositoryProvider,
    SchedulerProvider,
    ServiceProvider,
)
from app.repositories.api_key_repo import APIKeyRepository
from app.repositories.audit_repo import AuditLogRepository
from app.repositories.command_repo import CommandRepository
from app.repositories.health_repo import HealthRepository
from app.repositories.node_repo import NodeRepository
from app.repositories.script_execution_repo import ScriptExecutionRepository
from app.repositories.script_repo import ScriptRepository
from app.services.api_key_service import APIKeyService
from app.services.audit_service import AuditService
from app.services.command_execution_service import CommandExecutionService
from app.services.command_management_service import CommandManagementService
from app.services.config_service import ConfigService
from app.services.health_service import HealthService
from app.services.node_management_service import NodeManagementService
from app.services.script_execution_service import ScriptExecutionService
from app.services.script_history_service import ScriptHistoryService
from app.services.script_management_service import ScriptManagementService


@pytest.mark.asyncio
async def test_db_provider_disposes_engine() -> None:
    settings = MagicMock()
    settings.DATABASE_URL = "sqlite+aiosqlite:///:memory:"
    engine = MagicMock()
    engine.dispose = AsyncMock()
    provider = DbProvider()

    with patch("app.di.providers.create_async_engine", return_value=engine):
        resource = provider.get_engine(settings)
        provided_engine = await anext(resource)
        assert provided_engine is engine
        await resource.aclose()

    engine.dispose.assert_awaited_once()


def test_db_provider_builds_sessionmaker_from_engine() -> None:
    provider = DbProvider()
    engine = MagicMock()

    sessionmaker = provider.get_sessionmaker(engine)

    assert sessionmaker.kw["expire_on_commit"] is False
    assert sessionmaker.kw["bind"] is engine


@pytest.mark.asyncio
async def test_scheduler_provider_manages_lifecycle() -> None:
    provider = SchedulerProvider()
    engine = MagicMock()
    engine.dialect.name = "sqlite"
    settings = MagicMock(SCHEDULER_ENABLED=True)
    resource = provider.get_script_scheduler(engine, settings)

    scheduler = await anext(resource)
    assert scheduler._scheduler.running is True

    await resource.aclose()
    assert scheduler._scheduler.running is False


def test_repository_provider_resolves() -> None:
    session = MagicMock()
    provider = RepositoryProvider()
    assert isinstance(provider.get_node_repository(session), NodeRepository)
    assert isinstance(provider.get_audit_repository(session), AuditLogRepository)
    assert isinstance(provider.get_command_repository(session), CommandRepository)
    assert isinstance(provider.get_script_repository(session), ScriptRepository)
    assert isinstance(
        provider.get_script_execution_repository(session), ScriptExecutionRepository
    )
    assert isinstance(provider.get_api_key_repository(session), APIKeyRepository)
    assert isinstance(provider.get_health_repository(session), HealthRepository)
    assert provider.get_scoped_script_reader(MagicMock()) is not None
    execution_writer = provider.get_scoped_execution_writer(MagicMock())
    assert execution_writer is not None
    assert provider.get_script_execution_writer(execution_writer) is execution_writer
    assert provider.get_scoped_command_reader(MagicMock()) is not None
    assert provider.get_scoped_node_reader(MagicMock()) is not None
    script_gateway = provider.get_script_gateway(MagicMock())
    assert provider.get_script_reader(script_gateway) is script_gateway
    assert provider.get_script_writer(script_gateway) is script_gateway
    assert provider.get_script_execution_reader(script_gateway) is script_gateway
    assert provider.get_script_definition_reader(script_gateway) is script_gateway
    gateway = provider.get_command_management_gateway(MagicMock())
    assert provider.get_command_management_reader(gateway) is gateway
    assert provider.get_command_management_writer(gateway) is gateway
    assert provider.get_command_template_reader(gateway) is gateway


def test_connector_provider_resolves() -> None:
    from app.core.connectors.ssh import SSHConnectorFactory

    provider = ConnectorProvider()
    settings = MagicMock()
    settings.SSH_KNOWN_HOSTS_PATH = "/tmp/known_hosts"
    settings.SSH_STRICT_HOST_KEY_CHECKING = True
    factory = provider.get_ssh_connector_factory(settings)
    assert isinstance(factory, SSHConnectorFactory)
    assert factory._known_hosts_path == "/tmp/known_hosts"
    runtime = provider.get_docker_runtime(
        factory,
        provider.get_credential_cipher(),
    )
    assert runtime is not None


def test_service_provider_resolves() -> None:
    from app.adapters.persistence.command_reader import ScopedCommandTemplateReader
    from app.adapters.persistence.node_reader import ScopedNodeConnectionReader
    from app.adapters.persistence.script_gateway import (
        ScopedScriptExecutionWriter,
    )

    session = MagicMock()
    repo_provider = RepositoryProvider()
    conn_provider = ConnectorProvider()
    svc_provider = ServiceProvider()

    node_repo = repo_provider.get_node_repository(session)
    audit_repo = repo_provider.get_audit_repository(session)
    cmd_repo = repo_provider.get_command_repository(session)
    script_repo = repo_provider.get_script_repository(session)
    api_key_repo = repo_provider.get_api_key_repository(session)
    settings = MagicMock()
    settings.SSH_KNOWN_HOSTS_PATH = "/tmp/known_hosts"
    settings.SSH_STRICT_HOST_KEY_CHECKING = False
    factory = conn_provider.get_ssh_connector_factory(settings)
    credential_cipher = conn_provider.get_credential_cipher()
    node_reader = ScopedNodeConnectionReader(MagicMock())
    command_reader = ScopedCommandTemplateReader(MagicMock())
    execution_writer = ScopedScriptExecutionWriter(MagicMock())

    required_writer = svc_provider.get_required_audit_writer(MagicMock())
    audit_svc = svc_provider.get_audit_service(audit_repo, required_writer)
    assert isinstance(audit_svc, AuditService)

    node_command_svc = svc_provider.get_node_command_service(
        audit_svc,
        factory,
        node_reader,
        MagicMock(),
        credential_cipher,
    )
    node_bulk_command_svc = svc_provider.get_node_bulk_command_service(
        audit_svc,
        factory,
        node_reader,
        credential_cipher,
    )
    node_metrics_svc = svc_provider.get_node_metrics_service(
        factory,
        node_reader,
        credential_cipher,
    )
    assert node_command_svc is not None
    assert node_bulk_command_svc is not None
    assert node_metrics_svc is not None
    node_svc = svc_provider.get_node_management_service(
        MagicMock(),
        MagicMock(),
        credential_cipher,
        audit_svc,
    )
    assert isinstance(node_svc, NodeManagementService)

    command_management_svc = svc_provider.get_command_management_service(
        MagicMock(),
        MagicMock(),
        audit_svc,
    )
    command_execution_svc = svc_provider.get_command_execution_service(
        audit_svc,
        factory,
        command_reader,
        node_reader,
        credential_cipher,
    )
    assert isinstance(command_management_svc, CommandManagementService)
    assert isinstance(command_execution_svc, CommandExecutionService)

    script_management_svc = svc_provider.get_script_management_service(
        MagicMock(),
        MagicMock(),
        audit_svc,
    )
    script_history_svc = svc_provider.get_script_history_service(
        MagicMock(),
        MagicMock(),
    )
    assert isinstance(script_management_svc, ScriptManagementService)
    assert isinstance(script_history_svc, ScriptHistoryService)
    script_execution_svc = svc_provider.get_script_execution_service(
        MagicMock(),
        command_reader,
        node_reader,
        execution_writer,
        credential_cipher,
        factory,
        audit_svc,
    )
    assert isinstance(script_execution_svc, ScriptExecutionService)

    api_key_svc = svc_provider.get_api_key_service(api_key_repo)
    assert isinstance(api_key_svc, APIKeyService)

    config_svc = svc_provider.get_config_service(node_repo, cmd_repo, script_repo)
    assert isinstance(config_svc, ConfigService)

    scheduler = MagicMock()
    health = svc_provider.get_health_service(
        repo_provider.get_health_repository(session),
        scheduler,
        MagicMock(SCHEDULER_ENABLED=True),
    )
    assert isinstance(health, HealthService)
    assert svc_provider.get_streaming_command_service(node_reader, factory) is not None


async def test_db_session_provider_manages_transaction() -> None:
    provider = DbProvider()
    session = MagicMock()
    session_context = AsyncMock()
    session_context.__aenter__.return_value = session
    transaction = AsyncMock()
    session.begin.return_value = transaction
    factory = MagicMock(return_value=session_context)

    resource = provider.get_session(factory)
    assert await anext(resource) is session
    await resource.aclose()
    transaction.__aexit__.assert_awaited_once()


async def test_disabled_scheduler_provider_does_not_start() -> None:
    provider = SchedulerProvider()
    resource = provider.get_script_scheduler(
        MagicMock(), MagicMock(SCHEDULER_ENABLED=False)
    )
    scheduler = await anext(resource)
    assert scheduler._scheduler.running is False
    await resource.aclose()


async def test_audit_worker_provider_lifecycle() -> None:
    provider = SchedulerProvider()
    worker = MagicMock()
    worker.stop = AsyncMock()
    with patch("app.di.providers.AuditOutboxWorker", return_value=worker):
        resource = provider.get_audit_outbox_worker(MagicMock())
        assert await anext(resource) is worker
        await resource.aclose()
    worker.start.assert_called_once()
    worker.stop.assert_awaited_once()


def test_config_provider_returns_cached_settings() -> None:
    expected = MagicMock()
    with patch("app.di.providers.get_settings", return_value=expected):
        assert ConfigProvider().get_settings() is expected
