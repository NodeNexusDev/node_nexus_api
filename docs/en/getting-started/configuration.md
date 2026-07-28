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
SECRET_KEY=replace-with-a-random-secret
MASTER_API_KEY=replace-with-a-long-random-key
```

`SECRET_KEY` protects stored SSH credentials. Changing it makes existing
encrypted values unreadable. The complete, code-aligned list is in the
[configuration reference](../reference/configuration.md).
