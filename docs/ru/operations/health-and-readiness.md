---
title: Health и readiness
status: stable
translation_key: operations.health-and-readiness
source_revision: "2026-07-29"
---

# Health и readiness

`GET /health` — liveness probe, подтверждающая работу HTTP process.
`GET /ready` проверяет готовность, включая доступ к БД. Не добавляйте SSH или
удалённый Docker в platform probes. При ошибке readiness исключайте instance из
трафика; перезапускайте только при устойчивой ошибке liveness.
