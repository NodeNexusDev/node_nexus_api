---
title: Authentication
status: stable
translation_key: guides.authentication
source_revision: "2026-07-29"
---

# Authentication

Send `X-API-Key` with every protected request. The master key always has
read-write access. Managed keys can be `read-only` or `read-write`, can expire,
and are shown in full only when created.

```bash
curl -H 'X-API-Key: your-key' http://localhost:8000/api/v1/nodes/
```

Store keys in a secret manager, rotate them, and never put them in URLs or logs.
