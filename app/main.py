"""FastAPI application entry point."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as pkg_version

import structlog
from dishka.integrations.fastapi import setup_dishka
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.routing import APIRoute
from prometheus_fastapi_instrumentator import Instrumentator

from app.adapters.lifecycle.migration_runner import MigrationRunner
from app.api.error_mapping import domain_error_handler
from app.api.middleware import (
    RateLimitMiddleware,
    RequestLoggingMiddleware,
    TimeoutMiddleware,
)
from app.api.v1.api_keys import router as api_keys_router
from app.api.v1.audit import router as audit_router
from app.api.v1.commands import router as commands_router
from app.api.v1.config import router as config_router
from app.api.v1.docker import router as docker_router
from app.api.v1.docker_bulk import router as docker_bulk_router
from app.api.v1.health import router as health_router
from app.api.v1.nodes import router as nodes_router
from app.api.v1.scripts import router as scripts_router
from app.api.v1.websocket import router as ws_router
from app.application.services.schedule_restorer import ScheduleRestorer
from app.application.services.scheduled_script_executor import (
    ScheduledScriptExecutor,
)
from app.core.config import get_settings
from app.core.exceptions import DomainError
from app.core.logging import configure_logging
from app.core.scheduler import ScriptScheduler
from app.core.telemetry import init_telemetry
from app.di.container import container

logger = structlog.get_logger()  # operational: lifecycle, performance
audit = structlog.get_logger("audit")  # security: exceptions, errors


def stable_operation_id(route: APIRoute) -> str:
    """Build a deterministic OpenAPI operation identifier."""
    methods = "_".join(sorted(method.lower() for method in route.methods or []))
    path = (
        route.path_format.strip("/")
        .replace("/", "_")
        .replace("{", "")
        .replace("}", "")
        .replace("-", "_")
    )
    return f"{methods}_{path or 'root'}"


async def _cleanup_audit_logs() -> None:
    """Cleanup old audit logs on startup."""
    try:
        from app.application.services.audit_cleanup_job import AuditCleanupJob

        job = await container.get(AuditCleanupJob)
        deleted = await job.run()
        if deleted > 0:
            logger.info("audit.cleanup.startup", deleted=deleted)
    except Exception:
        logger.warning("audit.cleanup.startup.failed")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Application lifespan manager."""
    settings = get_settings()
    configure_logging(log_level=settings.LOG_LEVEL, debug=settings.DEBUG)
    logger.info("app.startup")
    if settings.AUTO_MIGRATE:
        migration_runner = await container.get(MigrationRunner)
        await migration_runner.run()
        logger.info("migrations.applied")
    else:
        logger.info("migrations.skipped", reason="AUTO_MIGRATE is disabled")
    scheduler = await container.get(ScriptScheduler)
    scheduled_executor = await container.get(ScheduledScriptExecutor)
    restorer = await container.get(ScheduleRestorer)
    from app.adapters.persistence.audit_outbox_worker import AuditOutboxWorker

    await container.get(AuditOutboxWorker)
    scheduler.configure_executor(scheduled_executor.execute)
    if settings.SCHEDULER_ENABLED:

        async def restore() -> tuple[int, int]:
            result = await restorer.run()
            logger.info(
                "scheduler.restore.completed",
                restored=result.restored,
                failed=result.failed,
            )
            return result.restored, result.failed

        scheduler.configure_reconciler(restore)
        await restore()
        scheduler.start_reconciliation()
    else:
        restorer.mark_disabled()
    await _cleanup_audit_logs()

    try:
        yield
    finally:
        await container.close()
        logger.info("app.shutdown")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    settings = get_settings()
    try:
        app_version = pkg_version("node-nexus-api")
    except PackageNotFoundError:
        app_version = "unknown"
    app = FastAPI(
        title="Node Nexus API",
        description=(
            "REST API for managing server nodes, SSH commands, scripts, "
            "and remote Docker resources."
        ),
        version=app_version,
        contact={
            "name": "Node Nexus maintainers",
            "url": "https://github.com/NodeNexusDev/node_nexus_api",
        },
        license_info={
            "name": "MIT",
            "identifier": "MIT",
        },
        generate_unique_id_function=stable_operation_id,
        lifespan=lifespan,
        openapi_tags=[
            {"name": "nodes", "description": "CRUD-операции и SSH-команды для нод"},
            {"name": "commands", "description": "Шаблоны команд с параметрами"},
            {"name": "scripts", "description": "Пайплайны команд для нод"},
            {"name": "audit", "description": "Просмотр аудит-лога операций"},
            {
                "name": "docker",
                "description": "Управление Docker контейнерами на нодах",
            },
            {"name": "api-keys", "description": "API key lifecycle and scopes"},
            {"name": "config", "description": "Configuration backup and restore"},
            {"name": "health", "description": "Liveness and readiness probes"},
        ],
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(RequestLoggingMiddleware)
    app.add_middleware(TimeoutMiddleware, timeout=settings.REQUEST_TIMEOUT)
    app.add_middleware(
        RateLimitMiddleware,
        requests=settings.RATE_LIMIT_REQUESTS,
        window=settings.RATE_LIMIT_WINDOW,
    )

    @app.middleware("http")
    async def _security_headers(request: Request, call_next):  # noqa: ANN001
        """Add security headers to every response."""
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Strict-Transport-Security"] = (
            "max-age=31536000; includeSubDomains"
        )
        return response

    app.add_exception_handler(DomainError, domain_error_handler)

    setup_dishka(container, app)
    app.include_router(health_router)
    app.include_router(nodes_router, prefix="/api/v1")
    app.include_router(commands_router, prefix="/api/v1")
    app.include_router(scripts_router, prefix="/api/v1")
    app.include_router(audit_router, prefix="/api/v1")
    app.include_router(api_keys_router, prefix="/api/v1")
    app.include_router(config_router, prefix="/api/v1")
    app.include_router(docker_router, prefix="/api/v1")
    app.include_router(docker_bulk_router, prefix="/api/v1")
    app.include_router(ws_router, prefix="/api/v1")

    # Prometheus metrics (sits inside all custom middleware)
    if settings.PROMETHEUS_ENABLED:
        instrumentator = Instrumentator(
            should_group_status_codes=False,
            should_ignore_untemplated=True,
            excluded_handlers=["/health", "/ready", settings.PROMETHEUS_PATH],
        )
        instrumentator.instrument(app)
        instrumentator.expose(app, endpoint=settings.PROMETHEUS_PATH)

    # OpenTelemetry tracing
    init_telemetry(app, settings)

    return app


app = create_app()
