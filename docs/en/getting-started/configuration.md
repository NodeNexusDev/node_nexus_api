---
title: Initial configuration
status: stable
translation_key: getting-started.configuration
source_revision: "2026-07-29"
---

# Initial configuration

At minimum, set:

```dotenv
DATABASE_URL=postgresql+asyncpg://node_nexus:change-me@db:5432/node_nexus
ENVIRONMENT=production
SECRET_KEY=replace-with-at-least-32-random-characters
ENCRYPTION_SALT=replace-with-at-least-16-random-characters
MASTER_API_KEY=replace-with-at-least-32-random-characters
```

`SECRET_KEY` protects stored SSH credentials. Changing it makes existing
encrypted values unreadable. Production startup rejects shorter secrets. The
complete, code-aligned list is in the
[configuration reference](../reference/configuration.md).
