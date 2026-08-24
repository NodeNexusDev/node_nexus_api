"""Tests for DI provider wiring — resolves all services from container."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.adapters.persistence.dao.command import CommandRepository
from app.adapters.persistence.dao.health import HealthRepository
from app.adapters.persistence.dao.node import NodeRepository
from app.adapters.persistence.dao.script import ScriptRepository
from app.adapters.persistence.dao.script_execution import ScriptExecutionRepository
from app.application.services.api_key_authentication import (
    APIKeyAuthenticationService,
)
from app.application.services.api_key_management import APIKeyManagementService
from app.application.services.audit_event_service import AuditEventService
from app.application.services.audit_log_service import AuditLogService
from app.application.services.command_execution_service import CommandExecutionService
from app.application.services.command_management_service import CommandManagementService
from app.application.services.config_service import ConfigService
from app.application.services.health_service import HealthService
from app.application.services.node_management_service import NodeManagementService
from app.application.services.script_execution_service import ScriptExecutionService
from app.application.services.script_history_service import ScriptHistoryService
from app.application.services.script_management_service import ScriptManagementService
from app.di.providers import (
    ConfigProvider,
    ConnectorProvider,
    DbProvider,
    RepositoryProvider,
    SchedulerProvider,
    ServiceProvider,
)


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


def test_db_provider_builds_migration_runner() -> None:
    settings = MagicMock(DATABASE_URL="postgresql+asyncpg://db/test")

    runner = DbProvider().get_migration_runner(settings)

    assert runner._database_url == settings.DATABASE_URL


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
    audit_gateway = provider.get_audit_log_gateway(MagicMock())
    assert provider.get_audit_log_reader(audit_gateway) is audit_gateway
    assert provider.get_audit_log_writer(audit_gateway) is audit_gateway
    assert isinstance(provider.get_command_repository(session), CommandRepository)
    assert isinstance(provider.get_script_repository(session), ScriptRepository)
    assert isinstance(
        provider.get_script_execution_repository(session), ScriptExecutionRepository
    )
    api_key_gateway = provider.get_api_key_gateway(MagicMock())
    assert provider.get_api_key_reader(api_key_gateway) is api_key_gateway
    assert provider.get_api_key_writer(api_key_gateway) is api_key_gateway
    health_repository = provider.get_health_repository(session)
    assert isinstance(health_repository, HealthRepository)
    assert provider.get_database_health_probe(health_repository) is health_repository
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
    from app.adapters.persistence.execution_stats import SqlAlchemyExecutionStatsGateway

    stats_gateway = provider.get_execution_stats_gateway(MagicMock())
    assert isinstance(stats_gateway, SqlAlchemyExecutionStatsGateway)
    assert provider.get_execution_stats_reader(stats_gateway) is stats_gateway
    from app.adapters.persistence.global_search import SqlAlchemyGlobalSearchGateway

    search_gateway = provider.get_global_search_gateway(MagicMock())
    assert isinstance(search_gateway, SqlAlchemyGlobalSearchGateway)
    assert provider.get_global_search_reader(search_gateway) is search_gateway


def test_connector_provider_resolves() -> None:
    from app.adapters.runtime.ssh import SSHConnectorFactory

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

    settings = MagicMock()
    settings.SSH_KNOWN_HOSTS_PATH = "/tmp/known_hosts"
    settings.SSH_STRICT_HOST_KEY_CHECKING = False
    factory = conn_provider.get_ssh_connector_factory(settings)
    credential_cipher = conn_provider.get_credential_cipher()
    node_reader = ScopedNodeConnectionReader(MagicMock())
    command_reader = ScopedCommandTemplateReader(MagicMock())
    execution_writer = ScopedScriptExecutionWriter(MagicMock())

    optional_outbox = svc_provider.get_request_audit_outbox(session)
    required_outbox = svc_provider.get_required_audit_outbox(MagicMock())
    audit_svc = svc_provider.get_audit_event_service(optional_outbox, required_outbox)
    assert isinstance(audit_svc, AuditEventService)
    assert isinstance(
        svc_provider.get_audit_log_service(MagicMock(), MagicMock()),
        AuditLogService,
    )

    node_command_svc = svc_provider.get_node_command_service(
        audit_svc,
        factory,
        node_reader,
        MagicMock(),
        credential_cipher,
        MagicMock(),
        MagicMock(),
    )
    node_bulk_command_svc = svc_provider.get_node_bulk_command_service(
        audit_svc,
        factory,
        node_reader,
        credential_cipher,
        MagicMock(),
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
        MagicMock(),
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
        MagicMock(),
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

    from app.application.services.execution_stats_service import ExecutionStatsService

    execution_stats_svc = svc_provider.get_execution_stats_service(MagicMock())
    assert isinstance(execution_stats_svc, ExecutionStatsService)

    from app.application.services.global_search_service import GlobalSearchService

    global_search_svc = svc_provider.get_global_search_service(MagicMock())
    assert isinstance(global_search_svc, GlobalSearchService)

    api_key_reader = MagicMock()
    api_key_writer = MagicMock()
    api_key_hasher = conn_provider.get_api_key_hasher()
    assert isinstance(
        svc_provider.get_api_key_authentication_service(
            api_key_reader,
            api_key_writer,
            api_key_hasher,
        ),
        APIKeyAuthenticationService,
    )
    assert isinstance(
        svc_provider.get_api_key_management_service(
            api_key_reader,
            api_key_writer,
            api_key_hasher,
        ),
        APIKeyManagementService,
    )

    config_svc = svc_provider.get_config_service(MagicMock(), MagicMock())
    assert isinstance(config_svc, ConfigService)

    scheduler = MagicMock()
    health = svc_provider.get_health_service(
        repo_provider.get_health_repository(session),
        scheduler,
        MagicMock(SCHEDULER_ENABLED=True),
    )
    assert isinstance(health, HealthService)
    assert (
        svc_provider.get_streaming_command_service(
            node_reader,
            factory,
            credential_cipher,
        )
        is not None
    )


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


def test_favorite_service_provider() -> None:
    from app.application.services.favorite_service import FavoriteService

    svc_provider = ServiceProvider()
    reader = MagicMock()
    writer = MagicMock()
    svc = svc_provider.get_favorite_service(reader, writer)
    assert isinstance(svc, FavoriteService)


def test_note_service_provider() -> None:
    from app.application.services.note_service import NoteService

    svc_provider = ServiceProvider()
    reader = MagicMock()
    writer = MagicMock()
    svc = svc_provider.get_note_service(reader, writer)
    assert isinstance(svc, NoteService)
