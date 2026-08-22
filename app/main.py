"""FastAPI application entry point."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as pkg_version

from dishka.integrations.fastapi import setup_dishka
from fastapi import FastAPI, HTTPException, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from prometheus_fastapi_instrumentator import Instrumentator
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.adapters.lifecycle.application_startup import ApplicationStartup
from app.api.error_mapping import domain_error_handler
from app.api.middleware import (
    ApiVersionMiddleware,
    CommitOnResponseMiddleware,
    RateLimitMiddleware,
    RequestIdMiddleware,
    RequestLoggingMiddleware,
    TimeoutMiddleware,
)
from app.api.v1.api_keys import router as api_keys_router
from app.api.v1.audit import router as audit_router
from app.api.v1.commands import router as commands_router
from app.api.v1.config import router as config_router
from app.api.v1.dashboard import router as dashboard_router
from app.api.v1.docker import router as docker_router
from app.api.v1.docker_bulk import router as docker_bulk_router
from app.api.v1.events import router as events_router
from app.api.v1.favorites import router as favorites_router
from app.api.v1.health import router as health_router
from app.api.v1.internal import router as internal_router
from app.api.v1.nodes import router as nodes_router
from app.api.v1.nodes_bulk import router as nodes_bulk_router
from app.api.v1.notes import router as notes_router
from app.api.v1.scripts import router as scripts_router
from app.api.v1.scripts_bulk import router as scripts_bulk_router
from app.api.v1.search import router as search_router
from app.api.v1.tags import router as tags_router
from app.api.v1.websocket import router as ws_router
from app.core.config import get_settings
from app.core.exceptions import DomainError
from app.core.telemetry import init_telemetry
from app.di.container import container


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


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Application lifespan manager."""
    startup = await container.get(ApplicationStartup)
    await startup.run()
    try:
        yield
    finally:
        await container.close()


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
            {"name": "bulk", "description": "Массовые операции над нодами"},
            {"name": "audit", "description": "Просмотр аудит-лога операций"},
            {
                "name": "docker",
                "description": "Управление Docker контейнерами на нодах",
            },
            {"name": "api-keys", "description": "API key lifecycle and scopes"},
            {"name": "config", "description": "Configuration backup and restore"},
            {"name": "health", "description": "Liveness and readiness probes"},
            {"name": "dashboard", "description": "Dashboard overview and metrics"},
            {"name": "favorites", "description": "Favorite nodes/scripts/commands"},
            {"name": "notes", "description": "Notes for nodes"},
            {"name": "tags", "description": "Global tag management"},
            {"name": "search", "description": "Global search across entities"},
            {"name": "events", "description": "Real-time event streaming"},
        ],
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH"],
        allow_headers=["Authorization", "Content-Type", "X-API-Key", "X-API-Version"],
    )
    app.add_middleware(RequestLoggingMiddleware)
    app.add_middleware(
        ApiVersionMiddleware,
        supported_versions=settings.SUPPORTED_API_VERSIONS,
    )
    app.add_middleware(RequestIdMiddleware)
    app.add_middleware(TimeoutMiddleware, timeout=settings.REQUEST_TIMEOUT)
    app.add_middleware(
        RateLimitMiddleware,
        requests=settings.RATE_LIMIT_REQUESTS,
        window=settings.RATE_LIMIT_WINDOW,
    )
    app.add_middleware(CommitOnResponseMiddleware)

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

    @app.exception_handler(HTTPException)
    async def _http_exception_handler(request: Request, exc: HTTPException):
        """Return HTTPException detail together with the request id."""
        request_id = getattr(request.state, "request_id", None)
        content: dict[str, object] = {"detail": exc.detail}
        if request_id:
            content["request_id"] = request_id
        return JSONResponse(
            status_code=exc.status_code,
            content=content,
            headers=exc.headers or {},
        )

    @app.exception_handler(RequestValidationError)
    async def _validation_exception_handler(
        request: Request, exc: RequestValidationError
    ):
        """Return validation errors together with the request id."""
        request_id = getattr(request.state, "request_id", None)
        content: dict[str, object] = {"detail": jsonable_encoder(exc.errors())}
        if request_id:
            content["request_id"] = request_id
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            content=content,
        )

    @app.exception_handler(StarletteHTTPException)
    async def _starlette_http_exception_handler(
        request: Request, exc: StarletteHTTPException
    ):
        """Return Starlette HTTPException detail together with the request id."""
        request_id = getattr(request.state, "request_id", None)
        content: dict[str, object] = {"detail": exc.detail}
        if request_id:
            content["request_id"] = request_id
        return JSONResponse(
            status_code=exc.status_code,
            content=content,
            headers=exc.headers or {},
        )

    app.add_exception_handler(DomainError, domain_error_handler)

    setup_dishka(container, app)
    app.include_router(health_router)
    app.include_router(nodes_bulk_router, prefix="/api/v1")
    app.include_router(nodes_router, prefix="/api/v1")
    app.include_router(commands_router, prefix="/api/v1")
    app.include_router(scripts_router, prefix="/api/v1")
    app.include_router(scripts_bulk_router, prefix="/api/v1")
    app.include_router(audit_router, prefix="/api/v1")
    app.include_router(dashboard_router, prefix="/api/v1")
    app.include_router(api_keys_router, prefix="/api/v1")
    app.include_router(config_router, prefix="/api/v1")
    app.include_router(docker_router, prefix="/api/v1")
    app.include_router(docker_bulk_router, prefix="/api/v1")
    app.include_router(events_router, prefix="/api/v1")
    app.include_router(ws_router, prefix="/api/v1")
    app.include_router(search_router, prefix="/api/v1")
    app.include_router(tags_router, prefix="/api/v1")
    app.include_router(favorites_router, prefix="/api/v1")
    app.include_router(notes_router, prefix="/api/v1")
    if settings.E2E_ENABLED:
        app.include_router(internal_router, prefix="/api/v1")

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
