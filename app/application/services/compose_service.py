"""Compose application service with Docker runner."""

from __future__ import annotations

import asyncio
import json
import re
import shlex
from typing import TYPE_CHECKING
from uuid import UUID

import structlog

from app.application.dto.compose import (
    ComposeBulkResultDTO,
    ComposeCreateDTO,
    ComposePsDTO,
    ComposeServiceResultDTO,
    ComposeUpdateDTO,
    ComposeViewDTO,
)
from app.application.services.docker.error_mapper import raise_for_docker_error
from app.core.exceptions import ComposeProjectNotFoundError

if TYPE_CHECKING:
    from app.application.ports.compose import ComposeReader, ComposeWriter
    from app.application.services.docker.command_runner import DockerCommandRunner

audit = structlog.get_logger("audit")

_PROJECT_NAME_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_.-]*$")


def _validate_project_name(name: str) -> str:
    """Validate compose project_name format."""
    if not name or not _PROJECT_NAME_RE.fullmatch(name) or len(name) > 100:
        raise ValueError(f"Invalid project_name: {name!r}")
    return name


def _compose_file_path(project_name: str) -> str:
    """Safe temp compose file path for a project."""
    import tempfile
    from pathlib import Path

    safe = "".join(c if c.isalnum() else "_" for c in project_name)
    tmpdir = Path(tempfile.gettempdir())
    return str(tmpdir / f"nn-compose-{safe}.yml")


def _env_prefix(env: dict[str, str] | None) -> str:
    """Build env var prefix for docker compose commands."""
    if not env:
        return ""
    parts = [f"{shlex.quote(k)}={shlex.quote(v)}" for k, v in env.items()]
    return " ".join(parts) + " "


