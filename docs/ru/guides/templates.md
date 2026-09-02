---
title: Шаблонные паки и реестры
description: Совместное использование команд и скриптов через реестры и паки с активами и установками.
status: stable
translation_key: guides.templates
source_revision: "2026-09-02"
---

# Шаблонные паки и реестры

Шаблоны — это переиспользуемые bundles из команд, скриптов и файлов-активов.
Они изолированы от нод, команд, скриптов, Docker и compose и управляются через
`/api/v2/templates`. Есть два уровня: реестры (GitHub-источники) и паки (сам bundle).

Структура пака на диске следует соглашению репозитория:

```
templates/{pack_id}/
  manifest.json
  commands.json
  scripts.json
  README.md           # опционально
  assets/
    docker-compose.yml
    nginx.conf
    ...
```

`pack_id` — имя каталога (уникально внутри реестра). API хранит метаданные в
`template_packs` (`{id, registry_id, pack_id, name, description, version, author, tags, manifest_sha, readme, installed_version, installed_at}`), активы в `template_assets` (`{id, pack_id, path, size, sha, content}`) с уникальностью `(pack_id, path)`, связи установки в `template_installations` (`{id, pack_id, entity_type, entity_id}`), и записи реестра в `template_registries` (`{id, owner, name, default_branch, last_synced_at}`).

`tags` — `ARRAY(String)` (GIN, JSON fallback для SQLite), `manifest_sha` — хэш манифеста для детекции изменений. `ScriptStep` внутри `scripts.json` использует `{command_name?: string, command_id?: UUID}` xor — ровно одно из полей задаёт шаг.

Списки — cursor-пагинация (`?cursor=<base64>&limit=20 → {items,next_cursor,has_more,limit}`), неверный cursor → `422`. Bulk-результаты — единый envelope `BulkResult` (`{total,succeeded,failed,results}`) с `200` или `207 Multi-Status`. Мутации требуют ключ `read-write`.

## Реестры (GitHub-источники)

Реестр указывает на GitHub-репозиторий, где по ветке `default_branch` лежат деревья `templates/{pack_id}/`.

### Создание реестра

```bash
curl --fail-with-body -X POST \
  "${NODE_NEXUS_URL}/api/v2/templates/registries" \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  -H 'Content-Type: application/json' \
  -d '{
    "owner": "my-org",
    "name": "node-nexus-templates",
    "github_token": "ghp_xxx",
    "default_branch": "main"
  }'
  # -> 201 {id, owner, name, default_branch, last_synced_at, created_at, updated_at}
```

`github_token` опционален (нужен для приватных репозиториев) и не возвращается. `409` при дубликате `(owner, name)`.

### Список / получение / удаление реестров

```bash
  # Список (cursor)
curl --fail-with-body \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v2/templates/registries?limit=20&cursor=eyJvZmZzZXQiOjIwfQ=="
  # -> {items, next_cursor, has_more, limit}

  # Один
curl --fail-with-body \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v2/templates/registries/${REGISTRY_ID}"

  # Удаление
curl --fail-with-body -X DELETE \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v2/templates/registries/${REGISTRY_ID}"
  # -> 204 No Content
```

### Синхронизация реестра

Выкачивает `templates/{pack_id}/` из GitHub, upsert'ит паки и возвращает результаты по каждому с `200` или `207`.

```bash
curl --fail-with-body -X POST \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v2/templates/registries/${REGISTRY_ID}/syncs"
  # -> {registry_id, total, succeeded, failed, results:[{pack_id,status:"success"|"error",error,message}]}
```

`total` — число найденных каталогов паков; `succeeded`/`failed` суммируют парсинг файлов и DB-upsert'ы. `404`, если реестр не найден; частичные синки → `207`.

## Паки

Паки могут быть синхронизированы из реестра или созданы локально через API.

### Создание локального пака

Inline-активы в base64. `manifest.manifest_sha` опционален и сохраняется как `manifest_sha`.

```bash
curl --fail-with-body -X POST \
  "${NODE_NEXUS_URL}/api/v2/templates/packs" \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  -H 'Content-Type: application/json' \
  -d '{
    "manifest": {
      "pack_id": "docker-install",
      "name": "Docker Install",
      "description": "Install Docker and compose",
      "version": "1.0.0",
      "author": "Ops Team",
      "tags": ["docker","setup"],
      "manifest_sha": "abc123"
    },
    "commands": [
      {
        "name": "install-docker",
        "command": "curl -fsSL https://get.docker.com | sh",
        "parameters": [],
        "tags": ["docker"],
        "description": "Install Docker"
      }
    ],
    "scripts": [
      {
        "name": "setup-stack",
        "description": "Full setup",
        "steps": [
          {"label": "install", "type": "command", "command": "curl -fsSL https://get.docker.com | sh", "on_failure": "stop"}
        ],
        "tags": ["docker"]
      }
    ],
    "readme": "# Docker Install\n...",
    "assets": [
      {"path": "assets/docker-compose.yml", "content_base64": "dmVyc2lvbjogJzMuOCcK..."},
      {"path": "assets/nginx.conf", "content_base64": "c2VydmVyIHsK..."}
    ],
    "registry_id": null
  }'
  # -> 201 {id, registry_id, pack_id, name, description, version, author, tags, manifest_sha, readme, installed_version, installed_at, created_at, updated_at, assets:[{id, pack_id, path,size,sha,created_at,updated_at}]}
```

