"""FastAPI application entry point."""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import structlog
from alembic.config import Config as AlembicConfig
from dishka import make_async_container
from dishka.integrations.fastapi import FastapiProvider, setup_dishka
from fastapi import FastAPI

from alembic import command as alembic_command
from app.api.v1.audit import router as audit_router
from app.api.v1.health import router as health_router
from app.api.v1.nodes import router as nodes_router
from app.core.config import get_settings
from app.di.providers import AppProvider

logger = structlog.get_logger()

container = make_async_container(AppProvider(), FastapiProvider())


def _run_migrations_sync() -> None:
    """Run pending Alembic migrations (sync, runs in thread)."""
    settings = get_settings()
    alembic_cfg = AlembicConfig("alembic.ini")
    alembic_cfg.set_main_option("sqlalchemy.url", settings.DATABASE_URL)
    alembic_command.upgrade(alembic_cfg, "head")


async def _run_migrations() -> None:
    """Run pending Alembic migrations."""
    await asyncio.to_thread(_run_migrations_sync)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Application lifespan manager."""
    logger.info("app.startup")
    try:
        await _run_migrations()
        logger.info("migrations.applied")
    except Exception:
        logger.exception("migrations.failed")
    yield
    await container.close()
    logger.info("app.shutdown")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title="Node Nexus API",
        description="REST API for managing server nodes",
        version="0.1.0",
        lifespan=lifespan,
    )
    setup_dishka(container, app)
    app.include_router(health_router)
    app.include_router(nodes_router, prefix="/api/v1")
    app.include_router(audit_router, prefix="/api/v1")
    return app


app = create_app()
