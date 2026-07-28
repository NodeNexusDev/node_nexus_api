"""Tests for DI provider wiring — resolves all services from container."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.di.providers import (
    ConnectorProvider,
    DbProvider,
    RepositoryProvider,
    SchedulerProvider,
    ServiceProvider,
)
from app.repositories.api_key_repo import APIKeyRepository
from app.repositories.audit_repo import AuditLogRepository
from app.repositories.command_repo import CommandRepository
from app.repositories.node_repo import NodeRepository
from app.repositories.script_execution_repo import ScriptExecutionRepository
from app.repositories.script_repo import ScriptRepository
from app.services.api_key_service import APIKeyService
from app.services.audit_service import AuditService
from app.services.command_service import CommandService
from app.services.config_service import ConfigService
from app.services.docker_service import DockerService
from app.services.node_service import NodeService
from app.services.script_service import ScriptService


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
    resource = provider.get_script_scheduler()

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


def test_connector_provider_resolves() -> None:
    from app.core.connectors.ssh import SSHConnectorFactory

    provider = ConnectorProvider()
    assert isinstance(provider.get_ssh_connector_factory(), SSHConnectorFactory)


def test_service_provider_resolves() -> None:
    from app.adapters.persistence.command_reader import ScopedCommandTemplateReader
    from app.adapters.persistence.node_reader import ScopedNodeConnectionReader

    session = MagicMock()
    repo_provider = RepositoryProvider()
    conn_provider = ConnectorProvider()
    svc_provider = ServiceProvider()

    node_repo = repo_provider.get_node_repository(session)
    audit_repo = repo_provider.get_audit_repository(session)
    cmd_repo = repo_provider.get_command_repository(session)
    script_repo = repo_provider.get_script_repository(session)
    exec_repo = repo_provider.get_script_execution_repository(session)
    api_key_repo = repo_provider.get_api_key_repository(session)
    factory = conn_provider.get_ssh_connector_factory()
    node_reader = ScopedNodeConnectionReader(MagicMock())
    command_reader = ScopedCommandTemplateReader(MagicMock())

    audit_svc = svc_provider.get_audit_service(audit_repo)
    assert isinstance(audit_svc, AuditService)

    node_svc = svc_provider.get_node_service(node_repo, audit_svc, factory, node_reader)
    assert isinstance(node_svc, NodeService)

    cmd_svc = svc_provider.get_command_service(
        cmd_repo,
        node_repo,
        audit_svc,
        factory,
        command_reader,
        node_reader,
    )
    assert isinstance(cmd_svc, CommandService)

    script_svc = svc_provider.get_script_service(
        script_repo, cmd_repo, node_repo, exec_repo, audit_svc, factory
    )
    assert isinstance(script_svc, ScriptService)

    api_key_svc = svc_provider.get_api_key_service(api_key_repo)
    assert isinstance(api_key_svc, APIKeyService)

    docker_svc = svc_provider.get_docker_service(
        node_repo, audit_svc, factory, node_reader
    )
    assert isinstance(docker_svc, DockerService)

    config_svc = svc_provider.get_config_service(node_repo, cmd_repo, script_repo)
    assert isinstance(config_svc, ConfigService)
