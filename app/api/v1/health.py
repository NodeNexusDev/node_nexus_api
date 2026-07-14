"""Health check endpoint."""

from typing import Annotated

from dishka.integrations.fastapi import inject
from fastapi import APIRouter, Security

from app.api.deps import get_current_api_key

router = APIRouter()


@router.get("/health")
@inject
async def health_check(
    _key: Annotated[str, Security(get_current_api_key)],
) -> dict[str, str]:
    """Health check endpoint."""
    return {"status": "healthy"}
