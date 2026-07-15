"""Domain exceptions for the application."""


class DomainError(Exception):
    """Base exception for domain errors."""


class NodeNotFoundError(DomainError):
    """Raised when a node is not found."""


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


class TagNotFoundError(DomainError):
    """Raised when a tag is not found on a node."""
