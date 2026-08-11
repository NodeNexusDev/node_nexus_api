---
title: Health and readiness
status: stable
translation_key: operations.health-and-readiness
source_revision: "2026-08-11"
---

# Health and readiness

`GET /health` is the liveness probe and confirms the process can serve HTTP.
`GET /ready` checks database access and persistent scheduler restoration. The
response body has a nested `checks` object with `status` and `detail` for each
individual check:

```json
{
  "status": "ready",
  "checks": {
    "database": {"status": "ok", "detail": "database reachable"},
    "scheduler": {"status": "ok", "detail": "ready=True, owns=False, jobs=0"}
  }
}
```

If any check fails, the endpoint returns `503 Service Unavailable` and
`status: "not_ready"`. The scheduler check becomes `ok` only after the initial
PostgreSQL-to-APScheduler reconciliation completes without registration errors.
A non-owner replica can still be ready: ownership controls job execution, not
HTTP traffic.

Do not put SSH or remote Docker checks in platform probes. Remove an instance
from traffic when readiness fails; restart it only when liveness fails
persistently.
