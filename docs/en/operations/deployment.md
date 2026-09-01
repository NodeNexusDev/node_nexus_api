---
title: Deployment and rollback
status: stable
translation_key: operations.deployment
source_revision: "2026-07-30"
---

# Deployment and rollback

## Production prerequisites

- Terminate TLS at a trusted reverse proxy and expose only the API port.
- Keep PostgreSQL and telemetry receivers on private networks.
- Store environment values in the deployment platform's secret store.
- Generate independent, high-entropy `SECRET_KEY` and `MASTER_API_KEY` values.
- Persist PostgreSQL data and verify backups before rollout.
- Set `AUTO_MIGRATE=false` when migrations are release-managed.

The Compose file is a useful baseline, but its example database credentials and
published database port are not production defaults.

## Release sequence

1. Record the application version and current Alembic revision.
2. Back up PostgreSQL and export application configuration.
3. Build an immutable image from the reviewed commit and scan dependencies.
4. Apply `uv run alembic upgrade head` as one controlled job.
5. Start one instance and wait for both `/health` and `/ready`.
6. Request `/api/v2/nodes/?page=1&size=1` with a valid key.
7. Shift traffic gradually while monitoring errors, timeouts, and database health.

Keep `SCHEDULER_ENABLED=true` on eligible replicas. PostgreSQL persists
schedules and its advisory lock elects one execution owner. Every replica may
serve schedule API requests; only the lock owner runs jobs. Mount a reviewed
OpenSSH `known_hosts` file at `SSH_KNOWN_HOSTS_PATH`; do not disable strict host
verification in production.

## Rollback

Before routing traffic to the previous image, confirm that it supports the
upgraded schema. Do not run `alembic downgrade` until its data-loss implications
have been reviewed and a fresh backup exists. After rollback, verify `/ready`,
repeat the authenticated smoke request, and record the failed version, migration
revision, and observed symptoms.