`registry_id` указывается только когда пак логически принадлежит реестру, созданному в том же окружении. `409`, если `pack_id` уже существует в рамках реестра.

### Список паков с фильтрами

Cursor-пагинация плюс фильтры: `registry_id`, `tag`, `installed`, `search` (ILIKE по name/description).

```bash
  # Все паки
curl --fail-with-body \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v2/templates/packs?limit=20&cursor=eyJvZmZzZXQiOjIwfQ=="

  # По реестру
curl --fail-with-body \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v2/templates/packs?registry_id=${REGISTRY_ID}&limit=20"

  # По тегу
curl --fail-with-body \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v2/templates/packs?tag=docker&limit=20"

  # По признаку installed
curl --fail-with-body \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v2/templates/packs?installed=true&limit=20"

  # Поиск
curl --fail-with-body \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v2/templates/packs?search=docker&limit=20"
```

Ответ — `CursorPage[PackResponse]` (`{items, next_cursor, has_more, limit}`); каждый `PackResponse` содержит `{id, registry_id, pack_id, name, description, version, author, tags, manifest_sha, readme, installed_version, installed_at, created_at, updated_at}`.

### Детали пака и архив

```bash
  # Детали с активами
curl --fail-with-body \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v2/templates/packs/${PACK_ID}"
  # -> {id, ..., assets:[{id, pack_id, path, size, sha, created_at, updated_at}]}

  # Активы как tar-стрим
curl --fail-with-body \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  --output pack.tar \
  "${NODE_NEXUS_URL}/api/v2/templates/packs/${PACK_ID}/archive"
  # -> application/x-tar, Content-Disposition: attachment; filename="<pack_id>.tar"
  # Пустой tar, если у пака нет активов. Алиас: /packs/{id}/assets/archive

  # Связи установки (cursor)
curl --fail-with-body \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v2/templates/packs/${PACK_ID}/installations?limit=20&cursor=eyJvZmZzZXQiOjIwfQ=="
  # -> {items:[{id, pack_id, entity_type:"command"|"script", entity_id, created_at}], next_cursor, has_more, limit}

  # Статистика
curl --fail-with-body \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v2/templates/packs/stats"

curl --fail-with-body \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v2/templates/packs/stats?group_by=tag"
  # -> {total, installed, not_installed, buckets:[{group,total,installed,not_installed}]}
```

`404`, если пак не найден.

## Install, uninstall, update

Установка материализует содержимое пака как реальные команды и скрипты с FK `template_pack_id` и связями через `template_installations`. `on_conflict` управляет коллизиями имён.

```bash
  # Install — создаёт commands/scripts с template_pack_id FK (201|207|409)
curl --fail-with-body -X POST \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v2/templates/packs/${PACK_ID}/installations?on_conflict=fail"
  # -> {total,succeeded,failed,results:[{entity_type,entity_id,name,status:"success"|"error",error}]}
  # on_conflict=fail (по умолчанию) → 409 при существующем имени команды/скрипта
  # on_conflict=rename      → добавляет суффиксы _1, _2 и т.д.

  # Install с переименованием
curl --fail-with-body -X POST \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v2/templates/packs/${PACK_ID}/installations?on_conflict=rename"

  # Uninstall — удаляет сущности, созданные последней установкой
curl --fail-with-body -X POST \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v2/templates/packs/${PACK_ID}/uninstallations"
  # -> 204 No Content

  # Update — uninstall+install атомарно, внимание: локальные правки сгенерированных команд/скриптов будут потеряны
curl --fail-with-body -X POST \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v2/templates/packs/${PACK_ID}/updates?on_conflict=fail"
  # -> 200|207 {total,succeeded,failed,results:[...]}  (409 при конфликте fail)
```

`201` при полной установке, `207` при частичной. Проверяйте `results[]` на `status`/`error`. Uninstall/install не транзакционны между удалёнными нодами — `207` означает частичную материализацию.

## Иерархия и соглашения

- Корень репозитория содержит минимум `templates/{pack_id}/manifest.json` плюс `commands.json` / `scripts.json` по наличию контента.
- Активы лежат под `templates/{pack_id}/assets/` и загружаются через `content_base64`; сервер сохраняет раскодированные байты, `size` и `sha`.
- `GET /packs/{id}/archive` стримит сохранённые активы как `application/x-tar`; используйте его для скачивания bundle активов пака.
- `GET /packs/{id}/installations` выводит связи `template_installations` на созданные строки `commands`/`scripts`.
- `tags` обеспечивают дискавери (`?tag=`) и индексируются через GIN; `manifest_sha` позволяет клиентам определить обновление без перекачки активов.
- Compose-проекты могут ссылаться на пак через `template_pack_id` — см. [Docker Compose](compose.md).

## Валидация и безопасность

Длины `owner`, `name` и `pack_id` ограничены (255/100). `github_token` опционален и скрывается. Бинарные активы должны быть в base64; переполненные или битые payload → `422`. Ошибки синка по отдельным пакам не откатывают остальные успешные upsert'ы в том же синке (`207`). Нужен ключ `read-write` для `POST /registries`, `DELETE`, `syncs`, `packs`, `installations`, `uninstallations` и `updates`.
