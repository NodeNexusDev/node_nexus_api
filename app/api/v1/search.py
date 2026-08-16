"""Global search endpoint."""

import structlog
from dishka.integrations.fastapi import DishkaRoute, FromDishka, inject
from fastapi import APIRouter, Query, Security

from app.api.deps import get_current_api_key
from app.application.services.global_search_service import GlobalSearchService
from app.schemas.global_search import GlobalSearchResponse, SearchResultItem

audit = structlog.get_logger("audit")

router = APIRouter(tags=["search"], route_class=DishkaRoute)


@router.get("/search", response_model=GlobalSearchResponse)
@inject
async def global_search(
    q: str = Query(..., min_length=1, description="Search query"),
    limit: int = Query(20, ge=1, le=100),
    service: FromDishka[GlobalSearchService] = None,  # ty: ignore[invalid-parameter-default]
    _key: str = Security(get_current_api_key),
) -> GlobalSearchResponse:
    audit.info("api.search", query=q, limit=limit)
    result = await service.search(q=q, limit=limit)
    return GlobalSearchResponse(
        nodes=[SearchResultItem.model_validate(n) for n in result.nodes],
        commands=[SearchResultItem.model_validate(c) for c in result.commands],
        scripts=[SearchResultItem.model_validate(s) for s in result.scripts],
        tags=list(result.tags),
    )
