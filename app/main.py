"""FastAPI application entry point."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from dishka import make_async_container
from dishka.integrations.fastapi import FastapiProvider, setup_dishka
from fastapi import FastAPI

from app.api.v1.health import router as health_router
from app.api.v1.nodes import router as nodes_router
from app.di.providers import AppProvider

container = make_async_container(AppProvider(), FastapiProvider())


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Application lifespan manager."""
    yield
    await container.close()


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
    return app


app = create_app()