class ComposeService:
    """Compose CRUD and runtime orchestration."""

    def __init__(
        self,
        reader: ComposeReader,
        writer: ComposeWriter,
        runner: DockerCommandRunner,
    ) -> None:
        self._reader = reader
        self._writer = writer
        self._runner = runner

    # ------------------------------------------------------------------ CRUD
    async def create_project(self, data: ComposeCreateDTO) -> ComposeViewDTO:
        """Create a compose project."""
        _validate_project_name(data.project_name)
        created = await self._writer.create_project(data)
        audit.info(
            "compose.project.created",
            node_id=str(data.node_id),
            project_name=data.project_name,
        )
        return created

    async def list_projects(
        self, node_id: UUID, offset: int = 0, limit: int = 20
    ) -> list[ComposeViewDTO]:
        """List projects with offset/limit."""
        return await self._reader.list_projects(node_id, offset, limit)

    async def list_all_projects(self, node_id: UUID) -> list[ComposeViewDTO]:
        """List all projects for node (for cursor pagination fallback)."""
        # fetch in pages to avoid loading huge sets
        all_items: list[ComposeViewDTO] = []
        offset = 0
        batch = 100
        while True:
            page = await self._reader.list_projects(node_id, offset, batch)
            all_items.extend(page)
            if len(page) < batch:
                break
            offset += batch
        return all_items

    async def count_projects(self, node_id: UUID) -> int:
        """Count projects for stats."""
        return await self._reader.count_projects(node_id)

    async def stats(self, node_id: UUID) -> int:
        """Alias for count."""
        return await self._reader.stats(node_id)

    async def get_project(self, node_id: UUID, project_name: str) -> ComposeViewDTO:
        """Get a project or raise."""
        validated = _validate_project_name(project_name)
        project = await self._reader.get_project(node_id, validated)
        if project is None:
            raise ComposeProjectNotFoundError(
                f"Compose project {project_name!r} not found"
            )
        return project

    async def update_project(
        self, node_id: UUID, project_name: str, data: ComposeUpdateDTO
    ) -> ComposeViewDTO:
        """Update a project or raise."""
        validated = _validate_project_name(project_name)
        updated = await self._writer.update_project(node_id, validated, data)
        if updated is None:
            raise ComposeProjectNotFoundError(
                f"Compose project {project_name!r} not found"
            )
        audit.info(
            "compose.project.updated",
            node_id=str(node_id),
            project_name=project_name,
        )
        return updated

    async def delete_project(self, node_id: UUID, project_name: str) -> None:
        """Delete a project or raise."""
        validated = _validate_project_name(project_name)
        deleted = await self._writer.delete_project(node_id, validated)
        if not deleted:
            raise ComposeProjectNotFoundError(
                f"Compose project {project_name!r} not found"
            )
        audit.info(
            "compose.project.deleted",
            node_id=str(node_id),
            project_name=project_name,
        )

    async def upsert_project(self, data: ComposeCreateDTO) -> ComposeViewDTO:
        """Upsert a project."""
        _validate_project_name(data.project_name)
        return await self._writer.upsert_project(data)

    # ---------------------------------------------------------------- runtime helpers
    async def _run_compose(
        self,
        node_id: UUID,
        project: ComposeViewDTO,
        compose_args: str,
        timeout: int = 60,
    ) -> str:
        """Write compose file and run docker compose."""
        node = await self._runner.get_target(node_id)
        file_path = _compose_file_path(project.project_name)
        env_str = _env_prefix(project.env)
        quoted = shlex.quote(project.compose)
        write_cmd = f"printf %s {quoted} > {shlex.quote(file_path)}"
        docker_args = (
            f"compose -p {shlex.quote(project.project_name)} "
            f"-f {shlex.quote(file_path)} {compose_args}"
        )
        docker_cmd = self._runner.build_command(node, docker_args)
        full = f"{write_cmd} && {env_str}{docker_cmd}"
        stdout, stderr, exit_code = await self._runner.execute(
            node, full, timeout=timeout
        )
        raise_for_docker_error(stderr, exit_code)
        return stdout.strip()

    async def _bulk_verb(
        self,
        node_id: UUID,
        project: ComposeViewDTO,
        verb: str,
        services: list[str] | None,
        extra: str = "",
        timeout: int = 60,
    ) -> list[ComposeServiceResultDTO]:
        """Run compose verb per service with gather."""
        if not services:
            try:
                out = await self._run_compose(
                    node_id, project, f"{verb}{extra}", timeout=timeout
                )
                return [
                    ComposeServiceResultDTO(
                        service=project.project_name, status="success", output=out
                    )
                ]
            except Exception as exc:  # noqa: BLE001
                return [
                    ComposeServiceResultDTO(
                        service=project.project_name, status="error", error=str(exc)
                    )
                ]

        async def _one(svc: str) -> ComposeServiceResultDTO:
            try:
                out = await self._run_compose(
                    node_id,
                    project,
                    f"{verb}{extra} {shlex.quote(svc)}",
                    timeout=timeout,
                )
                return ComposeServiceResultDTO(
                    service=svc, status="success", output=out
                )
            except Exception as exc:  # noqa: BLE001
                return ComposeServiceResultDTO(
                    service=svc, status="error", error=str(exc)
                )

        results = await asyncio.gather(*(_one(s) for s in services))
        return list(results)

    # ------------------------------------------------------------------ runtime ops
    async def up(
        self,
        node_id: UUID,
        project_name: str,
        pull: bool = False,
        build: bool = False,
        services: list[str] | None = None,
    ) -> ComposeBulkResultDTO:
        """Deploy via compose up -d."""
        project = await self.get_project(node_id, project_name)
        extra = " up -d"
        if pull:
            extra += " --pull always"
        if build:
            extra += " --build"

        if not services:
            try:
                out = await self._run_compose(node_id, project, extra)
                result = ComposeServiceResultDTO(
                    service=project_name, status="success", output=out
                )
                return ComposeBulkResultDTO(
                    total=1, succeeded=1, failed=0, results=(result,)
                )
            except Exception as exc:  # noqa: BLE001
                result = ComposeServiceResultDTO(
                    service=project_name, status="error", error=str(exc)
                )
                return ComposeBulkResultDTO(
                    total=1, succeeded=0, failed=1, results=(result,)
                )

        async def _one(svc: str) -> ComposeServiceResultDTO:
            try:
                out = await self._run_compose(
                    node_id, project, f"{extra} {shlex.quote(svc)}"
                )
                return ComposeServiceResultDTO(
                    service=svc, status="success", output=out
                )
            except Exception as exc:  # noqa: BLE001
                return ComposeServiceResultDTO(
                    service=svc, status="error", error=str(exc)
                )

        results = await asyncio.gather(*(_one(s) for s in services))
        typed = list(results)
        succeeded = sum(1 for r in typed if r.status == "success")
        failed = len(typed) - succeeded
        return ComposeBulkResultDTO(
            total=len(typed),
            succeeded=succeeded,
            failed=failed,
            results=tuple(typed),
        )

    async def down(
        self,
        node_id: UUID,
        project_name: str,
        volumes: bool = False,
        remove_orphans: bool = False,
        timeout: int | None = None,
        images: str | None = None,
    ) -> str:
        """Tear down via compose down."""
        project = await self.get_project(node_id, project_name)
        extra = " down"
        if volumes:
            extra += " -v"
        if remove_orphans:
            extra += " --remove-orphans"
        if images:
            extra += f" --rmi {shlex.quote(images)}"
        if timeout is not None:
            extra += f" -t {timeout}"
        return await self._run_compose(node_id, project, extra, timeout=120)

    async def verb_bulk(
        self,
        node_id: UUID,
        project_name: str,
        verb: str,
        services: list[str] | None = None,
        extra: str = "",
        timeout: int = 60,
    ) -> ComposeBulkResultDTO:
        """Generic bulk verb helper."""
        project = await self.get_project(node_id, project_name)
        results = await self._bulk_verb(
            node_id, project, verb, services, extra, timeout
        )
        succeeded = sum(1 for r in results if r.status == "success")
        failed = len(results) - succeeded
        return ComposeBulkResultDTO(
            total=len(results),
            succeeded=succeeded,
            failed=failed,
            results=tuple(results),
        )

    async def ps(
        self, node_id: UUID, project_name: str, all: bool = False
    ) -> ComposePsDTO:
        """List containers via compose ps."""
        project = await self.get_project(node_id, project_name)
        extra = " -a" if all else ""
        args = f"ps --format json{extra}"
        out = await self._run_compose(node_id, project, args)
        containers: list[dict[str, str]] = []
        if out.strip():
            for line in out.splitlines():
                try:
                    obj = json.loads(line)
                    if isinstance(obj, dict):
                        containers.append({str(k): str(v) for k, v in obj.items()})
                except json.JSONDecodeError:
                    continue
        return ComposePsDTO(output=out, containers=tuple(containers))

    async def logs(
        self,
        node_id: UUID,
        project_name: str,
        tail: int = 100,
        since: str | None = None,
        services: str | None = None,
    ) -> str:
        """Get logs via compose logs."""
        project = await self.get_project(node_id, project_name)
        since_arg = f" --since {shlex.quote(since)}" if since else ""
        services_arg = f" {shlex.quote(services)}" if services else ""
        args = f"logs --tail {tail}{since_arg}{services_arg}"
        return await self._run_compose(node_id, project, args)

    async def config(self, node_id: UUID, project_name: str) -> str:
        """Return resolved compose config."""
        project = await self.get_project(node_id, project_name)
        return await self._run_compose(node_id, project, "config")

    async def images(self, node_id: UUID, project_name: str) -> tuple[list[str], str]:
        """List images via compose images."""
        project = await self.get_project(node_id, project_name)
        try:
            out = await self._run_compose(node_id, project, "images --format json")
        except Exception:  # noqa: BLE001
            out = await self._run_compose(node_id, project, "config --images")
        images: list[str] = []
        if out.strip():
            for line in out.splitlines():
                stripped = line.strip()
                if stripped.startswith("{"):
                    try:
                        obj = json.loads(stripped)
                        if isinstance(obj, dict):
                            repo = obj.get("Repository") or obj.get("repository") or ""
                            if isinstance(repo, str) and repo:
                                images.append(repo)
                    except json.JSONDecodeError:
                        images.append(stripped)
                elif stripped:
                    images.append(stripped)
        return images, out

    async def top(
        self, node_id: UUID, project_name: str, service: str | None = None
    ) -> tuple[list[str], list[list[str]], str]:
        """Return processes via compose top."""
        project = await self.get_project(node_id, project_name)
        svc_arg = f" {shlex.quote(service)}" if service else ""
        out = await self._run_compose(node_id, project, f"top{svc_arg}")
        titles: list[str] = []
        processes: list[list[str]] = []
        lines = [line for line in out.strip().splitlines() if line.strip()]
        if lines:
            titles = lines[0].split()
            for line in lines[1:]:
                processes.append(line.split())
        return titles, processes, out

    async def port(
        self, node_id: UUID, project_name: str, service: str, private_port: str
    ) -> str:
        """Return port bindings."""
        project = await self.get_project(node_id, project_name)
        args = f"port {shlex.quote(service)} {shlex.quote(private_port)}"
        return await self._run_compose(node_id, project, args)

    async def version(self, node_id: UUID, project_name: str) -> tuple[str, str]:
        """Return compose version."""
        project = await self.get_project(node_id, project_name)
        node = await self._runner.get_target(node_id)
        docker_args = "compose version --format json"
        try:
            cmd = self._runner.build_command(node, docker_args)
            stdout, stderr, exit_code = await self._runner.execute(node, cmd)
            raise_for_docker_error(stderr, exit_code)
            out = stdout.strip()
            try:
                obj = json.loads(out)
                ver = (
                    str(obj.get("version") or obj.get("Version") or out)
                    if isinstance(obj, dict)
                    else out
                )
            except json.JSONDecodeError:
                ver = out
            return ver, out
        except Exception:  # noqa: BLE001
            out = await self._run_compose(node_id, project, "version --short")
            return out.strip(), out

    async def exec(
        self,
        node_id: UUID,
        project_name: str,
        service: str,
        command: str,
        timeout: int = 30,
    ) -> tuple[str, str, int]:
        """Execute command in service via compose exec."""
        project = await self.get_project(node_id, project_name)
        cmd_part = shlex.quote(command)
        args = f"exec -T {shlex.quote(service)} sh -c {cmd_part}"
        out = await self._run_compose(node_id, project, args, timeout=timeout)
        return out, "", 0

    async def run(
        self,
        node_id: UUID,
        project_name: str,
        service: str,
        command: str | None = None,
        detached: bool = False,
        timeout: int = 60,
    ) -> str:
        """Run one-off command via compose run."""
        project = await self.get_project(node_id, project_name)
        detached_flag = " -d" if detached else " --rm"
        cmd_part = f" {shlex.quote(command)}" if command else ""
        args = f"run{detached_flag} {shlex.quote(service)}{cmd_part}"
        return await self._run_compose(node_id, project, args, timeout=timeout)
