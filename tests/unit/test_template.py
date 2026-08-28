"""Unit tests for template renderer."""

import pytest

from app.application.dto.command_management import CommandParameterDTO
from app.core.exceptions import TemplateRenderError
from app.core.template import render_command


class TestRenderCommand:
    def test_simple_substitution(self) -> None:
        result = render_command(
            "echo {name}",
            [CommandParameterDTO(name="name", type="string", required=True)],
            {"name": "hello"},
        )
        assert result == "echo hello"

    def test_multiple_params(self) -> None:
        params = [
            CommandParameterDTO(name="host", type="string", required=True),
            CommandParameterDTO(name="port", type="integer", required=True),
        ]
        result = render_command(
            "ssh {host}:{port}", params, {"host": "10.0.0.1", "port": "22"}
        )
        assert result == "ssh 10.0.0.1:22"

    def test_default_value(self) -> None:
        params = [
            CommandParameterDTO(
                name="timeout", type="integer", required=False, default=30
            )
        ]
        result = render_command("curl --timeout {timeout} url", params, {})
        assert result == "curl --timeout 30 url"

    def test_user_value_overrides_default(self) -> None:
        params = [
            CommandParameterDTO(
                name="timeout", type="integer", required=False, default=30
            )
        ]
        result = render_command(
            "curl --timeout {timeout} url", params, {"timeout": "60"}
        )
        assert result == "curl --timeout 60 url"

    def test_no_placeholders(self) -> None:
        result = render_command("df -h", [], {})
        assert result == "df -h"

    def test_undeclared_placeholder_raises(self) -> None:
        with pytest.raises(TemplateRenderError, match="Undeclared placeholders"):
            render_command("echo {unknown}", [], {})

    def test_missing_required_param_raises(self) -> None:
        params = [CommandParameterDTO(name="service", type="string", required=True)]
        with pytest.raises(TemplateRenderError, match="Missing required parameters"):
            render_command("systemctl restart {service}", params, {})

    def test_optional_param_not_provided_is_ok(self) -> None:
        params = [CommandParameterDTO(name="extra", type="string", required=False)]
        result = render_command("echo test", params, {})
        assert result == "echo test"

    def test_optional_placeholder_left_intact(self) -> None:
        params = [CommandParameterDTO(name="optional", type="string", required=False)]
        result = render_command("echo {optional}", params, {})
        assert result == "echo {optional}"
