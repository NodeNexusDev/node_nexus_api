"""OpenTelemetry telemetry configuration — infrastructure adapter."""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    from fastapi import FastAPI

    from app.core.config import Settings

logger = structlog.get_logger()


def init_telemetry(app: FastAPI, settings: Settings) -> None:
    """Initialize OpenTelemetry tracing.

    Configures TracerProvider with OTLP exporter and instruments
    FastAPI and SQLAlchemy.
    """
    if not settings.OTEL_ENABLED:
        logger.debug("telemetry.disabled")
        return

    try:
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
            OTLPSpanExporter,
        )
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor

        endpoint = settings.OTEL_ENDPOINT
        service_name = settings.OTEL_SERVICE_NAME

        resource = Resource.create({"service.name": service_name})
        provider = TracerProvider(resource=resource)
        exporter = OTLPSpanExporter(endpoint=endpoint)
        provider.add_span_processor(BatchSpanProcessor(exporter))
        trace.set_tracer_provider(provider)

        # Instrument FastAPI
        FastAPIInstrumentor.instrument_app(app)

        # Instrument SQLAlchemy
        SQLAlchemyInstrumentor().instrument()

        logger.info(
            "telemetry.initialized",
            endpoint=endpoint,
            service_name=service_name,
        )
    except Exception as exc:
        logger.warning("telemetry.init_failed", error=str(exc))
