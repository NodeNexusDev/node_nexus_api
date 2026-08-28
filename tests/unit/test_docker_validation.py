"""Unit tests for Docker parameter validation."""

import pytest

from app.core.docker_validation import (
    validate_build_arg_key,
    validate_container_id,
    validate_container_name,
    validate_container_new_name,
    validate_docker_host,
    validate_env_vars,
    validate_image_name,
    validate_image_tag,
    validate_ip_address,
    validate_labels,
    validate_network_driver,
    validate_network_name,
    validate_port_mappings,
    validate_restart_policy,
    validate_volume_mounts,
    validate_volume_name,
)
from app.core.exceptions import DockerValidationError
from tests.typing import as_unvalidated


class TestValidateContainerId:
    def test_valid_hex_id(self) -> None:
        assert validate_container_id("abc123def456") == "abc123def456"

    def test_valid_short_id(self) -> None:
        assert validate_container_id("abc123") == "abc123"

    def test_valid_with_hyphens(self) -> None:
        assert validate_container_id("abc-123-def-456") == "abc-123-def-456"

    def test_valid_container_name(self) -> None:
        assert validate_container_id("e2e-test_ctr.1") == "e2e-test_ctr.1"

    def test_valid_full_id(self) -> None:
        full_id = "a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2"
        assert validate_container_id(full_id) == full_id

    def test_empty_string_raises(self) -> None:
        with pytest.raises(DockerValidationError, match="Invalid container reference"):
            validate_container_id("")

    def test_none_like_raises(self) -> None:
        with pytest.raises(DockerValidationError, match="Invalid container reference"):
            validate_container_id("abc; rm -rf /")

    def test_shell_injection_semicolon(self) -> None:
        with pytest.raises(DockerValidationError, match="Invalid container reference"):
            validate_container_id("abc;rm -rf /")

    def test_shell_injection_pipe(self) -> None:
        with pytest.raises(DockerValidationError, match="Invalid container reference"):
            validate_container_id("abc|cat /etc/passwd")

    def test_shell_injection_dollar(self) -> None:
        with pytest.raises(DockerValidationError, match="Invalid container reference"):
            validate_container_id("$(whoami)")

    def test_shell_injection_backtick(self) -> None:
        with pytest.raises(DockerValidationError, match="Invalid container reference"):
            validate_container_id("`whoami`")

    def test_shell_injection_space(self) -> None:
        with pytest.raises(DockerValidationError, match="Invalid container reference"):
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


class TestValidateContainerName:
    def test_valid_name(self) -> None:
        assert validate_container_name("my-container_1") == "my-container_1"

    def test_empty_raises(self) -> None:
        with pytest.raises(DockerValidationError, match="Invalid container name"):
            validate_container_name("")

    def test_invalid_start_char_raises(self) -> None:
        with pytest.raises(DockerValidationError, match="Invalid container name"):
            validate_container_name("-invalid")


class TestValidateImageTag:
    def test_valid_tag(self) -> None:
        assert validate_image_tag("repo:tag") == "repo:tag"

    def test_empty_raises(self) -> None:
        with pytest.raises(DockerValidationError, match="Invalid image tag"):
            validate_image_tag("")

    def test_invalid_char_raises(self) -> None:
        with pytest.raises(DockerValidationError, match="Invalid image tag"):
            validate_image_tag("repo tag")


class TestValidateNetworkName:
    def test_valid_name(self) -> None:
        assert validate_network_name("bridge") == "bridge"

    def test_empty_raises(self) -> None:
        with pytest.raises(DockerValidationError, match="Invalid network name"):
            validate_network_name("")

    def test_invalid_char_raises(self) -> None:
        with pytest.raises(DockerValidationError, match="Invalid network name"):
            validate_network_name("net;work")


class TestValidateRestartPolicy:
    def test_valid_policies(self) -> None:
        for policy in ["no", "always", "on-failure", "unless-stopped"]:
            assert validate_restart_policy(policy) == policy

    def test_invalid_policy_raises(self) -> None:
        with pytest.raises(DockerValidationError, match="Invalid restart policy"):
            validate_restart_policy("never")


class TestValidatePortMappings:
    def test_valid_mapping(self) -> None:
        assert validate_port_mappings({"80/tcp": "8080"}) == {"80/tcp": "8080"}

    def test_valid_range(self) -> None:
        assert validate_port_mappings({"80-90/tcp": "8080-8090"}) == {
            "80-90/tcp": "8080-8090"
        }

    def test_invalid_host_port_type_raises(self) -> None:
        with pytest.raises(DockerValidationError, match="Invalid host port"):
            validate_port_mappings(as_unvalidated(dict[str, str], {"80/tcp": 8080}))

    def test_invalid_host_port_value_raises(self) -> None:
        with pytest.raises(DockerValidationError, match="Invalid host port"):
            validate_port_mappings({"80/tcp": "80a"})

    def test_invalid_container_spec_raises(self) -> None:
        with pytest.raises(DockerValidationError, match="Invalid container port spec"):
            validate_port_mappings({"80/icmp": "8080"})


