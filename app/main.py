"""FastAPI application entry point."""

from fastapi import FastAPI

from app.api.v1.health import router as health_router
from app.api.v1.nodes import router as nodes_router


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title="Node Nexus API",
        description="REST API for managing server nodes",
        version="0.1.0",
    )
    app.include_router(health_router)
    app.include_router(nodes_router, prefix="/api/v1")
    return app


app = create_app()
