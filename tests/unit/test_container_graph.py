"""Smoke tests for the complete HTTP and lifecycle dependency graph."""

from typing import cast
from unittest.mock import MagicMock

from dishka import Provider, Scope, make_async_container, provide
from dishka.integrations.fastapi import FastapiProvider

from app.adapters.lifecycle.application_startup import ApplicationStartup
from app.adapters.persistence.audit_outbox_worker import AuditOutboxWorker
from app.application.services.api_key_authentication import (
    APIKeyAuthenticationService,
)
from app.application.services.api_key_management import APIKeyManagementService
from app.application.services.audit_log_service import AuditLogService
from app.application.services.config_service import ConfigService
from app.application.services.schedule_management import ScheduleManagementService
from app.application.services.script_execution_service import ScriptExecutionService
from app.application.services.streaming_command_service import StreamingCommandService
from app.core.config import Settings
from app.di.providers import AppProvider
from app.services.command_execution_service import CommandExecutionService
from app.services.command_management_service import CommandManagementService
from app.services.docker.bulk_service import DockerBulkService
from app.services.docker.container_service import DockerContainerService
from app.services.docker.image_service import DockerImageService
from app.services.docker.resource_service import DockerResourceService
from app.services.health_service import HealthService
from app.services.node_bulk_command_service import NodeBulkCommandService
from app.services.node_command_service import NodeCommandService
from app.services.node_management_service import NodeManagementService
from app.services.node_metrics_service import NodeMetricsService
from app.services.script_history_service import ScriptHistoryService
from app.services.script_management_service import ScriptManagementService

HTTP_DEPENDENCIES = (
    APIKeyAuthenticationService,
    APIKeyManagementService,
    AuditLogService,
    CommandExecutionService,
    CommandManagementService,
    ConfigService,
    DockerBulkService,
    DockerContainerService,
    DockerImageService,
    DockerResourceService,
    HealthService,
    NodeBulkCommandService,
    NodeCommandService,
    NodeManagementService,
    NodeMetricsService,
    ScheduleManagementService,
    ScriptExecutionService,
    ScriptHistoryService,
    ScriptManagementService,
    StreamingCommandService,
)


class GraphOverrides(Provider):
    """Replace side-effectful APP dependencies while preserving the graph."""

    @provide(scope=Scope.APP, override=True)
    def get_settings(self) -> Settings:
        return Settings(
            DATABASE_URL="sqlite+aiosqlite:///:memory:",
            SECRET_KEY="test-secret-key-for-container-graph",
            AUTO_MIGRATE=False,
            SCHEDULER_ENABLED=False,
        )

    @provide(scope=Scope.APP, override=True)
    def get_audit_worker(self) -> AuditOutboxWorker:
        return cast(AuditOutboxWorker, MagicMock())


async def test_resolves_all_router_and_lifecycle_dependencies() -> None:
    container = make_async_container(
        AppProvider(),
        GraphOverrides(),
        FastapiProvider(),
    )
    try:
        startup = await container.get(ApplicationStartup)
        assert isinstance(startup, ApplicationStartup)

        async with container() as request_container:
            for dependency in HTTP_DEPENDENCIES:
                assert isinstance(
                    await request_container.get(dependency),
                    dependency,
                )
    finally:
        await container.close()
