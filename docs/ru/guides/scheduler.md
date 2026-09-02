---
title: Scheduler
status: stable
translation_key: guides.scheduler
source_revision: "2026-09-02"
---

# Scheduler

Persistent script scheduling via `APScheduler` (`ApschedulerRuntime` + `ApschedulerJobScheduler`) and `app/application/services/schedule_management.py`, `schedule_reconciliation.py`, `schedule_restorer.py`, `scheduled_script_executor.py`.

## Concept

* `Script` → `Schedule` (`script_id`, `cron`, `timezone`, `node_ids`, `params`, `enabled`)
* `ScheduleManagementService` stores desired state via `ScheduleReader/Writer` (`SqlAlchemyScheduleGateway`)
* `ScheduleReconciliationService` syncs persistence ↔ `ApschedulerRuntime` (APS `CronTrigger`)
* `ScheduledScriptExecutor` is the APS callback — loads `ScriptDefinitionReader` + `NodeConnectionReader` + `ScriptExecutionWriter` and runs `ScriptExecutionService` without a request `AsyncSession`
* Ownership via advisory lock (`ApschedulerRuntime.acquire_ownership`, `start_ownership_monitor`, `SCHEDULER_OWNERSHIP_POLL_SECONDS=5`)
* Callbacks never receive `container`, `DAO`, or ORM

## Endpoints

All under `/scripts/{script_id}/schedules` (plural) via `app/api/v2/scripts.py`.

### Create or update

```http
POST /api/v2/scripts/{script_id}/schedules
X-API-Key: ...
Content-Type: application/json

{
  "cron": "0 9 * * *",
  "node_ids": ["<uuid>", "..."],
  "params": {"env": "prod"},
  "timezone": "UTC",
  "misfire_grace_seconds": 60
}
```

`201` with `ScheduleResponse` (`script_id`, `cron`, `timezone`, `message`). Cron is validated via `ScheduleValidationError` → `422`. `misfire_grace_seconds` defaults to `60`.

### Get

```http
GET /api/v2/scripts/{script_id}/schedules
GET /api/v2/scripts/{script_id}/schedule   # singular alias, not in OpenAPI
```

`200` with `ScheduledJob` (`id`, `script_id`, `cron`, `timezone`, `node_ids`, `params`, `enabled`, `operational_state`, `last_error_type`, `last_run_at`, `next_run_at`). `404` if `ScheduleNotFoundError`.

### Delete

```http
DELETE /api/v2/scripts/{script_id}/schedules
```

`204`.

### Execution history

```http
GET /api/v2/scripts/{script_id}/schedule/history?cursor=&limit=20
GET /api/v2/scripts/{script_id}/executions?trigger=scheduled&cursor=&limit=20
```

Cursor pagination (`_encode_offset` → `paginate_offset`) over `ScriptExecutionReader`.

### Trigger now (E2E)

```http
POST /api/v2/internal/e2e/scheduler/{script_id}/trigger-now
X-API-Key: ...
```

Bypasses cron, calls `ScheduledScriptExecutor.execute` directly, records `started/succeeded/failed` via `ScriptExecutionWriter`. Requires `E2E_ENABLED=true` and `scheduler.owns_execution`.

## Lifecycle

```
AppProvider → ApschedulerRuntime (APP, finalizer stop())
          → ApschedulerJobScheduler (port)
          → ScheduleReconciliationService
          → ScheduleRestorer (on startup, reconciles persistence → runtime)
          → AuditCleanupJob (retention)
```

`ApplicationStartup` runs `migration_runner`, `scheduler.start()`, `schedule_restorer.restore()`, `audit_cleanup`.

## Example

```bash
## Schedule
curl --fail-with-body -X POST \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  -H "Content-Type: application/json" \
  -d '{"cron":"*/5 * * * *","node_ids":["<node-uuid>"],"timezone":"UTC"}' \
  "${NODE_NEXUS_URL}/api/v2/scripts/<script-id>/schedules" | jq .

## Get
curl --fail-with-body -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v2/scripts/<script-id>/schedules" | jq .

## History
curl --fail-with-body -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v2/scripts/<script-id>/schedule/history?limit=20" | jq .

## Unschedule
curl --fail-with-body -X DELETE \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v2/scripts/<script-id>/schedules" -i
```

## See also

* `app/api/v2/scripts.py` — `schedule_script`, `get_schedule`, `unschedule_script`, `get_scheduled_execution_history`
* `app/adapters/runtime/apscheduler_runtime.py` (374) — `ApschedulerRuntime`, `acquire_ownership`
* `app/adapters/runtime/scheduler.py` — `ApschedulerJobScheduler`
* `architecture/decisions/ADR-003-scheduler-lifecycle.md`
