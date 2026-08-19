"""Transaction-safe script execution application use case."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import TYPE_CHECKING, cast
from uuid import UUID

import structlog

from app.application.command_policy import command_fingerprint
from app.application.dto.node_connection import NodeConnectionDTO
from app.application.dto.script_execution import (
    ResolvedScriptStepDTO,
    ScriptExecutionBatchResultDTO,
    ScriptExecutionRequestDTO,
    ScriptExecutionTargetDTO,
    ScriptNodeResultDTO,
    ScriptStepResultDTO,
)
from app.application.policies.output import bound_output
from app.application.services._target_resolver import resolve_targets
from app.application.types import JsonObject, JsonValue, PersistenceObject
from app.core.exceptions import (
    CommandNotFoundError,
    NodeNotFoundError,
    ScriptNotFoundError,
    TemplateRenderError,
)
from app.core.template import render_command

if TYPE_CHECKING:
    from app.application.ports.audit_sink import AuditEventSink
    from app.application.ports.command_reader import CommandTemplateReader
    from app.application.ports.credential_cipher import CredentialCipher
    from app.application.ports.node_reader import NodeConnectionReader
    from app.application.ports.remote_command import RemoteConnectorFactory
    from app.application.ports.script_persistence import (
        ScriptDefinitionReader,
        ScriptExecutionWriter,
    )

audit = structlog.get_logger("audit")
_SCRIPT_NODE_CONCURRENCY = 5


class ScriptExecutionService:
    """Execute preloaded script targets without sharing database sessions."""

    def __init__(
        self,
        script_reader: ScriptDefinitionReader,
        command_reader: CommandTemplateReader,
        node_reader: NodeConnectionReader,
        execution_writer: ScriptExecutionWriter,
        credential_cipher: CredentialCipher,
        connector_factory: RemoteConnectorFactory,
        audit_service: AuditEventSink | None = None,
    ) -> None:
        self._script_reader = script_reader
        self._command_reader = command_reader
        self._node_reader = node_reader
        self._execution_writer = execution_writer
        self._credential_cipher = credential_cipher
        self._connector_factory = connector_factory
        self._audit = audit_service

    async def execute_script(
        self, script_id: UUID, request: ScriptExecutionRequestDTO
    ) -> ScriptExecutionBatchResultDTO:
        """Load dependencies, run remote-only workers, and persist results."""
        definition = await self._script_reader.get_definition(script_id)
        if definition is None:
            raise ScriptNotFoundError(f"Script {script_id} not found")

        params = dict(request.params)
        resolved_steps = tuple(
            [await self._resolve_step(step, params) for step in definition.steps]
        )
        nodes = await self._resolve_targets(request)
        if not nodes and request.node_ids:
            raise NodeNotFoundError("Node not found")

        targets: list[ScriptExecutionTargetDTO] = []
        for node in nodes:
            execution_id = await self._execution_writer.create_execution(
                {
                    "script_id": script_id,
                    "node_id": node.id,
                    "params": None,
                    "status": "running",
                    "trigger": request.trigger,
                    "schedule_id": request.schedule_id,
                    "steps": [],
                    "started_at": datetime.now(UTC),
                }
            )
            targets.append(
                ScriptExecutionTargetDTO(
                    execution_id=execution_id,
                    script_id=script_id,
                    node=node,
                    steps=resolved_steps,
                )
            )

        semaphore = asyncio.Semaphore(_SCRIPT_NODE_CONCURRENCY)

        async def run(target: ScriptExecutionTargetDTO) -> ScriptNodeResultDTO:
            async with semaphore:
                return await self._run_remote(target)

        results = await asyncio.gather(*(run(target) for target in targets))
        for result in results:
            await self._execution_writer.update_execution(
                result.execution_id,
                {
                    "status": result.status,
                    "steps": [self._step_result_dict(step) for step in result.steps],
                    "finished_at": datetime.now(UTC),
                },
            )
            await self._log_result(script_id, result)

        return ScriptExecutionBatchResultDTO(
            script_id=script_id,
            results=tuple(results),
        )

    async def _resolve_targets(
        self, request: ScriptExecutionRequestDTO
    ) -> list[NodeConnectionDTO]:
        """Resolve target nodes from IDs and tags."""
        return await resolve_targets(
            self._node_reader,
            node_ids=request.node_ids,
            tags=request.tags,
        )

    async def _resolve_step(
        self,
        raw_step: JsonObject,
        global_params: dict[str, JsonValue],
    ) -> ResolvedScriptStepDTO:
        label = cast(str, raw_step["label"])
        on_failure = cast(str, raw_step.get("on_failure", "stop"))
        try:
            step_type = raw_step["type"]
            if step_type == "inline":
                command = raw_step.get("command")
                if not command:
                    raise TemplateRenderError("Inline step has no command")
                rendered = render_command(cast(str, command), [], global_params)
            elif step_type == "command":
                raw_command_id = raw_step.get("command_id")
                if not raw_command_id:
                    raise TemplateRenderError("Command step has no command_id")
                command_id = UUID(str(raw_command_id))
                template = await self._command_reader.get_template(command_id)
                if template is None:
                    raise CommandNotFoundError(f"Command {command_id} not found")
                step_params = cast(JsonObject, raw_step.get("params", {}))
                merged = {**global_params, **step_params}
                rendered = render_command(
                    template.command,
                    list(template.parameters),
                    merged,
                )
            else:
                raise TemplateRenderError(f"Unknown step type: {step_type}")
            return ResolvedScriptStepDTO(
                label=label,
                command=rendered,
                on_failure=on_failure,
            )
        except (CommandNotFoundError, TemplateRenderError) as exc:
            return ResolvedScriptStepDTO(
                label=label,
                command="",
                on_failure=on_failure,
                resolution_error=str(exc),
            )

    async def _run_remote(
        self, target: ScriptExecutionTargetDTO
    ) -> ScriptNodeResultDTO:
        """Run one immutable target without persistence dependencies."""
        node = target.node
        results: list[ScriptStepResultDTO] = []
        status = "completed"
        try:
            connector = self._connector_factory.create_ssh(
                host=node.host,
                port=node.port,
                username=node.username,
                password=self._credential_cipher.decrypt(node.password),
                ssh_key=self._credential_cipher.decrypt(node.ssh_key),
                passphrase=self._credential_cipher.decrypt(node.passphrase),
            )
            async with connector:
                for index, step in enumerate(target.steps):
                    if step.resolution_error is None:
                        stdout, stderr, exit_code = await connector.execute_command(
                            step.command
                        )
                    else:
                        stdout, stderr, exit_code = "", step.resolution_error, 1
                    safe_stdout = bound_output(stdout)
                    safe_stderr = bound_output(stderr)
                    results.append(
                        ScriptStepResultDTO(
                            step_index=index,
                            label=step.label,
                            command_fingerprint=command_fingerprint(step.command),
                            stdout=safe_stdout.value,
                            stderr=safe_stderr.value,
                            stdout_bytes=safe_stdout.original_bytes,
                            stderr_bytes=safe_stderr.original_bytes,
                            truncated=safe_stdout.truncated or safe_stderr.truncated,
                            exit_code=exit_code,
                        )
                    )
                    if exit_code != 0 and step.on_failure == "stop":
                        status = "failed"
                        break
        except Exception as exc:
            status = "failed"
            audit.exception(
                "script.execute.failed",
                script_id=str(target.script_id),
                node_id=str(node.id),
                error_type=type(exc).__name__,
            )
        return ScriptNodeResultDTO(
            execution_id=target.execution_id,
            node_id=node.id,
            node_name=node.name,
            status=status,
            steps=tuple(results),
        )

    async def _log_result(self, script_id: UUID, result: ScriptNodeResultDTO) -> None:
        audit.info(
            "script.executed",
            script_id=str(script_id),
            node_id=str(result.node_id),
            status=result.status,
        )
        if self._audit:
            await self._audit.log(
                action="execute",
                node_id=result.node_id,
                details={"script_id": str(script_id), "status": result.status},
            )

    @staticmethod
    def _step_result_dict(step: ScriptStepResultDTO) -> PersistenceObject:
        return {
            "step_index": step.step_index,
            "label": step.label,
            "command_fingerprint": step.command_fingerprint,
            "stdout": step.stdout,
            "stderr": step.stderr,
            "stdout_bytes": step.stdout_bytes,
            "stderr_bytes": step.stderr_bytes,
            "truncated": step.truncated,
            "exit_code": step.exit_code,
        }
