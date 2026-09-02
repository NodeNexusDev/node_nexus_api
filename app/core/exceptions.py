"""Domain exceptions for the application."""


class DomainError(Exception):
    """Base exception for domain errors."""


class NodeNotFoundError(DomainError):
    """Raised when a node is not found."""


class NodeNameConflictError(DomainError):
    """Raised when a node name violates its uniqueness contract."""


class ConnectionFailedError(DomainError):
    """Raised when a connection to a node fails."""


class CredentialDecryptionError(DomainError):
    """Raised when an encrypted credential cannot be decrypted safely."""


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


class NetworkNotFoundError(DockerError):
    """Raised when a Docker network is not found."""


class VolumeNotFoundError(DockerError):
    """Raised when a Docker volume is not found."""


class ImageNotFoundError(DockerError):
    """Raised when a Docker image is not found."""


class DockerDaemonError(DockerError):
    """Raised when Docker daemon is unreachable."""


class DockerValidationError(DockerError):
    """Raised when Docker command parameters are invalid."""


class RequestTimeoutError(DomainError):
    """Raised when a request exceeds the configured timeout."""


class UnsupportedConfigFormatError(DomainError):
    """Raised when an imported configuration format is not supported."""


class ScheduleValidationError(DomainError):
    """Raised when schedule input is invalid."""


class ScheduleNotFoundError(DomainError):
    """Raised when a persistent schedule is not found."""


class SchedulerOwnershipError(DomainError):
    """Raised when this replica does not own scheduler execution."""


class SchedulePersistenceError(DomainError):
    """Raised when schedule persistence or registration fails."""


class ScheduledScriptExecutionError(DomainError):
    """Raised when a scheduled script execution reports a failed result."""


class ExecutionNotFoundError(DomainError):
    """Raised when an execution record is not found."""


class AuditWriteError(DomainError):
    """Raised when an obligatory audit event cannot be persisted."""


class FavoriteNotFoundError(DomainError):
    """Raised when a favorite is not found."""


class InvalidCredentialsError(DomainError):
    """Raised when login credentials are invalid."""


class UserNotFoundError(DomainError):
    """Raised when a user is not found."""


class UserAlreadyExistsError(DomainError):
    """Raised when a user with the given email already exists."""


class TokenExpiredError(DomainError):
    """Raised when a JWT token has expired."""


class InvalidTokenError(DomainError):
    """Raised when a JWT token is invalid."""


class InsufficientPermissionsError(DomainError):
    """Raised when the user lacks required permissions."""


class HostKeyFetchError(DomainError):
    """Raised when SSH host key cannot be fetched or verified."""


class ComposeProjectNotFoundError(DomainError):
    """Raised when a compose project is not found."""


class ComposeProjectAlreadyExistsError(DomainError):
    """Raised when a compose project violates unique node/project constraint."""


class PackNotFoundError(DomainError):
    """Raised when a template pack is not found."""


class PackConflictError(DomainError):
    """Raised when a template pack name conflicts (409)."""
