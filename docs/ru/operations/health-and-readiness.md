---
title: Health и readiness
status: stable
translation_key: operations.health-and-readiness
source_revision: "2026-08-11"
---

# Health и readiness

`GET /health` — liveness probe, подтверждающая работу HTTP process.
`GET /ready` проверяет доступ к БД и восстановление персистентных расписаний.
Тело ответа содержит вложенный объект `checks` с `status` и `detail` для каждой
отдельной проверки:

```json
{
  "status": "ready",
  "checks": {
    "database": {"status": "ok", "detail": "database reachable"},
    "scheduler": {"status": "ok", "detail": "ready=True, owns=False, jobs=0"}
  }
}
```

Если какая-либо проверка не проходит, endpoint возвращает `503 Service
Unavailable` и `status: "not_ready"`. Проверка scheduler получает состояние `ok`
только после успешной первоначальной сверки PostgreSQL с APScheduler. Non-owner
реплика может оставаться готовой: ownership управляет выполнением jobs, а не
обслуживанием HTTP.

Не добавляйте SSH или удалённый Docker в platform probes. При ошибке readiness
исключайте instance из трафика; перезапускайте только при устойчивой ошибке
liveness.
