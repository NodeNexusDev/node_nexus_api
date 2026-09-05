# ruff: noqa: I001
"""DI providers for the application."""

from __future__ import annotations

from typing import cast

from dishka import Provider, Scope, provide

from app.adapters.runtime.docker import SshDockerRuntime
from app.adapters.runtime.known_hosts import FileKnownHostsManager
from app.adapters.runtime.node_validation import SshCredentialValidator
from app.adapters.runtime.ssh import SSHConnectorFactory
from app.adapters.security import AesGcmCredentialCipher, HmacSha256APIKeyHasher
from app.adapters.security.jwt_handler import JWTHandlerAdapter
from app.adapters.security.password_hasher import PasswordHasherAdapter
from app.application.ports.api_key_hasher import APIKeyHasher
from app.application.ports.credential_cipher import CredentialCipher
from app.application.ports.docker_runtime import DockerRuntime
from app.application.ports.jwt_handler import JWTHandler
from app.application.ports.known_hosts import KnownHostsManager
from app.application.ports.node_validation import NodeCredentialValidator
from app.application.ports.password_hasher import PasswordHasher
from app.application.ports.remote_command import RemoteConnectorFactory
from app.application.ports.remote_stream import RemoteStreamingConnectorFactory
from app.core.config import Settings


class ConnectorProvider(Provider):
    """Connector providers."""

    @provide(scope=Scope.APP)
    def get_ssh_connector_factory(self, settings: Settings) -> SSHConnectorFactory:
        """Get SSH connector factory."""
        return SSHConnectorFactory(
            known_hosts_path=settings.SSH_KNOWN_HOSTS_PATH,
            strict_host_key_checking=settings.SSH_STRICT_HOST_KEY_CHECKING,
        )

    @provide(scope=Scope.APP, provides=KnownHostsManager)
    def get_known_hosts_manager(self, settings: Settings) -> KnownHostsManager:
        """Get file-based known_hosts manager."""
        return cast(KnownHostsManager, FileKnownHostsManager(settings))

    @provide(scope=Scope.APP, provides=RemoteConnectorFactory)
    def get_remote_connector_factory(
        self, factory: SSHConnectorFactory
    ) -> RemoteConnectorFactory:
        """Bind remote command sessions to the SSH adapter."""
        return factory

    @provide(scope=Scope.APP, provides=RemoteStreamingConnectorFactory)
    def get_remote_streaming_connector_factory(
        self, factory: SSHConnectorFactory
    ) -> RemoteStreamingConnectorFactory:
        """Bind SSH streaming to its application port."""
        return factory

    @provide(scope=Scope.APP, provides=CredentialCipher)
    def get_credential_cipher(self) -> CredentialCipher:
        """Bind credential protection to the configured AES-GCM adapter."""
        return AesGcmCredentialCipher()

    @provide(scope=Scope.APP, provides=APIKeyHasher)
    def get_api_key_hasher(self) -> APIKeyHasher:
        """Bind API-key lookup hashing to the HMAC-SHA-256 adapter."""
        return HmacSha256APIKeyHasher()

    @provide(scope=Scope.APP, provides=JWTHandler)
    def get_jwt_handler(self) -> JWTHandler:
        """Bind JWT operations to the PyJWT adapter."""
        return JWTHandlerAdapter()

    @provide(scope=Scope.APP, provides=PasswordHasher)
    def get_password_hasher(self) -> PasswordHasher:
        """Bind password hashing to the bcrypt adapter."""
        return PasswordHasherAdapter()

    @provide(scope=Scope.APP, provides=DockerRuntime)
    def get_docker_runtime(
        self,
        connector_factory: RemoteConnectorFactory,
        credential_cipher: CredentialCipher,
    ) -> DockerRuntime:
        """Bind Docker CLI execution to the SSH runtime adapter."""
        return SshDockerRuntime(connector_factory, credential_cipher)

    @provide(scope=Scope.APP, provides=NodeCredentialValidator)
    def get_node_credential_validator(
        self,
        connector_factory: RemoteConnectorFactory,
        known_hosts: KnownHostsManager,
    ) -> NodeCredentialValidator:
        """Bind credential validation to the SSH adapter."""
        return SshCredentialValidator(connector_factory, known_hosts)