class TestValidateEnvVars:
    def test_valid_entry(self) -> None:
        assert validate_env_vars(["KEY=value"]) == ["KEY=value"]

    def test_invalid_key_raises(self) -> None:
        with pytest.raises(DockerValidationError, match="Invalid environment variable"):
            validate_env_vars(["1KEY=value"])

    def test_missing_equals_raises(self) -> None:
        with pytest.raises(DockerValidationError, match="Invalid environment variable"):
            validate_env_vars(["KEYvalue"])


class TestValidateLabels:
    def test_valid_labels(self) -> None:
        assert validate_labels({"com.example.foo": "bar"}) == {"com.example.foo": "bar"}

    def test_invalid_key_raises(self) -> None:
        with pytest.raises(DockerValidationError, match="Invalid label key"):
            validate_labels({"-bad": "value"})

    def test_invalid_value_type_raises(self) -> None:
        with pytest.raises(DockerValidationError, match="Invalid label value"):
            validate_labels(as_unvalidated(dict[str, str], {"key": 123}))


class TestValidateVolumeMounts:
    def test_valid_mount(self) -> None:
        result = validate_volume_mounts({"/host": {"bind": "/container", "mode": "rw"}})
        assert result == {"/host": {"bind": "/container", "mode": "rw"}}

    def test_default_mode(self) -> None:
        assert validate_volume_mounts({"/host": {"bind": "/container"}}) == {
            "/host": {"bind": "/container", "mode": "rw"}
        }

    def test_invalid_host_path_raises(self) -> None:
        with pytest.raises(DockerValidationError, match="Invalid volume host path"):
            validate_volume_mounts({"/host;rm -rf": {"bind": "/container"}})

    def test_invalid_host_path_type_raises(self) -> None:
        with pytest.raises(DockerValidationError, match="Invalid volume host path"):
            validate_volume_mounts(
                as_unvalidated(dict[str, dict[str, str]], {123: {"bind": "/container"}})
            )

    def test_invalid_spec_type_raises(self) -> None:
        with pytest.raises(DockerValidationError, match="Invalid volume spec"):
            validate_volume_mounts(
                as_unvalidated(dict[str, dict[str, str]], {"/host": "/container"})
            )

    def test_invalid_bind_path_raises(self) -> None:
        with pytest.raises(DockerValidationError, match="Invalid volume bind path"):
            validate_volume_mounts({"/host": {"bind": "/container;bad"}})

    def test_invalid_mode_raises(self) -> None:
        with pytest.raises(DockerValidationError, match="Invalid volume mode"):
            validate_volume_mounts({"/host": {"bind": "/container", "mode": "wo"}})


class TestValidateBuildArgKey:
    def test_valid_key(self) -> None:
        assert validate_build_arg_key("VERSION") == "VERSION"

    def test_empty_raises(self) -> None:
        with pytest.raises(DockerValidationError, match="Invalid build arg key"):
            validate_build_arg_key("")

    def test_invalid_char_raises(self) -> None:
        with pytest.raises(DockerValidationError, match="Invalid build arg key"):
            validate_build_arg_key("VERSION=1")


class TestValidateDockerHost:
    def test_valid_unix_socket(self) -> None:
        assert (
            validate_docker_host("unix:///var/run/docker.sock")
            == "unix:///var/run/docker.sock"
        )

    def test_valid_tcp(self) -> None:
        assert (
            validate_docker_host("tcp://192.168.1.100:2375")
            == "tcp://192.168.1.100:2375"
        )

    def test_valid_tcp_localhost(self) -> None:
        assert validate_docker_host("tcp://localhost:2376") == "tcp://localhost:2376"

    def test_empty_raises(self) -> None:
        with pytest.raises(DockerValidationError, match="Invalid docker_host"):
            validate_docker_host("")

    def test_invalid_scheme_raises(self) -> None:
        with pytest.raises(DockerValidationError, match="Invalid docker_host"):
            validate_docker_host("http://localhost:2375")

    def test_tcp_without_port_raises(self) -> None:
        with pytest.raises(DockerValidationError, match="Invalid docker_host"):
            validate_docker_host("tcp://localhost")

    def test_shell_injection_raises(self) -> None:
        with pytest.raises(DockerValidationError, match="Invalid docker_host"):
            validate_docker_host("tcp://host:2375; rm -rf /")


