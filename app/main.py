"""FastAPI application entry point."""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import structlog
from alembic.config import Config as AlembicConfig
from dishka import make_async_container
from dishka.integrations.fastapi import FastapiProvider, setup_dishka
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from alembic import command as alembic_command
from app.api.middleware import RequestLoggingMiddleware
from app.api.v1.api_keys import router as api_keys_router
from app.api.v1.audit import router as audit_router
from app.api.v1.commands import router as commands_router
from app.api.v1.docker import router as docker_router
from app.api.v1.health import router as health_router
from app.api.v1.nodes import router as nodes_router
from app.api.v1.scripts import router as scripts_router
from app.core.config import get_settings
from app.core.exceptions import (
    APIKeyNotFoundError,
    APIKeyRevokedError,
    AuthenticationError,
    CommandNotFoundError,
    ConnectionFailedError,
    ContainerNotFoundError,
    DockerDaemonError,
    DockerError,
    DockerValidationError,
    DomainError,
    ImageNotFoundError,
    NodeNotFoundError,
    ScriptNotFoundError,
    TagNotFoundError,
    TemplateRenderError,
)
from app.core.logging import configure_logging
from app.di.providers import AppProvider

logger = structlog.get_logger()  # operational: lifecycle, performance
audit = structlog.get_logger("audit")  # security: exceptions, errors

container = make_async_container(AppProvider(), FastapiProvider())


def _run_migrations_sync() -> None:
    """Run pending Alembic migrations (sync, runs in thread)."""
    settings = get_settings()
    alembic_cfg = AlembicConfig("alembic.ini")
    alembic_cfg.set_main_option("sqlalchemy.url", settings.DATABASE_URL)
    try:
        alembic_command.upgrade(alembic_cfg, "head")
    except Exception as exc:
        logger.exception("migrations.failed", database=settings.DATABASE_URL)
        raise RuntimeError(
            f"Database migrations failed. "
            f"Ensure the database is reachable and the schema is compatible. "
            f"Original error: {exc}"
        ) from exc


async def _run_migrations() -> None:
    """Run pending Alembic migrations."""
    await asyncio.to_thread(_run_migrations_sync)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Application lifespan manager."""
    settings = get_settings()
    configure_logging(log_level=settings.LOG_LEVEL, debug=settings.DEBUG)
    logger.info("app.startup")
    await _run_migrations()
    logger.info("migrations.applied")

    yield

    await container.close()
    logger.info("app.shutdown")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    settings = get_settings()
    app = FastAPI(
        title="Node Nexus API",
        description="REST API для управления серверными нодами с SSH-подключениями",
        version="0.2.1",
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

    @app.exception_handler(DomainError)
    async def _domain_error_handler(request: Request, exc: DomainError):  # noqa: ANN001
        audit.error("app.exception", error_type=type(exc).__name__, detail=str(exc))
        _error_status_map: dict[type[DomainError], int] = {
            NodeNotFoundError: 404,
            CommandNotFoundError: 404,
            ScriptNotFoundError: 404,
            APIKeyNotFoundError: 401,
            APIKeyRevokedError: 401,
            AuthenticationError: 401,
            TagNotFoundError: 404,
            ConnectionFailedError: 503,
            TemplateRenderError: 422,
            DockerError: 502,
            ContainerNotFoundError: 404,
            ImageNotFoundError: 404,
            DockerDaemonError: 503,
            DockerValidationError: 422,
        }
        status_code = _error_status_map.get(type(exc), 422)
        return JSONResponse(
            status_code=status_code,
            content={"detail": str(exc)},
        )

    setup_dishka(container, app)
    app.include_router(health_router)
    app.include_router(nodes_router, prefix="/api/v1")
    app.include_router(commands_router, prefix="/api/v1")
    app.include_router(scripts_router, prefix="/api/v1")
    app.include_router(audit_router, prefix="/api/v1")
    app.include_router(api_keys_router, prefix="/api/v1")
    app.include_router(docker_router, prefix="/api/v1")
    return app


app = create_app()
