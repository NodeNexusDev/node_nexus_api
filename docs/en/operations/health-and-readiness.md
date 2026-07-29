---
title: Health and readiness
status: stable
translation_key: operations.health-and-readiness
source_revision: "2026-07-29"
---

# Health and readiness

`GET /health` is the liveness probe and confirms the process can serve HTTP.
`GET /ready` checks database access and persistent scheduler restoration. The
scheduler check becomes `ok` only after the initial PostgreSQL-to-APScheduler
reconciliation completes without registration errors. A non-owner replica can
still be ready: ownership controls job execution, not HTTP traffic.

Do not put SSH or remote Docker checks in platform probes. Remove an instance
from traffic when readiness fails; restart it only when liveness fails
persistently.
