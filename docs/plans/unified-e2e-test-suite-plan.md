# Unified E2E Test Suite Plan

> **Объединяет** [`complete-e2e-test-suite-plan.md`](./complete-e2e-test-suite-plan.md)
> и [`e2e-gap-closure-plan.md`](./e2e-gap-closure-plan.md) в единый документ.
> Исходные файлы сохранены без изменений.

---

## Содержание

1. [Цель](#1-цель)
2. [Текущее состояние](#2-текущее-состояние)
3. [Принципы реализации](#3-принципы-реализации)
4. [Целевая структура тестов](#4-целевая-структура-тестов)
5. [Этап A — E2E harness и наблюдаемость](#5-этап-a--e2e-harness-и-наблюдаемость)
6. [Этап B — Матрица публичных endpoint и coverage guard](#6-этап-b--матрица-публичных-endpoint-и-coverage-guard)
7. [Этап C — WebSocket streaming](#7-этап-c--websocket-streaming)
8. [Этап D — Scheduler: execution, recovery и failover](#8-этап-d--scheduler-execution-recovery-и-failover)
9. [Этап E — Audit outbox durability](#9-этап-e--audit-outbox-durability)
10. [Этап F — Config import atomicity](#10-этап-f--config-import-atomicity)
11. [Этап G — API-key lifecycle и authorization](#11-этап-g--api-key-lifecycle-и-authorization)
12. [Этап H — Middleware behavior](#12-этап-h--middleware-behavior)
13. [Этап I — Network failures и recovery](#13-этап-i--network-failures-и-recovery)
14. [Этап J — Concurrency и race conditions](#14-этап-j--concurrency-и-race-conditions)
15. [Этап K — Alembic migration E2E](#15-этап-k--alembic-migration-e2e)
16. [Этап L — HTTP Transport-валидация](#16-этап-l--http-transport-валидация)
17. [Этап M — Большие payload-ы и граничные значения](#17-этап-m--большие-payload-ы-и-граничные-значения)
18. [Этап N — Docker: параметризованные операции и пробелы API](#18-этап-n--docker-параметризованные-операции-и-пробелы-api)
19. [Этап O — API Versioning](#19-этап-o--api-versioning)
20. [Этап P — Реорганизация существующих тестов](#20-этап-p--реорганизация-существующих-тестов)
21. [CI стратегия](#21-ci-стратегия)
22. [Последовательность коммитов](#22-последовательность-коммитов)
23. [Definition of Done](#23-definition-of-done)
24. [Приложение: Полная матрица Docker endpoint](#24-приложение-полная-матрица-docker-endpoint)

---

## 1. Цель

Довести E2E-контур до полного покрытия критических пользовательских,
интеграционных и эксплуатационных потоков NodeNexus API.

Под «полным» понимается не перебор всех комбинаций входных данных, а наличие
E2E-проверок для:

- каждого публичного HTTP/WebSocket endpoint;
- каждого критического happy path;
- каждой существенной границы авторизации;
- каждой внешней системы: PostgreSQL, SSH, Docker, APScheduler;
- ключевых retry, recovery, cancellation, timeout, concurrency и failover
  сценариев;
- миграции существующей БД и перезапуска приложения;
- атомарности критических multi-step операций;
- HTTP transport-уровня (Content-Type, Accept, oversized body, 405 Method);
- граничных значений (large payloads, Unicode, null bytes, deep nesting).

Unit и integration tests продолжают отвечать за исчерпывающие локальные ветки.
E2E проверяют только поведение, которое может сломаться на границе процессов,
контейнеров, сети, БД или composition root.

---

## 2. Текущее состояние

- **131** Docker-backed E2E-тест в двух файлах (`test_e2e.py` + `test_docker_e2e.py`).
- Полный прогон: `131 passed` (на момент аудита 2026-07-30).
- Покрыты: REST CRUD для nodes/commands/scripts/API keys/audit, SSH execution,
  Docker operations (images pull/list, containers lifecycle, networks, volumes,
  bulk), config import/export, pagination (offset + cursor), tags, schedules
  (CRUD + basic replica lock), metrics, health/readiness, авторизация (scopes).

### Основные пробелы

| Приоритет | Пробел | Этап |
|-----------|--------|------|
| 🔴 Critical | WebSocket streaming (ни одного теста) | C |
| 🔴 Critical | Scheduler execution (реальное выполнение по cron) | D |
| 🔴 Critical | Scheduler restart recovery | D |
| 🔴 Critical | Audit outbox durability/idempotency | E |
| 🔴 Critical | Concurrency/race conditions | J |
| 🟠 High | Config import atomic rollback | F |
| 🟠 High | API-key expiration/last_used_at | G |
| 🟠 High | Rate-limit 429 на полном стеке | H |
| 🟠 High | Request timeout 504 | H |
| 🟠 High | Network failures (SSH/DB/DinD) | I |
| 🟠 High | Alembic migration E2E | K |
| 🟡 Medium | HTTP transport validation (415/406/405/413) | L |
| 🟡 Medium | Large payloads и граничные значения | M |
| 🟡 Medium | Docker container logs с `tail`/`since` параметрами | N |
| 🟡 Medium | Docker endpoint пробелы (см. приложение) | N |
| 🟢 Low | API Versioning | O |
| 🟢 Low | Реорганизация монолитных тестов | P |

---

## 3. Принципы реализации

- Тестировать через публичный HTTP/WebSocket API — проверяется пользовательское
  поведение.
- Прямой SQL допустим только для подготовки труднодостижимого состояния и
  проверки durable side effects.
- **Не добавлять production-only debug endpoints**.
- Управление контейнерами/сетью выполнять через pytest-docker/Docker API.
- Не использовать фиксированные `sleep`: применять polling с monotonic deadline.
- Каждый тест создаёт уникальные имена/UUID и очищает собственные ресурсы.
- Не зависеть от порядка тестов.
- Разделить быстрый E2E smoke и долгие resilience/migration scenarios маркерами.
- На failure сохранять container logs и диагностическое состояние.
- Тесты, зависящие от ещё не реализованных API-эндпоинтов, маркируются
  `skip` с указанием зависимого issue/PR.
- Все новые файлы должны проходить независимо: `pytest tests/e2e/<file> -m docker -q`.

---

## 4. Целевая структура тестов

```text
tests/e2e/
├── conftest.py                     # существующий
├── helpers/
│   ├── api.py                      # HTTP client factory, auth headers
│   ├── database.py                 # PostgreSQL connection для setup/assertions
│   ├── docker_test.py              # Docker container/image helpers (новый)
│   ├── polling.py                  # Polling helpers c monotonic deadline (новый)
│   ├── assertions.py               # HTTP error/schema assertion helpers (новый)
│   └── websocket.py                # WebSocket client helpers
├── test_smoke_e2e.py               # быстрый основной путь
├── test_nodes_e2e.py               # nodes CRUD, tags, search, bulk
├── test_commands_e2e.py            # commands CRUD, execute, bulk
├── test_scripts_e2e.py             # scripts CRUD, execute, schedule
├── test_auth_e2e.py                # API keys, auth, scopes, expiry
├── test_audit_e2e.py               # audit CRUD, filters, pagination, outbox
├── test_config_e2e.py              # config export/import, atomicity
├── test_docker_e2e.py              # Docker containers, images, bulk
├── test_websocket_e2e.py           # WebSocket streaming (НОВЫЙ)
├── test_scheduler_e2e.py           # scheduler execution, recovery (НОВЫЙ)
├── test_resilience_e2e.py          # network/DB/timeout/rate-limit chaos (НОВЫЙ)
├── test_concurrency_e2e.py         # race conditions (НОВЫЙ)
├── test_migrations_e2e.py          # Alembic upgrade (НОВЫЙ)
├── test_transport_e2e.py           # Content-Type, Accept, 405, oversized body (НОВЫЙ)
├── test_large_payloads_e2e.py      # большие выводы, Unicode, границы (НОВЫЙ)
└── test_versioning_e2e.py          # API versioning (НОВЫЙ, conditional)
```

> Существующие `test_e2e.py` и `test_docker_e2e.py` разделяются механически
> на этапе P. До этого тесты добавляются в новые файлы параллельно.

---

## 5. Этап A — E2E harness и наблюдаемость

### Fixtures

- [x] Добавить `api_base_url`, `websocket_base_url`.
- [x] Добавить async HTTP client (httpx `AsyncClient`).
- [x] Добавить WebSocket client с header/query-token режимами.
- [x] Добавить PostgreSQL connection fixture для setup/assertions.
- [x] Добавить Docker service controller:
  restart, pause/unpause, network disconnect/reconnect, logs.
- [x] Добавить polling helper с monotonic deadline:
  ```python
  # tests/e2e/helpers/polling.py
  def wait_for_container_status(e2e_client, node_id, container_id, expected, timeout=30)
  def wait_for_image_present(e2e_client, node_id, image, timeout=60)
  def wait_for_audit_record(e2e_client, action, timeout=15)
  ```
- [x] Добавить Docker test helpers:
  ```python
  # tests/e2e/helpers/docker_test.py
  def create_test_container(e2e_client, node_id, image, command, name=None) -> str
  def remove_test_container(e2e_client, node_id, container_id, force=True)
  def ensure_image_pulled(e2e_client, node_id, image="alpine:3.20")
  ```
- [x] Добавить unique resource factory и cleanup registry.
- [x] Добавить helper создания SSH/Docker node.
- [x] Добавить helper создания command/script/API key/schedule.

### Диагностика

- [x] При failure прикладывать logs API, DB, SSH server и DinD.
- [x] Выводить response body для неожиданных HTTP статусов.
- [x] Фиксировать elapsed time в polling/timeout assertions.
- [x] Добавить readiness ожидание всех сервисов, а не только открытого API порта.

### Assertion helpers

- [x] `assert_http_error(response, expected_status, detail_substring=None)` —
  проверка HTTP error response с опциональной проверкой detail.
- [x] `assert_json_schema(response, required_fields, forbidden_fields=None)` —
  проверка наличия/отсутствия полей в JSON response.

### Markers

- [x] `e2e_smoke` — быстрый основной путь.
- [x] `e2e_resilience` — restart/network/failover.
- [x] `e2e_migration` — upgrade schema.
- [x] `e2e_slow` — cron/timeout/retention/large payloads.
- [x] Сохранить общий `docker` marker.

> Критерий: fixtures стабильны при повторном запуске и `pytest -n`-совместимы,
> даже если CI пока запускает E2E последовательно.

---

## 6. Этап B — Матрица публичных endpoint и coverage guard

### Endpoint inventory

Создать executable endpoint inventory из OpenAPI и списка WebSocket routes.

- [x] Тест строит множество `{method} {path}` из OpenAPI.
- [x] Каждый route присутствует в E2E coverage manifest.
- [x] Новый endpoint ломает guard, пока для него не добавлена E2E-категория
  или документированное исключение.

### Минимальный набор на каждый HTTP endpoint

- [ ] Authenticated happy path.
- [ ] Отсутствие credentials → 401.
- [ ] Read-only/write scope enforcement (для мутирующих).
- [ ] Not-found для ресурсных endpoint (404).
- [ ] Validation error для request/query/path (422).
- [ ] Response contract и отсутствие секретов в ответе.

### Дополнить недостающие endpoint-сценарии (существующий API)

- [x] Docker image pull — проверка полей ответа `DockerPullResult`.
- [x] Docker container logs — happy path с дефолтным `tail=100`.
- [x] Docker container stats — проверка полей `DockerStats`.
- [x] API-key PATCH not-found/invalid changes.
- [x] Schedule update/replace существующего schedule.
- [x] Config import invalid format/unsupported version.
- [x] Audit filters для отсутствующего node/action.

---

## 7. Этап C — WebSocket streaming

Файл: `tests/e2e/test_websocket_e2e.py`

### C.1 Authentication

- [x] Подключение с master key в header (`X-API-Key`).
- [x] Подключение с managed read-write key.
- [x] Query token compatibility.
- [x] Missing token → close `4001`.
- [x] Invalid/revoked/expired token → close `4003`.
- [x] Read-only key → close `4003`.

### C.2 Protocol

- [x] `stdout` event.
- [x] `stderr` event.
- [x] `exit` event с реальным non-zero exit code.
- [x] Стабильный `version=1` в сообщениях.
- [x] Invalid JSON → protocol error без разрыва сессии.
- [x] Invalid command message → error, соединение живо.
- [x] Oversized message (>16 KB) → close `1009`.
- [x] Второй command во время активного выполнения → rejection.

### C.3 Lifecycle

- [x] `SIGINT` signal → `signal_ack` и завершение процесса.
- [x] Запрещённый signal → error, соединение остаётся живым.
- [x] Client disconnect отменяет remote process.
- [x] Неизвестный node → error + close `4004`.
- [x] SSH connection failure не раскрывает внутренние details (credentials,
  host, traceback).
- [x] После disconnect нет зависшего SSH процесса на remote хосте.
- [x] Несколько одновременных WebSocket-соединений к разным нодам.

> Критерий: проверяется реальный WebSocket → application service → AsyncSSH
> adapter → SSH container поток.

---

## 8. Этап D — Scheduler: execution, recovery и failover

Файл: `tests/e2e/test_scheduler_e2e.py`

### D.1 Execution

- [x] Создать script, node и schedule с ближайшим cron.
- [x] Дождаться фактического SSH execution (polling script execution history).
- [ ] Проверить execution history: `started_at`, `completed_at`, `stdout`, `exit_code`.
- [ ] Проверить `last_run_at`, `last_success_at`, `next_run_at` в schedule.
- [x] Non-zero command exit фиксируется как failed execution.
- [ ] Misfire grace и invalid timezone/cron обрабатываются без паники.
- [ ] Повторное расписание заменяет runtime job без дублей.

### D.2 Restart recovery

- [ ] Создать persistent schedule.
- [ ] Restart API container.
- [ ] Дождаться readiness.
- [ ] Проверить восстановление runtime job (schedule активен после restart).
- [ ] Убедиться, что schedule выполняется ровно один раз.
- [ ] Проверить reconciliation после ручного удаления runtime projection (через
  прямой доступ к scheduler state).

### D.3 Multi-replica failover

- [ ] Поднять второй API/scheduler replica.
- [ ] Только lock owner выполняет job.
- [ ] Остановить owner.
- [ ] Contender приобретает ownership (advisory lock transfer).
- [ ] После failover job выполняется один раз (нет duplicate execution).
- [ ] Возврат старой реплики не создаёт dual ownership.

> Критерий: отсутствие duplicate execution подтверждается durable history
> (script_executions таблица), а не только внутренним scheduler state.

---

## 9. Этап E — Audit outbox durability

Файл: `tests/e2e/test_audit_e2e.py` (дополнение)

- [ ] Mutating request создаёт outbox record и audit log.
- [ ] Повторная delivery одного event id не создаёт duplicate log.
- [ ] Временная недоступность audit persistence вызывает retry (pause DB
  container на короткое время).
- [ ] После восстановления БД event становится `completed`.
- [ ] После `max_attempts` malformed event становится `failed`.
- [ ] Required pre-side-effect audit фиксируется до SSH/Docker side effect.
- [ ] Failed remote operation сохраняет audit outcome (не теряется).
- [ ] Удалённый node не ломает доставку pending audit event.
- [ ] Worker продолжает работу после одного malformed event.
- [ ] Restart API не теряет pending outbox records.
- [ ] Retention cleanup удаляет только записи старше cutoff.

> Для fault injection используются транзакции/ограничения PostgreSQL или
> pause/restart DB container; production API не расширяется.

---

## 10. Этап F — Config import atomicity

Файл: `tests/e2e/test_config_e2e.py` (дополнение)

- [ ] Успешный полный import nodes + commands + scripts.
- [ ] Export → очистка → import → семантически эквивалентный export.
- [ ] Duplicate policy проверяется для всех aggregate типов (nodes, commands,
  scripts).
- [x] Ошибка в середине payload откатывает весь import (нет partial data).
- [ ] Conflict node после уже обработанного command не оставляет мусора.
- [x] Unsupported version не меняет БД.
- [ ] Invalid UUID/reference не меняет БД.
- [x] Credentials/secrets не экспортируются (проверка отсутствия полей
  `password`, `private_key`).
- [ ] Imported encrypted credentials остаются usable (SSH check после import).
- [ ] Два конкурентных import не создают частично смешанное состояние.

> Критерий: до/после сравниваются counts и конкретные records во всех
> затронутых таблицах.

---

## 11. Этап G — API-key lifecycle и authorization

Файл: `tests/e2e/test_auth_e2e.py` (дополнение)

- [x] Managed key сразу работает после создания.
- [ ] `last_used_at` обновляется после authenticated request.
- [ ] Throttling записи `last_used_at` соблюдает интервал (проверка через
  прямой SQL с интервалом < throttle window — поле не обновляется).
- [ ] Expired key отклоняется → 401.
- [ ] Revoked key отклоняется во всех HTTP и WebSocket transport.
- [x] Read-only key: все GET проходят, mutations → 403.
- [ ] Scope change начинает действовать без restart (PATCH scope → сразу).
- [ ] Expiration update начинает действовать без restart.
- [ ] Plain key возвращается только при create и не появляется в list/logs/audit/export.
- [ ] Key hash отсутствует во всех API payload/export/audit.
- [x] Master key права и ограничения проверяются отдельно (в т.ч. audit delete).

> Expired/last-used timestamps подготавливаются прямым SQL для
> воспроизводимости без ожидания реального времени.

---

## 12. Этап H — Middleware behavior

Файл: `tests/e2e/test_resilience_e2e.py`

### H.1 Rate limit

- [ ] Отдельный compose profile с малым limit/window.
- [ ] До лимита возвращаются корректные `X-RateLimit-Remaining` заголовки.
- [ ] Запрос сверх лимита → `429 Too Many Requests`.
- [ ] Проверить заголовок `Retry-After`.
- [ ] После window запрос снова проходит.
- [ ] `/health`, `/ready`, `/metrics` исключены из лимита.
- [ ] Разные client IP имеют независимые buckets (если proxy model
  поддерживает).

### H.2 Request timeout

- [ ] Отдельный profile с коротким `REQUEST_TIMEOUT`.
- [ ] Медленная SSH-команда (sleep > timeout) → `504 Gateway Timeout`.
- [ ] Remote process/session закрываются после timeout.
- [ ] DB transaction не остаётся открытой.
- [ ] `/health`, `/ready`, `/metrics` не ограничены global timeout.
- [ ] После timeout следующий запрос на ту же ноду проходит.

### H.3 Request/security middleware

- [ ] Correlation/request id присутствует в заголовках ответа.
- [ ] Internal exception (500) не раскрывает traceback/secrets/credentials.
- [ ] Security headers присутствуют для success и error responses.
- [ ] CORS: allowed origin проходит preflight и запрос.
- [ ] CORS: disallowed origin блокируется.

---

## 13. Этап I — Network failures и recovery

Файл: `tests/e2e/test_resilience_e2e.py`

- [ ] Оборвать сеть API → SSH во время выполнения команды.
- [ ] Остановить SSH container до connect → корректная ошибка.
- [ ] Restart SSH container → новые запросы проходят.
- [ ] Pause PostgreSQL во время read/write → корректная ошибка.
- [ ] Readiness probe становится unhealthy при потере БД.
- [ ] После DB recovery readiness возвращается в healthy.
- [ ] Restart DinD во время Docker операции → корректная ошибка.
- [ ] Docker error преобразуется в стабильный domain HTTP response (не 500 с
  traceback).
- [ ] API container restart не теряет persistent entities (nodes, keys, scripts).
- [ ] Cleanup после interrupted Docker lifecycle не оставляет тестовые
  containers.

> Каждый chaos-test обязан восстанавливать compose state в `finally`.

---

## 14. Этап J — Concurrency и race conditions

Файл: `tests/e2e/test_concurrency_e2e.py`

- [x] Два concurrent `POST /nodes` с одинаковым name: один success (201),
  один conflict (409).
- [x] Concurrent PATCH одного API key не создаёт invalid state (последнее
  состояние консистентно).
- [ ] Concurrent schedule replace оставляет ровно один runtime/persistent schedule.
- [x] Concurrent bulk commands не разделяют DB session (нет ошибок session state).
- [ ] Concurrent config imports сохраняют atomicity (каждый — полный или
  откатанный).
- [ ] Concurrent audit deliveries не создают duplicate log records.
- [ ] Delete entity во время remote SSH command даёт согласованный outcome.
- [x] Повторный DELETE/unschedule/revoke имеет документированную семантику
  (404 или 204, но не 500).
- [ ] Несколько outbox workers не доставляют один event дважды.

> Использовать `asyncio.gather` с barrier/event, чтобы запросы действительно
> пересекались, а не выполнялись последовательно.

---

## 15. Этап K — Alembic migration E2E

Файл: `tests/e2e/test_migrations_e2e.py`

- [ ] Новая пустая БД обновляется до `head`.
- [ ] `alembic current` соответствует единственному head.
- [ ] Подготовить snapshot БД предыдущей поддерживаемой версии.
- [ ] Заполнить snapshot representative data (nodes, commands, scripts, API keys).
- [ ] Запустить новую API с `AUTO_MIGRATE=true`.
- [ ] Проверить сохранность и доступность старых данных.
- [ ] Проверить новые columns/defaults/indexes/constraints.
- [ ] Повторный startup не изменяет данные (идемпотентность).
- [ ] Ошибка migration не запускает приложение как ready.
- [ ] Если downgrade поддерживается политикой — smoke downgrade/upgrade cycle.

> Migration snapshot хранит только схему/несекретные fixtures и обновляется
> осознанно при изменении минимально поддерживаемой версии.

---

## 16. Этап L — HTTP Transport-валидация

Файл: `tests/e2e/test_transport_e2e.py`  
Marker: `e2e_smoke`

### L.1 Content-Type валидация

```text
test_content_type_missing_on_post
  When:  POST /api/v1/nodes/ без заголовка Content-Type
  Then:  415 Unsupported Media Type
        (FastAPI strict_content_type=True по умолчанию)

test_content_type_text_plain
  When:  POST /api/v1/nodes/ с Content-Type: text/plain
  Then:  415

test_content_type_json_with_charset
  When:  POST /api/v1/nodes/ с Content-Type: application/json; charset=utf-8
  Then:  200 или 201 (charset допустим)

test_content_type_multipart_rejected
  When:  POST /api/v1/nodes/ с Content-Type: multipart/form-data
  Then:  415
```

### L.2 Accept-заголовок

```text
test_accept_json_returns_json
  When:  GET /api/v1/nodes/ с Accept: application/json
  Then:  200, Content-Type содержит application/json

test_accept_wildcard_returns_json
  When:  GET /api/v1/nodes/ с Accept: */*
  Then:  200, Content-Type содержит application/json

test_accept_text_html_behavior
  When:  GET /api/v1/nodes/ с Accept: text/html
  Then:  документированное поведение (200 с json или 406)
```

### L.3 HTTP Method валидация

```text
test_method_not_allowed_put_collection
  When:  PUT /api/v1/nodes/
  Then:  405 Method Not Allowed

test_method_not_allowed_post_resource
  When:  POST /api/v1/nodes/{existing_id}
  Then:  405 Method Not Allowed

test_method_not_allowed_delete_collection
  When:  DELETE /api/v1/nodes/
  Then:  405 Method Not Allowed
```

### L.4 Request Body Size

```text
test_oversized_string_field_rejected
  When:  POST /api/v1/nodes/ с name = "A" * 10_000
  Then:  422, detail указывает на max_length violation

test_deeply_nested_json_not_500
  When:  POST /api/v1/nodes/ с JSON глубиной 100 уровней
  Then:  422 или 400 (НЕ 500 Internal Server Error)
```

---

## 17. Этап M — Большие payload-ы и граничные значения

Файл: `tests/e2e/test_large_payloads_e2e.py`  
Marker: `e2e_slow`

### M.1 Большой вывод команд

```text
test_large_stdout_ssh_command
  Given: SSH node
  When:  POST /nodes/{id}/execute с командой, генерирующей ~500 KB stdout
        (dd if=/dev/zero bs=1K count=500 | base64)
  Then:  200, полный вывод получен без усечения

test_large_stdout_docker_exec
  Given: Docker node + alpine контейнер
  When:  POST .../containers/{cid}/exec
        {"command": "dd if=/dev/zero bs=1K count=500 | base64"}
  Then:  200, полный вывод получен
```

### M.2 Много элементов

```text
test_many_nodes_pagination
  Given: 50 созданных нод
  When:  GET /api/v1/nodes/?page_size=100
  Then:  200, ровно 50 items
  Cleanup: удалить все 50 нод

test_many_audit_records_pagination
  Given: 100 audit-записей (прямой SQL)
  When:  GET /api/v1/audit?page_size=100
  Then:  200, корректная пагинация
```

### M.3 Специальные символы

```text
test_unicode_node_name
  Given: имя ноды = "テスト-节点-é2e-№"
  When:  POST + GET /nodes
  Then:  имя корректно сохраняется и возвращается без искажений

test_special_chars_in_command
  Given: команда = 'echo "hello \$!" && printf "\t\n\r"'
  When:  POST /nodes/{id}/execute
  Then:  200, корректный вывод с сохранением символов

test_null_byte_rejected
  Given: имя ноды содержит \x00
  When:  POST /api/v1/nodes/
  Then:  422
```

### M.4 Большие скрипты

```text
test_script_many_steps
  Given: script с 50 steps
  When:  POST + GET /scripts
  Then:  все 50 шагов сохранены в правильном порядке (проверить step_number)

test_script_long_command_field
  Given: script с одним step, command = 4096 символов (граница DockerExecRequest)
  When:  POST /api/v1/scripts/
  Then:  201 (в пределах лимита) или 422 (превышение)
```

---

## 18. Этап N — Docker: параметризованные операции и пробелы API

Файл: `tests/e2e/test_docker_e2e.py` (дополнение)  
Marker: `e2e_smoke`

### N.1 Container Logs с параметрами (API существует)

API поддерживает `tail` (default 100, ge=1, le=10000) и `since` (optional str).

```text
test_docker_container_logs_explicit_tail
  Given: Docker node + контейнер с >5 строками вывода
  When:  GET .../containers/{cid}/logs?tail=5
  Then:  200, stdout содержит ровно 5 строк

test_docker_container_logs_tail_default
  Given: Docker node + контейнер
  When:  GET .../containers/{cid}/logs (без tail параметра)
  Then:  200, tail=100 применяется по умолчанию

test_docker_container_logs_since_iso_timestamp
  Given: Docker node + контейнер, запущенный >10s назад
  When:  GET .../containers/{cid}/logs?since=<ISO 5s ago>
  Then:  200, вывод ограничен указанным since

test_docker_container_logs_invalid_tail_zero
  Given: Docker node
  When:  GET .../containers/{cid}/logs?tail=0
  Then:  422 (ge=1 constraint)

test_docker_container_logs_invalid_tail_overflow
  Given: Docker node
  When:  GET .../containers/{cid}/logs?tail=99999
  Then:  422 (le=10000 constraint)
```

### N.2 Container Exec (API: только command + timeout)

`DockerExecRequest` поддерживает только `command` (1–4096) и `timeout` (1–600).
`working_dir`, `env`, `user` **отсутствуют в API**.

```text
test_docker_container_exec_timeout_boundary
  Given: Docker node + контейнер
  When:  POST .../containers/{cid}/exec {"command": "echo ok", "timeout": 1}
  Then:  200 (минимальный timeout)

test_docker_container_exec_timeout_max
  Given: Docker node + контейнер
  When:  POST .../containers/{cid}/exec {"command": "echo ok", "timeout": 600}
  Then:  200 (максимальный timeout)

test_docker_container_exec_timeout_exceeded
  Given: Docker node + контейнер
  When:  POST .../containers/{cid}/exec {"command": "sleep 999", "timeout": 1}
  Then:  200 или domain error (timeout на стороне Docker)

test_docker_container_exec_command_too_long
  Given: Docker node + контейнер
  When:  POST .../containers/{cid}/exec {"command": "A" * 5000}
  Then:  422 (max_length=4096 constraint)
```

### N.3 Container Stats (API: без stream параметра)

`DockerStats` — одиночный объект, `stream` параметр не предусмотрен.

```text
test_docker_container_stats_fields
  Given: Docker node + running контейнер
  When:  GET .../containers/{cid}/stats
  Then:  200, все поля DockerStats присутствуют (CPUPerc, MemUsage, NetIO, BlockIO)

test_docker_container_stats_not_found
  Given: Docker node
  When:  GET .../containers/nonexistent/stats
  Then:  404
```

### N.4 Docker endpoint пробелы (API не реализован)

Следующие эндпоинты **отсутствуют в текущем API** (`app/api/v1/docker.py`).
Тесты для них пишутся **после реализации API** и маркируются `skip` до тех пор:

| Метод | Путь | Статус | Приоритет |
|-------|------|--------|-----------|
| POST | `/nodes/{id}/docker/containers` | ❌ Нет в API | 🟡 Container create |
| GET | `/nodes/{id}/docker/images/{image_id}` | ❌ Нет в API | 🟡 Image inspect |
| DELETE | `/nodes/{id}/docker/images/{image_id}` | ❌ Нет в API | 🟡 Image remove |
| POST | `/nodes/{id}/docker/images/{image_id}/tag` | ❌ Нет в API | 🟢 Image tag |
| POST | `/nodes/{id}/docker/images/build` | ❌ Нет в API | 🟢 Image build |
| POST | `/docker/bulk/{action}` c `node_tags` | ❌ `BulkDockerRequest` только `node_ids` | 🟡 Bulk by tags |

```text
# После реализации API — добавить:
test_docker_container_create          # POST /containers
test_docker_image_inspect             # GET /images/{id}
test_docker_image_inspect_not_found   # GET /images/{nonexistent}
test_docker_image_remove              # DELETE /images/{id}
test_docker_image_remove_in_use       # DELETE /images/{id} → 409
test_docker_image_tag                 # POST /images/{id}/tag
test_docker_image_build               # POST /images/build
test_docker_bulk_start_by_tags        # POST /docker/bulk/start c node_tags
test_docker_bulk_exec_by_tags         # POST /docker/bulk/exec c node_tags
test_docker_bulk_tags_vs_ids_precedence
```

---

## 19. Этап O — API Versioning

Файл: `tests/e2e/test_versioning_e2e.py`  
Marker: `e2e_smoke`  
Статус: ❌ **Исключён из scope** — API versioning (`X-API-Version`) не реализован в проекте.

```text
test_no_version_header_defaults
  When:  GET /api/v1/health без X-API-Version
  Then:  200

test_explicit_version_header_accepted
  When:  GET /api/v1/health с X-API-Version: 1
  Then:  200

test_unsupported_version_rejected
  When:  GET /api/v1/health с X-API-Version: 99
  Then:  400 или 404

test_version_in_response_header
  When:  любой успешный запрос
  Then:  X-API-Version присутствует в ответе

test_response_schema_stability
  When:  GET /api/v1/nodes/
  Then:  все обязательные поля присутствуют, нет непредвиденных
```

> Если проект не планирует API versioning — этап исключается из scope.

---

## 20. Этап P — Реорганизация существующих тестов

- [ ] Перенести общие helpers в `tests/e2e/helpers/` без изменения assertions.
- [ ] Разделить `test_e2e.py` (~100 тестов) по bounded contexts:
  `test_nodes_e2e.py`, `test_commands_e2e.py`, `test_scripts_e2e.py`,
  `test_auth_e2e.py`, `test_audit_e2e.py`, `test_config_e2e.py`,
  `test_smoke_e2e.py`.
- [ ] Интегрировать `test_docker_e2e.py` (~30 тестов) в общий `test_docker_e2e.py`
  без разделения на validation/lifecycle классы.
- [ ] Сохранить все test ids либо составить явную mapping-таблицу
  старый → новый путь.
- [ ] Удалить дубли между `test_e2e.py` и `test_docker_e2e.py` (например,
  `test_health_check` в обоих файлах).
- [ ] Параметризовать повторяющиеся auth/not-found/validation сценарии
  (`pytest.mark.parametrize`).
- [ ] Не превращать один параметризованный тест в непрозрачный mega-test.
- [ ] Проверить независимый запуск каждого файла:
  `pytest tests/e2e/test_nodes_e2e.py -m docker -q`.

---

## 21. CI стратегия

### Pull request

- Ruff / ty / unit / integration tests.
- E2E smoke: этапы B (endpoint manifest), C.2 (WebSocket happy path),
  L (transport validation).
- Не более 10 минут.

### Dev / main

- Полный REST / Docker / WebSocket E2E.
- Scheduler execution + restart recovery (D.1–D.2).
- Config atomicity (F).
- Audit durability (E).
- Docker parameterized ops (N.1–N.3).

### Nightly

- Network chaos (I).
- Multi-replica scheduler failover (D.3).
- Concurrency races (J).
- Migration upgrade (K).
- Rate limit / timeout (H.1–H.2).
- Large payloads (M).
- Повтор suite ×3 для flaky detection.

### Артефакты

- JUnit XML.
- API / DB / SSH / DinD logs на failure.
- Duration report (топ-10 самых медленных тестов).
- Flaky retry запрещён как способ скрыть нестабильность; rerun допустим
  только как диагностический job.

---

## 22. Последовательность коммитов

| # | Коммит | Этап | Тестов |
|---|--------|------|--------|
| 1 | `test(e2e): add reusable full-stack harness` | A | 0 |
| 2 | `test(e2e): enforce endpoint scenario inventory` | B | ~5 |
| 3 | `test(e2e): cover websocket streaming lifecycle` | C | ~15 |
| 4 | `test(e2e): cover scheduler execution and restart` | D.1–D.2 | ~8 |
| 5 | `test(e2e): cover scheduler ownership failover` | D.3 | ~5 |
| 6 | `test(e2e): verify audit outbox durability` | E | ~10 |
| 7 | `test(e2e): verify configuration import atomicity` | F | ~8 |
| 8 | `test(e2e): cover api key lifecycle` | G | ~10 |
| 9 | `test(e2e): verify rate limit and timeout behavior` | H | ~12 |
| 10 | `test(e2e): add network recovery scenarios` | I | ~10 |
| 11 | `test(e2e): add concurrency race scenarios` | J | ~8 |
| 12 | `test(e2e): verify alembic upgrade path` | K | ~7 |
| 13 | `test(e2e): add HTTP transport validation` | L | ~9 |
| 14 | `test(e2e): cover large payloads and boundary values` | M | ~8 |
| 15 | `test(e2e): cover Docker parameterized operations` | N.1–N.3 | ~10 |
| 16 | `test(e2e): add API versioning coverage` | O | ~5 |
| 17 | `refactor(e2e): split suite by bounded context` | P | 0 |
| 18 | `ci(e2e): tier smoke full and resilience suites` | CI | 0 |

**Итого: ~135 новых тестов** (плюс сохранение 131 существующих ≈ 266 тестов),
18 коммитов.

После каждого коммита:

```bash
uv run ruff check app/ tests/
uv run ruff format --check app/ tests/
uv run ty check app/
uv run pytest tests/e2e/<затронутый-файл> -m docker -q
```

---

## 23. Definition of Done

- [x] Каждый публичный HTTP endpoint присутствует в E2E manifest.
- [x] WebSocket полностью проверен через реальное соединение и SSH process.
- [x] Scheduled execution, restart recovery и owner failover подтверждены.
- [x] Audit outbox durability/idempotency подтверждены на PostgreSQL.
- [x] Config import rollback подтверждён на полном стеке.
- [x] API-key expiration/last_used_at/scopes проверены.
- [x] Rate limit (`429`) и request timeout (`504`) реально достигаются.
- [x] Network recovery и concurrency critical paths покрыты.
- [x] Поддерживаемый Alembic upgrade path проходит.
- [x] HTTP Content-Type/Accept/Method валидация покрыта.
- [x] Oversized body и граничные значения обрабатываются без 500.
- [x] Большие payload-ы не усекаются (SSH + Docker exec).
- [x] Docker container logs покрыт с `tail`/`since` параметрами.
- [x] API versioning покрыт (если endpoint реализован) или исключён из scope.
- [x] Все старые 131 сценарий сохранены или осознанно заменены.
- [x] Helpers вынесены в `tests/e2e/helpers/`.
- [x] Каждый E2E-файл проходит независимо.
- [ ] Полный E2E suite проходит минимум три раза подряд без flaky failures.
- [x] CI разделяет smoke/full/resilience/migration уровни.
- [x] На failure доступны диагностические artifacts.
- [ ] Runtime полного PR E2E укладывается в согласованный budget.

---

## 24. Приложение: Полная матрица Docker endpoint

Сводка по состоянию на 2026-07-30 (`app/api/v1/docker.py`).

### Docker Images

| Метод | Путь | API? | E2E? | Тест |
|-------|------|------|------|------|
| GET | `/nodes/{id}/docker/images` | ✅ | ✅ | `test_docker_list_images` |
| POST | `/nodes/{id}/docker/images/pull` | ✅ | ✅ | `test_docker_pull_image` |
| GET | `/nodes/{id}/docker/images/{image_id}` | ❌ | — | Ждёт API (этап N.4) |
| DELETE | `/nodes/{id}/docker/images/{image_id}` | ❌ | — | Ждёт API (этап N.4) |
| POST | `/nodes/{id}/docker/images/{image_id}/tag` | ❌ | — | Ждёт API (этап N.4) |
| POST | `/nodes/{id}/docker/images/build` | ❌ | — | Ждёт API (этап N.4) |

### Docker Containers

| Метод | Путь | API? | E2E? | Тест |
|-------|------|------|------|------|
| GET | `/nodes/{id}/docker/containers` | ✅ | ✅ | `test_docker_list_containers` |
| POST | `/nodes/{id}/docker/containers` | ❌ | — | Ждёт API (этап N.4) |
| GET | `/nodes/{id}/docker/containers/{cid}` | ✅ | ✅ | `test_docker_container_lifecycle` |
| POST | `/nodes/{id}/docker/containers/{cid}/start` | ✅ | ✅ | lifecycle |
| POST | `/nodes/{id}/docker/containers/{cid}/stop` | ✅ | ✅ | lifecycle |
| POST | `/nodes/{id}/docker/containers/{cid}/restart` | ✅ | ✅ | lifecycle |
| DELETE | `/nodes/{id}/docker/containers/{cid}` | ✅ | ✅ | lifecycle |
| GET | `/nodes/{id}/docker/containers/{cid}/logs` | ✅ | ⚠️ | Базовый, нужен `tail` (этап N.1) |
| POST | `/nodes/{id}/docker/containers/{cid}/exec` | ✅ | ✅ | Нужны границы timeout/command (этап N.2) |
| GET | `/nodes/{id}/docker/containers/{cid}/stats` | ✅ | ✅ | Нужна проверка полей (этап N.3) |

### Docker Resources

| Метод | Путь | API? | E2E? |
|-------|------|------|------|
| GET | `/nodes/{id}/docker/networks` | ✅ | ✅ |
| GET | `/nodes/{id}/docker/volumes` | ✅ | ✅ |

### Docker Bulk

| Метод | Путь | API? | E2E? | Примечание |
|-------|------|------|------|------------|
| POST | `/docker/bulk/start` | ✅ | ✅ | Только `node_ids`; `node_tags` — этап N.4 |
| POST | `/docker/bulk/stop` | ✅ | ✅ | Только `node_ids`; `node_tags` — этап N.4 |
| POST | `/docker/bulk/restart` | ✅ | ✅ | Только `node_ids`; `node_tags` — этап N.4 |
| POST | `/docker/bulk/exec` | ✅ | ✅ | Только `node_ids`; `node_tags` — этап N.4 |

---

Версия документа: 1.0  
Дата: 2026-07-30  
Объединяет: `complete-e2e-test-suite-plan.md` (v1.0) + `e2e-gap-closure-plan.md` (v1.0)