class TestValidateVolumeName:
    def test_valid_simple(self) -> None:
        assert validate_volume_name("my-vol") == "my-vol"

    def test_valid_with_underscore(self) -> None:
        assert validate_volume_name("my_vol_1") == "my_vol_1"

    def test_valid_with_hyphen(self) -> None:
        assert validate_volume_name("my-vol-1") == "my-vol-1"

    def test_valid_with_dot(self) -> None:
        assert validate_volume_name("vol.1.0") == "vol.1.0"

    def test_empty_raises(self) -> None:
        with pytest.raises(DockerValidationError, match="Invalid volume name"):
            validate_volume_name("")

    def test_starts_with_hyphen_raises(self) -> None:
        with pytest.raises(DockerValidationError, match="Invalid volume name"):
            validate_volume_name("-bad")

    def test_shell_injection_semicolon(self) -> None:
        with pytest.raises(DockerValidationError, match="Invalid volume name"):
            validate_volume_name("vol;rm -rf /")

    def test_shell_injection_dollar(self) -> None:
        with pytest.raises(DockerValidationError, match="Invalid volume name"):
            validate_volume_name("$(whoami)")

    def test_shell_injection_space(self) -> None:
        with pytest.raises(DockerValidationError, match="Invalid volume name"):
            validate_volume_name("my vol")


class TestValidateContainerNewName:
    def test_valid_simple(self) -> None:
        assert validate_container_new_name("my-container") == "my-container"

    def test_valid_with_underscore(self) -> None:
        assert validate_container_new_name("my_container_1") == "my_container_1"

    def test_valid_with_dot(self) -> None:
        assert validate_container_new_name("ctr.1.0") == "ctr.1.0"

    def test_empty_raises(self) -> None:
        with pytest.raises(DockerValidationError, match="Invalid container name"):
            validate_container_new_name("")

    def test_starts_with_hyphen_raises(self) -> None:
        with pytest.raises(DockerValidationError, match="Invalid container name"):
            validate_container_new_name("-bad")

    def test_shell_injection_semicolon(self) -> None:
        with pytest.raises(DockerValidationError, match="Invalid container name"):
            validate_container_new_name("ctr;rm -rf /")

    def test_shell_injection_dollar(self) -> None:
        with pytest.raises(DockerValidationError, match="Invalid container name"):
            validate_container_new_name("$(whoami)")

    def test_shell_injection_space(self) -> None:
        with pytest.raises(DockerValidationError, match="Invalid container name"):
            validate_container_new_name("bad name")


class TestValidateNetworkDriver:
    def test_valid_bridge(self) -> None:
        assert validate_network_driver("bridge") == "bridge"

    def test_valid_host(self) -> None:
        assert validate_network_driver("host") == "host"

    def test_valid_overlay(self) -> None:
        assert validate_network_driver("overlay") == "overlay"

    def test_valid_none(self) -> None:
        assert validate_network_driver("none") == "none"

    def test_valid_with_underscore(self) -> None:
        assert validate_network_driver("my_driver") == "my_driver"

    def test_empty_raises(self) -> None:
        with pytest.raises(DockerValidationError, match="Invalid network driver"):
            validate_network_driver("")

    def test_shell_injection_semicolon(self) -> None:
        with pytest.raises(DockerValidationError, match="Invalid network driver"):
            validate_network_driver("bridge;rm -rf /")

    def test_shell_injection_dollar(self) -> None:
        with pytest.raises(DockerValidationError, match="Invalid network driver"):
            validate_network_driver("$(whoami)")


class TestValidateIpAddress:
    def test_valid_ip(self) -> None:
        assert validate_ip_address("172.20.0.2") == "172.20.0.2"

    def test_valid_cidr(self) -> None:
        assert validate_ip_address("172.20.0.2/16") == "172.20.0.2/16"

    def test_valid_loopback(self) -> None:
        assert validate_ip_address("127.0.0.1") == "127.0.0.1"

    def test_valid_zeros(self) -> None:
        assert validate_ip_address("0.0.0.0") == "0.0.0.0"

    def test_empty_raises(self) -> None:
        with pytest.raises(DockerValidationError, match="Invalid IP address"):
            validate_ip_address("")

    def test_invalid_format_no_dots(self) -> None:
        with pytest.raises(DockerValidationError, match="Invalid IP address"):
            validate_ip_address("not-an-ip")

    def test_invalid_format_letters(self) -> None:
        with pytest.raises(DockerValidationError, match="Invalid IP address"):
            validate_ip_address("abc.def.ghi.jkl")

    def test_shell_injection_semicolon(self) -> None:
        with pytest.raises(DockerValidationError, match="Invalid IP address"):
            validate_ip_address("1.2.3.4;rm -rf /")

    def test_shell_injection_dollar(self) -> None:
        with pytest.raises(DockerValidationError, match="Invalid IP address"):
            validate_ip_address("$(whoami)")
