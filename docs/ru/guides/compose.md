---
title: Docker Compose проекты
description: Сохранение compose-проектов на ноде и управление жизненным циклом через compose-команды.
status: stable
translation_key: guides.compose
source_revision: "2026-09-02"
---

# Docker Compose проекты

Поддержка Compose изолирована от управления одиночными Docker-контейнерами.
Compose-проект — это сохраняемая запись в `compose_projects` (`{id, node_id, project_name, compose, env, template_pack_id, UNIQUE(node_id, project_name)}`), которая создаётся как чистое состояние БД. Деплой — отдельный шаг: создание проекта не выполняет `compose up`. Все операции скоупированы на ноду по пути `/api/v2/nodes/{id}/docker/compose` и требуют доступный Docker daemon с `docker compose` на хосте. Мутации требуют ключ `read-write` (или JWT с правом записи).

`env` хранится как JSON (`{ "VAR": "value" }`) и проецируется в `.env` на удалённом хосте. `template_pack_id` — опциональный FK на template pack, из которого был создан проект. `project_name` валидируется как `^[a-zA-Z0-9][a-zA-Z0-9_.-]*$`, до 100 символов, уникален в рамках ноды.

Bulk-операции по сервисам возвращают `BulkResult` (`{total,succeeded,failed,results:[{service,status:"success"|"error",error,output}]}`) с `200` при полном успехе или `207 Multi-Status` при частичном. Список проектов — cursor-пагинация (`?cursor=<base64>&limit=20 → {items,next_cursor,has_more,limit}`); неверный cursor → `422`.

## Создание проекта (чистая БД)

Удалённый вызов не выполняется; запись только сохраняется в PostgreSQL.

```bash
curl --fail-with-body -X POST \
  "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/compose/projects" \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  -H 'Content-Type: application/json' \
  -d '{
    "project_name": "web-stack",
    "compose": "services:\n  web:\n    image: nginx:alpine\n    ports:\n      - \"8080:80\"\n",
    "env": {"NGINX_HOST": "example.com"},
    "template_pack_id": null
  }'
  # -> 201 {id, node_id, project_name, compose, env, template_pack_id, created_at, updated_at}
```

`env` может отсутствовать или быть пустым; при обновлении полностью заменяет карту. При конфликте `(node_id, project_name)` — `409`.

## Список проектов (cursor-пагинация)

```bash
  # Первая страница
curl --fail-with-body \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/compose/projects?limit=20"

  # Следующая страница
curl --fail-with-body \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/compose/projects?cursor=eyJvZmZzZXQiOjIwfQ==&limit=20"
  # -> {items, next_cursor, has_more, limit}
```

Cursor кодирует `{"offset": N}` как base64url JSON. Итерируйтесь пока `has_more == true`; на последней странице `next_cursor` равен `null`.

## Получение, обновление, удаление проекта (чистая БД)

```bash
  # Получить по имени
curl --fail-with-body \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/compose/projects/web-stack"

  # Патч (частично) — обновляются только переданные поля, env заменяет все ключи
curl --fail-with-body -X PATCH \
  "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/compose/projects/web-stack" \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  -H 'Content-Type: application/json' \
  -d '{
    "compose": "services:\n  web:\n    image: nginx:1.25\n",
    "env": {"NGINX_HOST": "new.example.com"}
  }'

  # Отвязать от template pack
curl --fail-with-body -X PATCH \
  "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/compose/projects/web-stack" \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  -H 'Content-Type: application/json' \
  -d '{"template_pack_id": null}'

  # Удалить (чистая БД, без удалённого teardown)
curl --fail-with-body -X DELETE \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/compose/projects/web-stack"
  # -> 204 No Content
```

Удаление записи БД не выполняет `compose down`. При необходимости сначала вызовите `/downs`. `404`, если проект не найден на этой ноде.

## Деплой и lifecycle-операции

