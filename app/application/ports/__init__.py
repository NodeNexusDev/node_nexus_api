"""Ports implemented by persistence and infrastructure adapters."""

from app.application.ports.api_key import APIKeyReader, APIKeyWriter
from app.application.ports.api_key_hasher import APIKeyHasher
from app.application.ports.audit_log import (
    AuditLogReader,
    AuditLogWriter,
    AuditOutboxPort,
)
from app.application.ports.audit_sink import AuditEventSink
from app.application.ports.audit_writer import AuditWriter
from app.application.ports.command_management import CommandReader, CommandWriter
from app.application.ports.credential_cipher import CredentialCipher
from app.application.ports.docker_runtime import DockerRuntime
from app.application.ports.health import DatabaseHealthProbe
from app.application.ports.node_management import (
    NodeManagementReader,
    NodeManagementWriter,
)
from app.application.ports.node_reader import NodeConnectionReader, NodeStatusWriter
from app.application.ports.remote_command import (
    RemoteCommandSession,
    RemoteConnectorFactory,
)
from app.application.ports.remote_stream import (
    RemoteStreamingConnector,
    RemoteStreamingConnectorFactory,
)
from app.application.ports.schedule import (
    JobSchedulerPort,
    ScheduleReader,
    ScheduleWriter,
)
from app.application.ports.script_persistence import (
    ScriptDefinitionReader,
    ScriptExecutionReader,
    ScriptExecutionWriter,
    ScriptReader,
    ScriptWriter,
)

__all__ = [
    "APIKeyReader",
    "APIKeyWriter",
    "APIKeyHasher",
    "AuditEventSink",
    "AuditLogReader",
    "AuditLogWriter",
    "AuditOutboxPort",
    "AuditWriter",
    "CommandReader",
    "CommandWriter",
    "CredentialCipher",
    "DatabaseHealthProbe",
    "DockerRuntime",
    "JobSchedulerPort",
    "NodeConnectionReader",
    "NodeManagementReader",
    "NodeManagementWriter",
    "NodeStatusWriter",
    "RemoteCommandSession",
    "RemoteConnectorFactory",
    "RemoteStreamingConnector",
    "RemoteStreamingConnectorFactory",
    "ScheduleReader",
    "ScheduleWriter",
    "ScriptDefinitionReader",
    "ScriptExecutionReader",
    "ScriptExecutionWriter",
    "ScriptReader",
    "ScriptWriter",
]
