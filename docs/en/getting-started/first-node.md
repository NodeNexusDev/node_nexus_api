---
title: Register the first node
status: stable
translation_key: getting-started.first-node
source_revision: "2026-07-29"
---

# Register the first node

With the API running, create a node:

```bash
curl -X POST http://localhost:8000/api/v1/nodes/ \
  -H 'Content-Type: application/json' \
  -H 'X-API-Key: your-master-key' \
  -d '{"name":"server-1","host":"192.0.2.10","port":22,"username":"ops","password":"change-me","connection_type":"ssh"}'
```

Keep credentials out of shell history in real environments. Use the returned
`id` with the node connectivity endpoint shown in Swagger UI at `/docs`.