Деплой явный. `404`, если `project_name` не найден. `207` при частичных ошибках по сервисам.

### `up` / `down`

```bash
  # Up — аналог `docker compose up -d [--build] [--pull]` (BulkResult по сервисам, 200|207)
curl --fail-with-body -X POST \
  "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/compose/projects/web-stack/ups" \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  -H 'Content-Type: application/json' \
  -d '{"pull": false, "build": true, "services": ["web"]}'
  # -> {total,succeeded,failed,results:[{service,status,error,output}]}

  # Up с pull + build по всем сервисам
curl --fail-with-body -X POST \
  "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/compose/projects/web-stack/ups" \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  -H 'Content-Type: application/json' \
  -d '{"pull": true, "build": true}'

  # Down — `docker compose down` (-v volumes, --remove-orphans, -t timeout, --rmi images=all|local)
curl --fail-with-body -X POST \
  "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/compose/projects/web-stack/downs" \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  -H 'Content-Type: application/json' \
  -d '{"volumes": false, "remove_orphans": true, "timeout": 30, "images": null}'
  # -> {status:"down", output:"..."}
```

Без `services` команда применяется ко всем сервисам.

### Bulk-группы (`207`)

Все команды ниже — `POST /nodes/{id}/docker/compose/projects/{name}/{verb}`, возвращают `BulkResult` с `200` или `207`. Тело — `{services?: ["name"]}`, кроме `kills` (`{signal?, services?}`).

| Суффикс пути | Команда | Доп. query | Тело | Элемент BulkResult |
|--------------|---------|------------|------|-------------------|
| `/starts` | `compose start` | — | `{services?:[]}` | `{service,status,error,output}` |
| `/stops` | `compose stop` | `?timeout=10` (1..600) | `{services?:[]}` | то же |
| `/restarts` | `compose restart` | `?timeout=10` | `{services?:[]}` | то же |
| `/pauses` | `compose pause` | — | `{services?:[]}` | то же |
| `/unpauses` | `compose unpause` | — | `{services?:[]}` | то же |
| `/kills` | `compose kill` | — | `{"signal":"SIGTERM", services?:[]}` | то же |
| `/creates` | `compose create` | — | `{services?:[]}` | то же |
| `/rms` | `compose rm -f [-v]` | `?volumes=false` | `{services?:[]}` | то же |
| `/pulls` | `compose pull` | — | `{services?:[]}` | то же |
| `/pushs` | `compose push` | — | `{services?:[]}` | то же |
| `/builds` | `compose build [--no-cache]` | `?no_cache=false` | `{services?:[]}` | то же |

Примеры:

```bash
  # Start / Stop / Restart
curl --fail-with-body -X POST \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" -H 'Content-Type: application/json' \
  -d '{"services": ["web","api"]}' \
  "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/compose/projects/web-stack/starts"

curl --fail-with-body -X POST \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" -H 'Content-Type: application/json' \
  -d '{"services": ["web"]}' \
  "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/compose/projects/web-stack/stops?timeout=30"

curl --fail-with-body -X POST \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" -H 'Content-Type: application/json' \
  -d '{"services": ["web"]}' \
  "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/compose/projects/web-stack/restarts?timeout=30"

  # Pause / Unpause
curl --fail-with-body -X POST \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" -H 'Content-Type: application/json' \
  -d '{"services": ["web"]}' \
  "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/compose/projects/web-stack/pauses"
curl --fail-with-body -X POST \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" -H 'Content-Type: application/json' \
  -d '{"services": ["web"]}' \
  "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/compose/projects/web-stack/unpauses"

  # Kill с сигналом / Rm с volumes / Build --no-cache / Pull / Push
curl --fail-with-body -X POST \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" -H 'Content-Type: application/json' \
  -d '{"signal": "SIGKILL", "services": ["web"]}' \
  "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/compose/projects/web-stack/kills"

curl --fail-with-body -X POST \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" -H 'Content-Type: application/json' \
  -d '{"services": ["web"]}' \
  "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/compose/projects/web-stack/rms?volumes=true"

curl --fail-with-body -X POST \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" -H 'Content-Type: application/json' \
  -d '{"services": ["web"]}' \
  "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/compose/projects/web-stack/builds?no_cache=true"

curl --fail-with-body -X POST \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" -H 'Content-Type: application/json' \
  -d '{"services": ["web"]}' \
  "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/compose/projects/web-stack/pulls"

curl --fail-with-body -X POST \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" -H 'Content-Type: application/json' \
  -d '{"services": ["web"]}' \
  "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/compose/projects/web-stack/pushs"

  # Create сервисов (без старта)
curl --fail-with-body -X POST \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" -H 'Content-Type: application/json' \
  -d '{"services": ["web"]}' \
  "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/compose/projects/web-stack/creates"
```

