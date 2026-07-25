"""Docker parameter validation utilities."""

import re

from app.core.exceptions import DockerValidationError

_CONTAINER_ID_RE = re.compile(r"^[a-fA-F0-9\-]+$")
_IMAGE_NAME_RE = re.compile(r"^[a-zA-Z0-9\-_./:]+$")


def validate_container_id(container_id: str) -> str:
    """Validate Docker container ID format.

    Only allows hexadecimal characters and hyphens to prevent command injection.
    """
    if not container_id or not _CONTAINER_ID_RE.match(container_id):
        raise DockerValidationError(
            f"Invalid container ID format: {container_id!r}. "
            "Container ID must contain only hexadecimal characters and hyphens."
        )
    return container_id


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
