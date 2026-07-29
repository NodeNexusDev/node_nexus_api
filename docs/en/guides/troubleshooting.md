---
title: Troubleshooting
status: stable
translation_key: guides.troubleshooting
source_revision: "2026-07-29"
---

# Troubleshooting

Start with the HTTP status, response `detail`, and request ID from structured
logs. Never add API keys, passwords, or private keys to diagnostic output.

| Symptom | Likely cause | Diagnostic action |
|---|---|---|
| `401 Unauthorized` | Missing, inactive, expired, or unknown API key | Check `X-API-Key` and the managed key state |
| `403 Forbidden` | A read-only key attempted a mutation | Grant write scope only if required |
| `409 Conflict` | The node name is already in use | Search the inventory by name |
| `422 Unprocessable Entity` | Invalid schema, cursor, parameter, or identifier | Read `detail` and compare the request with the API reference |
| `429 Too Many Requests` | The process exceeded its rate-limit window | Back off; inspect the rate-limit settings |
| `503` during a node operation | SSH or the remote Docker daemon failed | Check routing, port, credentials, host-key policy, and daemon access |
| `504 Gateway Timeout` | The operation exceeded `REQUEST_TIMEOUT` | Find the slow remote operation before increasing the timeout |

## Application is not ready

`GET /ready` returns `503` when the database check fails:

```bash
docker compose ps
docker compose logs --tail=100 api
docker compose logs --tail=100 db
docker compose exec db pg_isready -U "${POSTGRES_USER:-postgres}"
```

Inside the API container, `DATABASE_URL` must use the Compose hostname `db`. If
`AUTO_MIGRATE=false`, apply migrations separately and inspect the current
revision with `uv run alembic current`.

## Schedules and remote Docker

Schedules live in process memory, disappear after restart, and are not
coordinated across replicas. Use one scheduler owner or an external durable
scheduler. For Docker failures, verify node connectivity and run `docker
version`, `docker info`, and `docker ps` on the remote host. Bulk operations can
partially succeed, so inspect every result.
