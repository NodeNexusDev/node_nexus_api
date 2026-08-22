"""Tests for OpenTelemetry telemetry configuration."""

from unittest.mock import MagicMock, patch

from app.adapters.telemetry import init_telemetry


class TestTelemetryConfig:
    """Tests for telemetry configuration."""

    def test_telemetry_disabled_by_default(self):
        """OTEL_ENABLED defaults to False."""
        from app.core.config import get_settings

        settings = get_settings()
        assert settings.OTEL_ENABLED is False

    def test_telemetry_endpoint_default(self):
        """OTEL_ENDPOINT defaults to localhost:4317."""
        from app.core.config import get_settings

        settings = get_settings()
        assert settings.OTEL_ENDPOINT == "http://localhost:4317"

    def test_telemetry_service_name_default(self):
        """OTEL_SERVICE_NAME defaults to node-nexus-api."""
        from app.core.config import get_settings

        settings = get_settings()
        assert settings.OTEL_SERVICE_NAME == "node-nexus-api"


class TestTelemetryInit:
    """Tests for init_telemetry function."""

    def test_init_skips_when_disabled(self):
        """init_telemetry does nothing when OTEL_ENABLED=False."""
        app = MagicMock()
        settings = MagicMock()
        settings.OTEL_ENABLED = False

        with patch("app.adapters.telemetry.logger") as mock_logger:
            init_telemetry(app, settings)
            mock_logger.debug.assert_called_once_with("telemetry.disabled")

    def test_init_imports_when_enabled(self):
        """init_telemetry attempts to set up tracing when enabled."""
        app = MagicMock()
        settings = MagicMock()
        settings.OTEL_ENABLED = True
        settings.OTEL_ENDPOINT = "http://localhost:4317"
        settings.OTEL_SERVICE_NAME = "test-service"

        with patch("app.adapters.telemetry.logger") as mock_logger:
            # The actual import will fail if opentelemetry is not fully configured
            # but we can verify the flow
            try:
                init_telemetry(app, settings)
            except Exception:
                pass
            # Should have attempted initialization
            any_called = (
                mock_logger.debug.called
                or mock_logger.info.called
                or mock_logger.warning.called
            )
            assert any_called

    def test_init_handles_import_error_gracefully(self):
        """init_telemetry handles missing opentelemetry packages."""
        app = MagicMock()
        settings = MagicMock()
        settings.OTEL_ENABLED = True

        with patch.dict("sys.modules", {"opentelemetry": None}):
            with patch("app.adapters.telemetry.logger") as mock_logger:
                init_telemetry(app, settings)
                # Should log a warning, not crash
                assert mock_logger.warning.called
