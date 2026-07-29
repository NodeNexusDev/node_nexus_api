"""Internal data-transfer objects for application boundaries."""

from app.application.dto.audit import AuditEventDTO
from app.application.dto.command_execution import (
    CommandExecutionDTO,
    CommandRequestDTO,
    CommandResultDTO,
)
from app.application.dto.node_connection import NodeConnectionDTO

__all__ = [
    "AuditEventDTO",
    "CommandExecutionDTO",
    "CommandRequestDTO",
    "CommandResultDTO",
    "NodeConnectionDTO",
]
