from __future__ import annotations

from typing import Protocol


class TagManager(Protocol):
    async def rename_tag(self, old_name: str, new_name: str) -> int: ...

    async def delete_tag(self, tag_name: str) -> int: ...
