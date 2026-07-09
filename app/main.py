"""FastAPI application entry point."""

from contextlib import asynccontextmanager

from dishka import make_async_container
from fastapi import FastAPI

from app.api.v1.health import router as health_router
from app.api.v1.nodes import router as nodes_router
from app.di.providers import AppProvider


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    container = make_async_container(AppProvider())
    app.state.container = container
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
    app.include_router(health_router)
    app.include_router(nodes_router, prefix="/api/v1")
    return app


app = create_app()
