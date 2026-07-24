"""Script service for business logic."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any
from uuid import UUID

if TYPE_CHECKING:
    from app.core.connectors.base import ConnectorFactory
    from app.repositories.command_repo import CommandRepository
    from app.repositories.node_repo import NodeRepository
    from app.services.audit_service import AuditService

import structlog

from app.core.exceptions import (
    CommandNotFoundError,
    NodeNotFoundError,
    ScriptNotFoundError,
    TemplateRenderError,
)
from app.core.ssh_utils import decrypt_value, get_connector_factory
from app.core.template import render_command
from app.repositories.script_execution_repo import ScriptExecutionRepository
from app.repositories.script_repo import ScriptRepository
from app.schemas.script import (
    ScriptCreate,
    ScriptExecuteRequest,
    ScriptExecutionBatchResult,
    ScriptNodeResult,
    ScriptResponse,
    ScriptStep,
    ScriptStepResult,
    ScriptUpdate,
)
from app.schemas.script_execution import ScriptExecutionResponse

audit = structlog.get_logger("audit")


class ScriptService:
    """Service for script operations."""

    def __init__(
        self,
        repository: ScriptRepository,
        command_repository: CommandRepository,
        node_repository: NodeRepository,
        execution_repository: ScriptExecutionRepository,
        audit_service: AuditService | None = None,
        connector_factory: ConnectorFactory | None = None,
    ):
        self._repository = repository
        self._command_repository = command_repository
        self._node_repository = node_repository
        self._execution_repository = execution_repository
        self._audit = audit_service
        self._connector_factory = connector_factory

    async def _log(
        self,
        action: str,
        node_id: UUID | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        if self._audit:
            await self._audit.log(action=action, node_id=node_id, details=details)

    async def get_script(self, script_id: UUID) -> ScriptResponse:
        """Get a script by ID."""
        script = await self._repository.get_by_id(script_id)
        if script is None:
            raise ScriptNotFoundError(f"Script {script_id} not found")
        return self._to_response(script)

    async def get_all_scripts(
        self, page: int = 1, size: int = 20
    ) -> tuple[list[ScriptResponse], int]:
        """Get all scripts with total count."""
        skip = (page - 1) * size
        scripts = await self._repository.get_all(skip=skip, limit=size)
        total = await self._repository.count()
        return [self._to_response(s) for s in scripts], total

    async def create_script(self, data: ScriptCreate) -> ScriptResponse:
        """Create a new script."""
        raw = data.model_dump(mode="json")
        script = await self._repository.create(raw)
        audit.info("script.create.ok", script_id=str(script.id), name=data.name)
        await self._log("create", details={"entity": "script", "name": data.name})
        return self._to_response(script)

    async def update_script(
        self, script_id: UUID, data: ScriptUpdate
    ) -> ScriptResponse:
        """Update an existing script."""
        update_data = data.model_dump(mode="json", exclude_unset=True)
        script = await self._repository.update(script_id, update_data)
        if script is None:
            raise ScriptNotFoundError(f"Script {script_id} not found")
        audit.info("script.update.ok", script_id=str(script_id))
        await self._log("update", details={"entity": "script", "id": str(script_id)})
        return self._to_response(script)

    async def delete_script(self, script_id: UUID) -> bool:
        """Delete a script."""
        script = await self._repository.get_by_id(script_id)
        if script is None:
            raise ScriptNotFoundError(f"Script {script_id} not found")
        await self._log("delete", details={"entity": "script", "id": str(script_id)})
        await self._repository.delete(script_id)
        audit.info("script.delete.ok", script_id=str(script_id))
        return True

    async def get_executions(
        self, script_id: UUID, page: int = 1, size: int = 20
    ) -> tuple[list[ScriptExecutionResponse], int]:
        """Get execution history for a script."""
        script = await self._repository.get_by_id(script_id)
        if script is None:
            raise ScriptNotFoundError(f"Script {script_id} not found")

        skip = (page - 1) * size
        executions = await self._execution_repository.get_by_script_id(
            script_id, skip=skip, limit=size
        )
        total = await self._execution_repository.count_by_script_id(script_id)
        return [ScriptExecutionResponse.model_validate(e) for e in executions], total

    async def execute_script(
        self, script_id: UUID, data: ScriptExecuteRequest
    ) -> ScriptExecutionBatchResult:
        """Execute a script on multiple nodes in parallel."""
        script = await self._repository.get_by_id(script_id)
        if script is None:
            raise ScriptNotFoundError(f"Script {script_id} not found")

        steps = [ScriptStep(**s) for s in script.steps]

        node_results: list[ScriptNodeResult] = []
        for node_id in data.node_ids:
            try:
                result = await self._execute_on_node(
                    script_id, steps, node_id, data.params
                )
                node_results.append(result)
            except Exception as exc:
                audit.error(
                    "script.execute.node_failed",
                    script_id=str(script_id),
                    node_id=str(node_id),
                    error_type=type(exc).__name__,
                    error=str(exc),
                )
                node_results.append(
                    ScriptNodeResult(
                        execution_id=UUID(int=0),
                        node_id=node_id,
                        node_name="unknown",
                        status="failed",
                        steps=[],
                    )
                )

        return ScriptExecutionBatchResult(
            script_id=script_id,
            results=node_results,
        )

    async def _execute_on_node(
        self,
        script_id: UUID,
        steps: list[ScriptStep],
        node_id: UUID,
        params: dict[str, Any],
    ) -> ScriptNodeResult:
        """Execute all script steps on a single node."""
        node = await self._node_repository.get_by_id(node_id)
        if node is None:
            raise NodeNotFoundError(f"Node {node_id} not found")

        execution = await self._execution_repository.create(
            {
                "script_id": script_id,
                "node_id": node_id,
                "params": params,
                "status": "running",
                "steps": [],
                "started_at": datetime.now(UTC),
            }
        )

        step_results: list[dict[str, Any]] = []
        final_status = "completed"

        try:
            password = decrypt_value(node.password)
            ssh_key = decrypt_value(node.ssh_key)
            connector = get_connector_factory(self._connector_factory).create_ssh(
                host=node.host,
                port=node.port,
                username=node.username,
                password=password,
                ssh_key=ssh_key,
            )

            async with connector:
                for idx, step in enumerate(steps):
                    command_str = step.command or ""
                    try:
                        command_str = await self._resolve_command(step, params)
                        stdout, stderr, exit_code = await connector.execute_command(
                            command_str
                        )
                    except (CommandNotFoundError, TemplateRenderError) as exc:
                        stdout = ""
                        stderr = str(exc)
                        exit_code = 1

                    step_result = {
                        "step_index": idx,
                        "label": step.label,
                        "command": command_str,
                        "stdout": stdout,
                        "stderr": stderr,
                        "exit_code": exit_code,
                    }
                    step_results.append(step_result)

                    if exit_code != 0 and step.on_failure == "stop":
                        final_status = "failed"
                        break

            audit.info(
                "script.executed",
                script_id=str(script_id),
                node_id=str(node_id),
                status=final_status,
            )
        except Exception as exc:
            final_status = "failed"
            audit.error(
                "script.execute.failed",
                script_id=str(script_id),
                node_id=str(node_id),
                error=str(exc),
            )
        finally:
            await self._execution_repository.update(
                execution.id,
                {
                    "status": final_status,
                    "steps": step_results,
                    "finished_at": datetime.now(UTC),
                },
            )

        return ScriptNodeResult(
            execution_id=execution.id,
            node_id=node_id,
            node_name=node.name,
            status=final_status,
            steps=[ScriptStepResult(**sr) for sr in step_results],
        )

    async def _resolve_command(
        self, step: ScriptStep, global_params: dict[str, Any]
    ) -> str:
        """Resolve a step to a rendered command string."""
        if step.type == "inline":
            if not step.command:
                raise TemplateRenderError("Inline step has no command")
            return render_command(step.command, [], global_params)

        if step.type == "command":
            if not step.command_id:
                raise TemplateRenderError("Command step has no command_id")
            command = await self._command_repository.get_by_id(step.command_id)
            if command is None:
                raise CommandNotFoundError(f"Command {step.command_id} not found")
            parameters = command.parameters if command.parameters else []
            merged_params = {**global_params, **step.params}
            return render_command(command.command, parameters, merged_params)

        raise TemplateRenderError(f"Unknown step type: {step.type}")

    @staticmethod
    def _to_response(script: Any) -> ScriptResponse:
        steps = [ScriptStep(**s) for s in script.steps]
        return ScriptResponse(
            id=script.id,
            name=script.name,
            description=script.description,
            steps=steps,
            created_at=script.created_at,
            updated_at=script.updated_at,
        )
