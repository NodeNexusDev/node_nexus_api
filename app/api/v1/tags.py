"""Tag management endpoints."""

import structlog
from dishka.integrations.fastapi import DishkaRoute, FromDishka, inject
from fastapi import APIRouter, Body, Security

from app.api.deps import require_write_scope
from app.application.services.tag_management_service import TagManagementService

audit = structlog.get_logger("audit")

router = APIRouter(tags=["tags"], route_class=DishkaRoute)


@router.patch("/tags/{tag_name}")
@inject
async def rename_tag(
    tag_name: str,
    new_name: str = Body(..., embed=True),
    service: FromDishka[TagManagementService] = None,
    _key: str = Security(require_write_scope),
) -> dict:
    audit.info("api.tags.rename", old=tag_name, new=new_name)
    affected = await service.rename_tag(tag_name, new_name)
    return {
        "old_name": tag_name,
        "new_name": new_name,
        "affected": affected,
    }


@router.delete("/tags/{tag_name}")
@inject
async def delete_tag(
    tag_name: str,
    service: FromDishka[TagManagementService] = None,
    _key: str = Security(require_write_scope),
) -> dict:
    audit.info("api.tags.delete", tag=tag_name)
    affected = await service.delete_tag(tag_name)
    return {
        "tag": tag_name,
        "affected": affected,
    }
