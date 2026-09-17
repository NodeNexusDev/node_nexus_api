"""GitHub template source — fetch pack trees via the Contents API."""

from __future__ import annotations

import base64
from typing import Any, override

import httpx2
import structlog

from app.application.ports.template_source import (
    FetchedAsset,
    FetchedPack,
    TemplateSource,
)
from app.core.exceptions import DomainError

logger = structlog.get_logger()

GITHUB_API_BASE = "https://api.github.com"
TEMPLATES_ROOT = "templates"

# Sync bounds (mirror pack asset limits to avoid abuse).
MAX_PACKS_PER_SYNC = 200
MAX_ASSET_FILES = 100
MAX_ASSET_BYTES = 1_048_576  # 1 MiB per file
MAX_PACK_ASSETS_BYTES = 10_485_760  # 10 MiB per pack


class GitHubTemplateSource(TemplateSource):
    """Read ``templates/{pack_id}/`` trees from a GitHub repository."""

    def __init__(self, timeout: float = 20.0) -> None:
        self._timeout = httpx2.Timeout(connect=5.0, read=timeout, write=5.0, pool=5.0)

    def _headers(self, token: str | None) -> dict[str, str]:
        headers = {
            "Accept": "application/vnd.github+json",
            "User-Agent": "node-nexus-api",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if token:
            headers["Authorization"] = f"Bearer {token}"
        return headers

    @override
    async def fetch_packs(
        self,
        owner: str,
        repo: str,
        branch: str,
        token: str | None,
    ) -> list[FetchedPack]:
        """Fetch all pack trees under ``templates/``."""
        async with httpx2.AsyncClient(
            base_url=GITHUB_API_BASE,
            headers=self._headers(token),
            timeout=self._timeout,
        ) as client:
            entries = await self._contents(client, owner, repo, TEMPLATES_ROOT, branch)
            if entries is None:
                if not await self._repo_exists(client, owner, repo):
                    raise DomainError(f"GitHub repository {owner}/{repo} not found")
                # No templates/ directory — nothing to sync.
                return []
            packs: list[FetchedPack] = []
            for entry in entries:
                if not isinstance(entry, dict) or entry.get("type") != "dir":
                    continue
                if len(packs) >= MAX_PACKS_PER_SYNC:
                    logger.warning(
                        "github.sync.pack_limit",
                        owner=owner,
                        repo=repo,
                        limit=MAX_PACKS_PER_SYNC,
                    )
                    break
                dirname = str(entry.get("name", ""))
                pack = await self._fetch_pack(client, owner, repo, dirname, branch)
                if pack is not None:
                    packs.append(pack)
            return packs

    async def _repo_exists(
        self, client: httpx2.AsyncClient, owner: str, repo: str
    ) -> bool:
        """Check repository existence (distinguish typo from empty templates/)."""
        try:
            response = await client.get(f"/repos/{owner}/{repo}")
        except httpx2.HTTPError as exc:
            raise DomainError(
                f"GitHub request failed for {owner}/{repo}: {exc}"
            ) from exc
        if response.status_code == 404:
            return False
        if response.status_code >= 400:
            raise DomainError(
                f"GitHub request failed for {owner}/{repo}: HTTP {response.status_code}"
            )
        return True

    async def _contents(
        self,
        client: httpx2.AsyncClient,
        owner: str,
        repo: str,
        path: str,
        branch: str,
    ) -> list[dict[str, Any]] | dict[str, Any] | None:
        """GET repository contents; None on 404, raise DomainError otherwise."""
        try:
            response = await client.get(
                f"/repos/{owner}/{repo}/contents/{path}",
                params={"ref": branch},
            )
        except httpx2.HTTPError as exc:
            raise DomainError(f"GitHub request failed for {path}: {exc}") from exc
        if response.status_code == 404:
            return None
        if response.status_code == 401:
            raise DomainError("GitHub authentication failed (check token)")
        if response.status_code == 403:
            raise DomainError("GitHub access forbidden or rate limit exceeded")
        if response.status_code >= 400:
            raise DomainError(
                f"GitHub request failed for {path}: HTTP {response.status_code}"
            )
        try:
            return response.json()
        except ValueError as exc:
            raise DomainError(f"Invalid GitHub response for {path}") from exc

    async def _fetch_file(
        self,
        client: httpx2.AsyncClient,
        owner: str,
        repo: str,
        path: str,
        branch: str,
    ) -> tuple[bytes, str | None] | None:
        """Fetch a single file; None on 404. Returns (raw bytes, blob sha)."""
        payload = await self._contents(client, owner, repo, path, branch)
        if payload is None:
            return None
        if not isinstance(payload, dict) or payload.get("type") != "file":
            return None
        content = payload.get("content", "")
        if not isinstance(content, str):
            return None
        try:
            raw = base64.b64decode(content)
        except ValueError as exc:
            raise DomainError(f"Invalid GitHub file encoding for {path}") from exc
        sha = payload.get("sha")
        return raw, sha if isinstance(sha, str) else None

    async def _fetch_pack(
        self,
        client: httpx2.AsyncClient,
        owner: str,
        repo: str,
        dirname: str,
        branch: str,
    ) -> FetchedPack | None:
        """Fetch one pack directory; None when manifest.json is missing."""
        root = f"{TEMPLATES_ROOT}/{dirname}"
        fetched = await self._fetch_file(
            client, owner, repo, f"{root}/manifest.json", branch
        )
        if fetched is None:
            logger.warning("github.sync.pack_no_manifest", pack=dirname)
            return None
        manifest_raw, manifest_sha = fetched
        try:
            import json

            manifest = json.loads(manifest_raw.decode("utf-8"))
        except (ValueError, UnicodeDecodeError) as exc:
            raise DomainError(
                f"Invalid manifest.json in pack {dirname}: {exc}"
            ) from exc
        if not isinstance(manifest, dict):
            raise DomainError(f"Invalid manifest.json in pack {dirname}: not an object")

        commands: list[dict[str, Any]] = []
        fetched = await self._fetch_file(
            client, owner, repo, f"{root}/commands.json", branch
        )
        if fetched is not None:
            commands = self._parse_json_list(fetched[0], f"{dirname}/commands.json")

        scripts: list[dict[str, Any]] = []
        fetched = await self._fetch_file(
            client, owner, repo, f"{root}/scripts.json", branch
        )
        if fetched is not None:
            scripts = self._parse_json_list(fetched[0], f"{dirname}/scripts.json")

        readme: str | None = None
        fetched = await self._fetch_file(
            client, owner, repo, f"{root}/README.md", branch
        )
        if fetched is not None:
            try:
                readme = fetched[0].decode("utf-8")
            except UnicodeDecodeError:
                readme = None

        assets = await self._fetch_assets(client, owner, repo, f"{root}/assets", branch)
        return FetchedPack(
            dirname=dirname,
            manifest=manifest,
            commands=commands,
            scripts=scripts,
            readme=readme,
            assets=tuple(assets),
            manifest_sha=manifest_sha,
        )

    async def _fetch_assets(
        self,
        client: httpx2.AsyncClient,
        owner: str,
        repo: str,
        path: str,
        branch: str,
    ) -> list[FetchedAsset]:
        """Fetch asset files recursively (bounded)."""
        entries = await self._contents(client, owner, repo, path, branch)
        if not entries or not isinstance(entries, list):
            return []
        assets: list[FetchedAsset] = []
        total = 0

        async def _walk(items: list[dict[str, Any]], prefix: str) -> None:
            nonlocal total
            for entry in items:
                if not isinstance(entry, dict):
                    continue
                entry_type = entry.get("type")
                name = str(entry.get("name", ""))
                if entry_type == "dir":
                    sub = await self._contents(
                        client, owner, repo, f"{path}/{prefix}{name}", branch
                    )
                    if isinstance(sub, list):
                        await _walk(sub, f"{prefix}{name}/")
                elif entry_type == "file":
                    if len(assets) >= MAX_ASSET_FILES:
                        raise DomainError(
                            f"Too many asset files in {path} (max {MAX_ASSET_FILES})"
                        )
                    fetched = await self._fetch_file(
                        client, owner, repo, f"{path}/{prefix}{name}", branch
                    )
                    if fetched is None:
                        continue
                    raw, _sha = fetched
                    if len(raw) > MAX_ASSET_BYTES:
                        raise DomainError(
                            f"Asset {prefix}{name} too large ({len(raw)} bytes)"
                        )
                    total += len(raw)
                    if total > MAX_PACK_ASSETS_BYTES:
                        raise DomainError(f"Pack assets too large in {path}")
                    assets.append(
                        FetchedAsset(path=f"assets/{prefix}{name}", content=raw)
                    )

        await _walk(entries, "")
        return assets

    @staticmethod
    def _parse_json_list(raw: bytes, label: str) -> list[dict[str, Any]]:
        """Parse a JSON list file; raise DomainError on invalid content."""
        try:
            import json

            parsed = json.loads(raw.decode("utf-8"))
        except (ValueError, UnicodeDecodeError) as exc:
            raise DomainError(f"Invalid {label}: {exc}") from exc
        if not isinstance(parsed, list):
            raise DomainError(f"Invalid {label}: expected a list")
        return parsed
