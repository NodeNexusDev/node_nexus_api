---
title: Переиспользуемые команды
status: stable
translation_key: guides.commands
source_revision: "2026-08-12"
---

# Переиспользуемые команды

Шаблоны команд задают именованные параметры и поддерживают теги. Создайте
шаблон, выполните его на ноде со значениями параметров и проверьте exit code,
stdout и stderr. Параметры валидируются до удалённого выполнения; не собирайте
недоверенные shell-фрагменты за пределами модели шаблонов.

## Создание и выполнение шаблона

```bash
curl --fail-with-body -X POST "${NODE_NEXUS_URL}/api/v2/commands/" \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  -H 'Content-Type: application/json' \
  -d '{
    "name": "disk-usage",
    "command": "df -h {{ mount }}",
    "parameters": [{
      "name": "mount",
      "type": "string",
      "required": true,
      "description": "Absolute mount path"
    }],
    "tags": ["diagnostics"]
  }'
```

Сохраните UUID и выполните шаблон:

```bash
curl --fail-with-body -X POST \
  "${NODE_NEXUS_URL}/api/v2/commands/${COMMAND_ID}/execute" \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  -H 'Content-Type: application/json' \
  -d "{\"node_id\": \"${NODE_ID}\", \"params\": {\"mount\": \"/\"}}"
```

Код `exit_code: 0` означает успех. Сохраняйте `stderr`: утилиты могут записывать
туда предупреждения. Поддерживаются параметры `string`, `integer` и `boolean`;
отсутствие обязательного значения приводит к ошибке до SSH-выполнения.

## Поиск команд

Добавьте параметр `search` для фильтрации по имени или описанию:

```bash
curl --fail-with-body --get \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  --data-urlencode 'search=disk' \
  "${NODE_NEXUS_URL}/api/v2/commands/"
```

Поиск выполняется по полям `name` и `description` с помощью case-insensitive
сопоставления (ILIKE). Ответ возвращает только те шаблоны, у которых имя или
описание содержат подстроку поиска.

## Глобальный список тегов команд

```bash
curl --fail-with-body \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v2/commands/tags"
```

Возвращает отсортированный список уникальных тегов, используемых во всех
шаблонах команд. Подходит для построения автокомплита и фильтров в UI.
