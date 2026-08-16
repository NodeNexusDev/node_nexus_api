"""Application service for validating node credentials."""

from app.application.dto.node_validation import (
    NodeValidationRequestDTO,
    NodeValidationResultDTO,
)
from app.application.ports.node_validation import NodeCredentialValidator


class NodeValidationService:
    """Validate SSH connectivity without persisting a node."""

    def __init__(self, validator: NodeCredentialValidator) -> None:
        self._validator = validator

    async def validate_credentials(
        self, request: NodeValidationRequestDTO
    ) -> NodeValidationResultDTO:
        """Delegate credential validation to the port."""
        return await self._validator.validate(request)
