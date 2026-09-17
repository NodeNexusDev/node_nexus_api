"""Template source port — fetch pack trees from a registry."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


@dataclass(frozen=True, slots=True)
class FetchedAsset:
    """Single asset file fetched from a registry."""

    path: str
    content: bytes


@dataclass(frozen=True, slots=True)
class FetchedPack:
    """Pack tree fetched from a registry repository."""

    dirname: str
    manifest: dict[str, object]
    commands: list[dict[str, object]] = field(default_factory=list)
    scripts: list[dict[str, object]] = field(default_factory=list)
    readme: str | None = None
    assets: tuple[FetchedAsset, ...] = ()
    manifest_sha: str | None = None


class TemplateSource(Protocol):
    """Fetch pack trees from a template registry."""

    async def fetch_packs(
        self, owner: str, repo: str, branch: str, token: str | None
    ) -> list[FetchedPack]:
        """Fetch all pack trees."""
        ...
