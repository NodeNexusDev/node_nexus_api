---
title: Health and readiness
status: stable
translation_key: operations.health-and-readiness
source_revision: "2026-07-29"
---

# Health and readiness

`GET /health` is the liveness probe and confirms the process can serve HTTP.
`GET /ready` checks readiness, including database access. Do not put SSH or
remote Docker checks in platform probes. Remove an instance from traffic when
readiness fails; restart it only when liveness fails persistently.
