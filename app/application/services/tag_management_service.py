from __future__ import annotations

from app.application.ports.tag_manager import TagManager


class TagManagementService:
    def __init__(self, tag_manager: TagManager) -> None:
        self._tag_manager = tag_manager

    async def rename_tag(self, old_name: str, new_name: str) -> int:
        return await self._tag_manager.rename_tag(old_name, new_name)

    async def delete_tag(self, tag_name: str) -> int:
        return await self._tag_manager.delete_tag(tag_name)
