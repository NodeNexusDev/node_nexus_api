"""Docker parameter validation utilities."""

import re

from app.core.exceptions import DockerValidationError

_CONTAINER_REFERENCE_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_.-]*$")
_IMAGE_NAME_RE = re.compile(r"^[a-zA-Z0-9\-_./:]+$")
_NETWORK_NAME_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_.-]*$")
_ENV_VAR_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=.+$")
_LABEL_KEY_RE = re.compile(r"^[a-zA-Z0-9](?:[a-zA-Z0-9_.\-/]*[a-zA-Z0-9])?$")
_PORT_SPEC_RE = re.compile(r"^\d+(?:-\d+)?(?:/tcp|/udp)?$")
_HOST_PORT_RE = re.compile(r"^\d+(?:-\d+)?$")
_VOLUME_PATH_RE = re.compile(r"^[A-Za-z0-9_./~\-:]+$")
_BUILD_ARG_KEY_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_RESTART_POLICIES = frozenset({"no", "always", "on-failure", "unless-stopped"})


def validate_container_id(container_id: str) -> str:
    """Validate Docker container ID or name format.

    Allows Docker IDs and names while blocking shell metacharacters.
    """
    if not container_id or not _CONTAINER_REFERENCE_RE.fullmatch(container_id):
        raise DockerValidationError(
            f"Invalid container reference format: {container_id!r}. "
            "Container reference must start with an alphanumeric character and "
            "contain only alphanumeric characters, hyphens, underscores, and dots."
        )
    return container_id


def validate_container_name(name: str) -> str:
    """Validate a Docker container name supplied to ``docker create --name``."""
    if not name or not _CONTAINER_REFERENCE_RE.fullmatch(name):
        raise DockerValidationError(
            f"Invalid container name format: {name!r}. "
            "Container name must start with an alphanumeric character and "
            "contain only alphanumeric characters, hyphens, underscores, and dots."
        )
    return name


def validate_image_name(image: str) -> str:
    """Validate Docker image name format.

    Allows: registry/repo:tag, repo:tag, repo
    Blocks: shell metacharacters, spaces, etc.
    """
    if not image or not _IMAGE_NAME_RE.match(image):
        raise DockerValidationError(
            f"Invalid image name format: {image!r}. "
            "Image name must contain only alphanumeric characters, "
            "hyphens, underscores, dots, slashes, and colons."
        )
    return image


def validate_image_tag(tag: str) -> str:
    """Validate a fully-qualified ``repo:tag`` target used by ``docker tag``."""
    if not tag or not _IMAGE_NAME_RE.fullmatch(tag):
        raise DockerValidationError(
            f"Invalid image tag format: {tag!r}. "
            "Image tag must contain only alphanumeric characters, "
            "hyphens, underscores, dots, slashes, and colons."
        )
    return tag


def validate_network_name(network: str) -> str:
    """Validate a Docker network name used by ``--network``."""
    if not network or not _NETWORK_NAME_RE.fullmatch(network):
        raise DockerValidationError(f"Invalid network name format: {network!r}.")
    return network


def validate_restart_policy(policy: str) -> str:
    """Validate a Docker restart policy value."""
    if policy not in _RESTART_POLICIES:
        raise DockerValidationError(
            f"Invalid restart policy: {policy!r}. "
            f"Allowed values: {', '.join(sorted(_RESTART_POLICIES))}."
        )
    return policy


def validate_port_mappings(ports: dict[str, str]) -> dict[str, str]:
    """Validate a ``{container_port[/proto]: host_port}`` mapping."""
    validated: dict[str, str] = {}
    for container_spec, host_port in ports.items():
        if not isinstance(host_port, str) or not _HOST_PORT_RE.fullmatch(host_port):
            raise DockerValidationError(
                f"Invalid host port mapping for {container_spec!r}: {host_port!r}"
            )
        if not _PORT_SPEC_RE.fullmatch(container_spec):
            raise DockerValidationError(
                f"Invalid container port spec: {container_spec!r}"
            )
        validated[container_spec] = host_port
    return validated


def validate_env_vars(env: list[str]) -> list[str]:
    """Validate environment variable entries of the form ``KEY=value``."""
    validated: list[str] = []
    for entry in env:
        if not isinstance(entry, str) or not _ENV_VAR_RE.fullmatch(entry):
            raise DockerValidationError(
                f"Invalid environment variable entry: {entry!r}. "
                "Expected 'KEY=value' with KEY starting with a letter/underscore."
            )
        validated.append(entry)
    return validated


