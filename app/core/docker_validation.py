"""Docker parameter validation utilities."""

import re

from app.core.exceptions import DockerValidationError

_CONTAINER_REFERENCE_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_.-]*$")
_IMAGE_NAME_RE = re.compile(r"^[a-zA-Z0-9\-_./:]+$")


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