Проверяйте каждый элемент `results`; `200` — всё успешно, `207` — `succeeded>0 && failed>0`.

### Exec и run

```bash
  # Exec в запущенном сервисе — `compose exec <service> <command>` (-> {stdout,stderr,exit_code})
curl --fail-with-body -X POST \
  "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/compose/projects/web-stack/executions" \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  -H 'Content-Type: application/json' \
  -d '{"service": "web", "command": "nginx -t", "timeout": 30}'

  # Run one-off — `compose run [--detach] <service> [command]` (-> {output})
curl --fail-with-body -X POST \
  "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/compose/projects/web-stack/runs" \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  -H 'Content-Type: application/json' \
  -d '{"service": "web", "command": "echo hello", "detached": false, "timeout": 60}'
```

`service` обязателен; `command` для `run` опционален (используется `CMD` образа). Таймауты 1..600 секунд.

### Инспекция (GET)

| Путь | Query | Ответ |
|------|-------|-------|
| `GET .../ps` | `?all=false` | `{output, containers:[{...}]}` (`compose ps`) |
| `GET .../logs` | `?tail=100&since=...&services=web` | `{output, logs}` (`compose logs --tail`) |
| `GET .../config` | — | `{config, output}` (`compose config` — резолв YAML) |
| `GET .../images` | — | `{images:[...], output}` (`compose images`) |
| `GET .../top` | `?service=web` | `{titles:[...], processes:[[...]], output}` |
| `GET .../port` | `?service=web&private_port=80` (оба обязательны) | `{output, bindings}` |
| `GET .../version` | — | `{version, output}` (`compose version`) |

Примеры:

```bash
curl --fail-with-body \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/compose/projects/web-stack/ps?all=true"

curl --fail-with-body \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/compose/projects/web-stack/logs?tail=200&services=web"

curl --fail-with-body \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/compose/projects/web-stack/config"

curl --fail-with-body \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/compose/projects/web-stack/images"

curl --fail-with-body \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/compose/projects/web-stack/top?service=web"

curl --fail-with-body \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/compose/projects/web-stack/port?service=web&private_port=80"

curl --fail-with-body \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/compose/projects/web-stack/version"
```

## Обработка ошибок

- `422` при неверном `project_name`, пустом/переполненном (>1MiB) `compose`, неверных именах сервисов, неверных query-параметрах (`timeout` вне диапазона, битый cursor) или некорректном JSON для `env`.
- `404`, когда compose-проект не найден на данной ноде.
- `207` требует проверки каждого `results[]`; успешные операции по сервисам не откатываются при частичной ошибке.
- `401/403` при отсутствии или `read-only` ключе на мутациях.

## Валидация и безопасность

`project_name` строго валидируется; содержимое `compose` ограничено по размеру и передаётся как есть удалённому `compose` через SSH. Значения `env` — JSON-строки. Сначала получите ноду, выведите список проектов, затем деплойте. Считайте Compose-команды привилегированными — они запускают произвольные образы/команды на ноде.
