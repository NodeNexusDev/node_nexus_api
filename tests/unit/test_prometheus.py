"""Tests for Prometheus metrics integration."""


class TestPrometheusConfig:
    """Tests for Prometheus configuration settings."""

    def test_prometheus_enabled_default(self):
        """PROMETHEUS_ENABLED defaults to True."""
        from app.core.config import get_settings

        settings = get_settings()
        assert settings.PROMETHEUS_ENABLED is True

    def test_metrics_path_configurable(self):
        """PROMETHEUS_PATH setting is used."""
        from app.core.config import get_settings

        settings = get_settings()
        assert settings.PROMETHEUS_PATH == "/metrics"

    def test_prometheus_imports_work(self):
        """prometheus-fastapi-instrumentator is importable."""
        from prometheus_fastapi_instrumentator import Instrumentator

        inst = Instrumentator()
        assert inst is not None


class TestMiddlewareExclusions:
    """Tests that /metrics is excluded from timeout and rate limiting."""

    def test_timeout_middleware_excludes_metrics(self):
        """TimeoutMiddleware skips /metrics path."""
        from app.api.middleware import TimeoutMiddleware

        assert "/metrics" in TimeoutMiddleware.EXCLUDED_PATHS

    def test_rate_limit_middleware_excludes_metrics(self):
        """RateLimitMiddleware skips /metrics path."""
        from app.api.middleware import RateLimitMiddleware

        assert "/metrics" in RateLimitMiddleware.EXCLUDED_PATHS

    def test_health_still_excluded(self):
        """Health paths still excluded from both middlewares."""
        from app.api.middleware import RateLimitMiddleware, TimeoutMiddleware

        assert "/health" in TimeoutMiddleware.EXCLUDED_PATHS
        assert "/ready" in TimeoutMiddleware.EXCLUDED_PATHS
        assert "/health" in RateLimitMiddleware.EXCLUDED_PATHS
        assert "/ready" in RateLimitMiddleware.EXCLUDED_PATHS

    def test_metrics_not_excluded_from_health_router(self):
        """/metrics is separate from /health in health router."""
        # /metrics endpoint is exposed by instrumentator, not the health router
        from app.api.v2 import health

        assert hasattr(health, "router")
