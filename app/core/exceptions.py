"""Domain exceptions for the application."""


class DomainError(Exception):
    """Base exception for domain errors."""


class NodeNotFoundError(DomainError):
    """Raised when a node is not found."""


class ConnectionFailedError(DomainError):
    """Raised when a connection to a node fails."""
