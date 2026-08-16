"""Port for validating node credentials without persistence."""

from typing import Protocol

from app.application.dto.node_validation import (
    NodeValidationRequestDTO,
    NodeValidationResultDTO,
)


class NodeCredentialValidator(Protocol):
    """Validate SSH connectivity with provided credentials."""

    async def validate(
        self, request: NodeValidationRequestDTO
    ) -> NodeValidationResultDTO: ...
