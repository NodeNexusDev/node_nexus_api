"""Unit tests for Docker parameter validation."""

import pytest

from app.core.docker_validation import validate_container_id, validate_image_name
from app.core.exceptions import DockerValidationError


class TestValidateContainerId:
    def test_valid_hex_id(self) -> None:
        assert validate_container_id("abc123def456") == "abc123def456"

    def test_valid_short_id(self) -> None:
        assert validate_container_id("abc123") == "abc123"

    def test_valid_with_hyphens(self) -> None:
        assert validate_container_id("abc-123-def-456") == "abc-123-def-456"

    def test_valid_full_id(self) -> None:
        full_id = "a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2"
        assert validate_container_id(full_id) == full_id

    def test_empty_string_raises(self) -> None:
        with pytest.raises(DockerValidationError, match="Invalid container ID"):
            validate_container_id("")

    def test_none_like_raises(self) -> None:
        with pytest.raises(DockerValidationError, match="Invalid container ID"):
            validate_container_id("abc; rm -rf /")

    def test_shell_injection_semicolon(self) -> None:
        with pytest.raises(DockerValidationError, match="Invalid container ID"):
            validate_container_id("abc;rm -rf /")

    def test_shell_injection_pipe(self) -> None:
        with pytest.raises(DockerValidationError, match="Invalid container ID"):
            validate_container_id("abc|cat /etc/passwd")

    def test_shell_injection_dollar(self) -> None:
        with pytest.raises(DockerValidationError, match="Invalid container ID"):
            validate_container_id("$(whoami)")

    def test_shell_injection_backtick(self) -> None:
        with pytest.raises(DockerValidationError, match="Invalid container ID"):
            validate_container_id("`whoami`")

    def test_shell_injection_space(self) -> None:
        with pytest.raises(DockerValidationError, match="Invalid container ID"):
            validate_container_id("abc def")


class TestValidateImageName:
    def test_valid_simple(self) -> None:
        assert validate_image_name("nginx") == "nginx"

    def test_valid_with_tag(self) -> None:
        assert validate_image_name("nginx:latest") == "nginx:latest"

    def test_valid_with_version_tag(self) -> None:
        assert validate_image_name("nginx:1.21") == "nginx:1.21"

    def test_valid_with_registry(self) -> None:
        assert (
            validate_image_name("docker.io/library/nginx:latest")
            == "docker.io/library/nginx:latest"
        )

    def test_valid_with_hyphen(self) -> None:
        assert validate_image_name("my-app:1.0") == "my-app:1.0"

    def test_valid_with_underscore(self) -> None:
        assert validate_image_name("my_app:1.0") == "my_app:1.0"

    def test_valid_with_dot(self) -> None:
        assert (
            validate_image_name("registry.example.com/app:1.0")
            == "registry.example.com/app:1.0"
        )

    def test_valid_with_slash(self) -> None:
        assert validate_image_name("library/nginx:latest") == "library/nginx:latest"

    def test_empty_string_raises(self) -> None:
        with pytest.raises(DockerValidationError, match="Invalid image name"):
            validate_image_name("")

    def test_shell_injection_semicolon(self) -> None:
        with pytest.raises(DockerValidationError, match="Invalid image name"):
            validate_image_name("nginx;rm -rf /")

    def test_shell_injection_pipe(self) -> None:
        with pytest.raises(DockerValidationError, match="Invalid image name"):
            validate_image_name("nginx|cat /etc/passwd")

    def test_shell_injection_dollar(self) -> None:
        with pytest.raises(DockerValidationError, match="Invalid image name"):
            validate_image_name("$(whoami)")

    def test_shell_injection_backtick(self) -> None:
        with pytest.raises(DockerValidationError, match="Invalid image name"):
            validate_image_name("`whoami`")

    def test_shell_injection_space(self) -> None:
        with pytest.raises(DockerValidationError, match="Invalid image name"):
            validate_image_name("nginx latest")

    def test_shell_injection_quotes(self) -> None:
        with pytest.raises(DockerValidationError, match="Invalid image name"):
            validate_image_name('nginx"test')

    def test_shell_injection_ampersand(self) -> None:
        with pytest.raises(DockerValidationError, match="Invalid image name"):
            validate_image_name("nginx&echo")
