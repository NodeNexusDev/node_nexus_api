---
title: Аутентификация
status: stable
translation_key: guides.authentication
source_revision: "2026-07-29"
---

# Аутентификация

Передавайте `X-API-Key` в каждом защищённом запросе. Master key всегда имеет
read-write доступ. Управляемые ключи имеют scope `read-only` или `read-write`,
могут истекать и показываются полностью только при создании.

```bash
curl -H 'X-API-Key: your-key' http://localhost:8000/api/v1/nodes/
```

Храните ключи в secret manager, ротируйте их и не помещайте в URL или логи.
