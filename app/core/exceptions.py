"""Domain exceptions for the application."""


class DomainError(Exception):
    """Base exception for domain errors."""


class NodeNotFoundError(DomainError):
    """Raised when a node is not found."""


class NodeNameConflictError(DomainError):
    """Raised when a node name violates its uniqueness contract."""


class ConnectionFailedError(DomainError):
    """Raised when a connection to a node fails."""


class CommandNotFoundError(DomainError):
    """Raised when a command template is not found."""


class ScriptNotFoundError(DomainError):
    """Raised when a script is not found."""


class TemplateRenderError(DomainError):
    """Raised when a command template cannot be rendered."""


class AuthenticationError(DomainError):
    """Raised when authentication fails."""


class APIKeyNotFoundError(DomainError):
    """Raised when an API key is not found."""


class APIKeyRevokedError(DomainError):
    """Raised when an API key has been revoked."""


class APIKeyExpiredError(DomainError):
    """Raised when an API key has expired."""


class TagNotFoundError(DomainError):
    """Raised when a tag is not found on a node."""


class DockerError(DomainError):
    """Raised when a Docker operation fails."""


class ContainerNotFoundError(DockerError):
    """Raised when a Docker container is not found."""


class ImageNotFoundError(DockerError):
    """Raised when a Docker image is not found."""


class DockerDaemonError(DockerError):
    """Raised when Docker daemon is unreachable."""


class DockerValidationError(DockerError):
    """Raised when Docker command parameters are invalid."""


class RequestTimeoutError(DomainError):
    """Raised when a request exceeds the configured timeout."""
