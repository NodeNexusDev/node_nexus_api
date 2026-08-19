---
title: Регистрация первой ноды
status: stable
translation_key: getting-started.first-node
source_revision: "2026-07-29"
---

# Регистрация первой ноды

После запуска API создайте ноду:

```bash
curl -X POST http://localhost:8000/api/v1/nodes/ \
  -H 'Content-Type: application/json' \
  -H 'X-API-Key: your-master-key' \
  -d '{"name":"server-1","host":"192.0.2.10","port":22,"username":"ops","password":"change-me","connection_type":"ssh"}'
```

В реальной среде не оставляйте учётные данные в истории shell. Используйте
полученный `id` в endpoint проверки подключения, описанном в Swagger UI
по адресу `/docs`.

!!! tip "Аутентификация по SSH-ключу"
    Вместо пароля можно передать `"ssh_key": "<приватный-ключ>"` и
    опционально `"passphrase": "<пароль>"` для зашифрованных ключей.
    Подробнее: [руководство по нодам](../guides/nodes.md#ssh-).