def validate_labels(labels: dict[str, str]) -> dict[str, str]:
    """Validate Docker label key/value pairs."""
    validated: dict[str, str] = {}
    for key, value in labels.items():
        if not isinstance(key, str) or not _LABEL_KEY_RE.fullmatch(key):
            raise DockerValidationError(f"Invalid label key: {key!r}")
        if not isinstance(value, str):
            raise DockerValidationError(
                f"Invalid label value for {key!r}: must be a string"
            )
        validated[key] = value
    return validated


def validate_volume_mounts(
    volumes: dict[str, dict[str, str]],
) -> dict[str, dict[str, str]]:
    """Validate bind-mount volume specifications."""
    validated: dict[str, dict[str, str]] = {}
    for host_path, spec in volumes.items():
        if not isinstance(host_path, str) or not _VOLUME_PATH_RE.fullmatch(host_path):
            raise DockerValidationError(f"Invalid volume host path: {host_path!r}")
        if not isinstance(spec, dict):
            raise DockerValidationError(
                f"Invalid volume spec for {host_path!r}: must be an object"
            )
        bind = spec.get("bind")
        mode = spec.get("mode", "rw")
        if not isinstance(bind, str) or not _VOLUME_PATH_RE.fullmatch(bind):
            raise DockerValidationError(
                f"Invalid volume bind path for {host_path!r}: {bind!r}"
            )
        if mode not in {"rw", "ro"}:
            raise DockerValidationError(
                f"Invalid volume mode for {host_path!r}: {mode!r}. Allowed: rw, ro."
            )
        validated[host_path] = {"bind": bind, "mode": mode}
    return validated


def validate_build_arg_key(key: str) -> str:
    """Validate a Docker ``--build-arg`` key."""
    if not key or not _BUILD_ARG_KEY_RE.fullmatch(key):
        raise DockerValidationError(
            f"Invalid build arg key: {key!r}. "
            "Must start with letter/underscore and contain only "
            "alphanumeric characters and underscores."
        )
    return key


_DOCKER_HOST_RE = re.compile(r"^(unix:///[\w./\-]+|tcp://[\w.\-]+:\d+)$")


def validate_docker_host(docker_host: str) -> str:
    """Validate a ``DOCKER_HOST`` value (unix socket or tcp endpoint)."""
    if not docker_host or not _DOCKER_HOST_RE.fullmatch(docker_host):
        raise DockerValidationError(
            f"Invalid docker_host value: {docker_host!r}. "
            "Expected 'unix:///path/to/socket' or 'tcp://host:port'."
        )
    return docker_host


_VOLUME_NAME_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_.\-]*$")
_NETWORK_DRIVER_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_.\-]*$")
_IP_ADDRESS_RE = re.compile(r"^(\d{1,3}\.){3}\d{1,3}(/\d{1,2})?$")


def validate_volume_name(name: str) -> str:
    """Validate a Docker volume name."""
    if not name or not _VOLUME_NAME_RE.fullmatch(name):
        raise DockerValidationError(
            f"Invalid volume name: {name!r}. "
            "Volume name must start with alphanumeric and contain only "
            "alphanumeric characters, hyphens, underscores, and dots."
        )
    return name


def validate_container_new_name(name: str) -> str:
    """Validate a new container name for ``docker rename``."""
    if not name or not _CONTAINER_REFERENCE_RE.fullmatch(name):
        raise DockerValidationError(
            f"Invalid container name: {name!r}. "
            "Container name must start with an alphanumeric character and "
            "contain only alphanumeric characters, hyphens, underscores, and dots."
        )
    return name


def validate_network_driver(driver: str) -> str:
    """Validate a Docker network driver name."""
    if not driver or not _NETWORK_DRIVER_RE.fullmatch(driver):
        raise DockerValidationError(f"Invalid network driver: {driver!r}.")
    return driver


def validate_ip_address(ip: str) -> str:
    """Validate an IP address or CIDR notation."""
    if not ip or not _IP_ADDRESS_RE.fullmatch(ip):
        raise DockerValidationError(
            f"Invalid IP address: {ip!r}. Expected 'x.x.x.x' or 'x.x.x.x/n'."
        )
    return ip
