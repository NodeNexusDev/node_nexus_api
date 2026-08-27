---
title: Начальная конфигурация
status: stable
translation_key: getting-started.configuration
source_revision: "2026-07-29"
---

# Начальная конфигурация

Минимально задайте:

```dotenv
DATABASE_URL=postgresql+asyncpg://node_nexus:change-me@db:5432/node_nexus
ENVIRONMENT=production
SECRET_KEY=replace-with-at-least-32-random-characters
ENCRYPTION_SALT=replace-with-at-least-16-random-characters
MASTER_API_KEY=replace-with-at-least-32-random-characters
```

`SECRET_KEY` защищает сохранённые SSH-учётные данные. После его замены ранее
зашифрованные значения нельзя прочитать. Production startup отклоняет secrets
короче указанных ограничений. Полный список, сверенный с кодом,
находится в [справочнике конфигурации](../reference/configuration.md).
