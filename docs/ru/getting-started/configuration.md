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
SECRET_KEY=replace-with-a-random-secret
MASTER_API_KEY=replace-with-a-long-random-key
```

`SECRET_KEY` защищает сохранённые SSH-учётные данные. После его замены ранее
зашифрованные значения нельзя прочитать. Полный список, сверенный с кодом,
находится в [справочнике конфигурации](../reference/configuration.md).
