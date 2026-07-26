"""OpenTelemetry telemetry configuration."""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    from fastapi import FastAPI

logger = structlog.get_logger()


def init_telemetry(app: FastAPI, settings: object) -> None:
    """Initialize OpenTelemetry tracing.

    Configures TracerProvider with OTLP exporter and instruments
    FastAPI and SQLAlchemy.
    """
    enabled = getattr(settings, "OTEL_ENABLED", False)
    if not enabled:
        logger.debug("telemetry.disabled")
        return

    try:
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
            OTLPSpanExporter,
        )
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
        from opentelemetry.resources import Resource  # type: ignore
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor

        endpoint = getattr(settings, "OTEL_ENDPOINT", "http://localhost:4317")
        service_name = getattr(settings, "OTEL_SERVICE_NAME", "node-nexus-api")

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
