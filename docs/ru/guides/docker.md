---
title: Управление удалённым Docker
status: stable
translation_key: guides.docker
source_revision: "2026-07-29"
---

# Управление удалённым Docker

Docker-операции выполняются через SSH-подключение ноды и требуют доступный
Docker daemon на целевом хосте. Сначала проверьте ноду и получите список
контейнеров. Bulk-вызовы возвращают отдельные результаты; частичная ошибка не
откатывает успешные удалённые операции.

## Проверка перед изменением состояния

```bash
curl --fail-with-body \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v1/nodes/${NODE_ID}/docker/containers"
```

Используйте возвращённый ID контейнера в путях `/start`, `/stop`, `/restart`,
`/logs`, `/stats` и `/exec`. Для изменения состояния нужен ключ `read-write`:

```bash
curl --fail-with-body -X POST \
  "${NODE_NEXUS_URL}/api/v1/nodes/${NODE_ID}/docker/containers/${CONTAINER_ID}/exec" \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  -H 'Content-Type: application/json' \
  -d '{"command": "id", "timeout": 30}'
```

Идентификаторы, имена images и тайм-ауты валидируются до построения удалённой
команды. Тем не менее используйте SSH-учётную запись с минимальными правами и
считайте выполнение в контейнере привилегированным доступом. Bulk endpoints под
`/api/v1/docker/bulk/` могут завершиться частично; проверяйте каждый `results`.
