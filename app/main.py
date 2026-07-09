"""FastAPI application entry point."""

from fastapi import FastAPI


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title="Node Nexus API",
        description="REST API for managing server nodes",
        version="0.1.0",
    )
    return app


app = create_app()
