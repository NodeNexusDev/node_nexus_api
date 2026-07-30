---
title: Управление нодами
status: stable
translation_key: guides.nodes
source_revision: "2026-07-30"
---

# Управление нодами

Ноды — это удалённые серверы, доступные по SSH. Каждая нода хранит
зашифрованные учётные данные, метаданные подключения, теги и статус последней
проверки.

## Создание ноды

```bash
curl --fail-with-body -X POST "${NODE_NEXUS_URL}/api/v1/nodes/" \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  -H 'Content-Type: application/json' \
  -d '{
    "name": "web-01",
    "host": "192.0.2.10",
    "port": 22,
    "connection_type": "ssh",
    "username": "ops",
    "password": "change-me",
    "tags": ["production", "frontend"]
  }'
```

Сохраните возвращённый UUID для метрик, выполнения команд и проверок
подключения.

## Список и фильтрация

Offset-пагинация:

```bash
curl --fail-with-body --get \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  --data-urlencode 'page=1' \
  --data-urlencode 'size=20' \
  "${NODE_NEXUS_URL}/api/v1/nodes/"
```

Фильтрация по тегам с логикой AND:

```bash
curl --fail-with-body --get \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  --data-urlencode 'tags=production' \
  --data-urlencode 'tags=frontend' \
  "${NODE_NEXUS_URL}/api/v1/nodes/"
```

Не смешивайте offset-пагинацию (`page`/`size`) и cursor-пагинацию
(`cursor`/`limit`) в одном запросе. Используйте `total` из ответа для
итерации страниц.

## Проверка подключения

```bash
curl --fail-with-body -X POST \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v1/nodes/${NODE_ID}/check/"
```

Успешная проверка подтверждает доступность по SSH. Статус ноды обновляется
автоматически.

## Системные метрики

```bash
curl --fail-with-body \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v1/nodes/${NODE_ID}/metrics/"
```

Возвращает информацию о CPU, памяти, дисках и нагрузке с удалённого хоста.

Актуальные схемы запросов и ответов смотрите в Swagger UI (`/docs`).
