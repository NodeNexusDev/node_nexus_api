---
title: Решение проблем
status: stable
translation_key: guides.troubleshooting
source_revision: "2026-07-29"
---

# Решение проблем

- `401`: проверьте `X-API-Key`, срок действия и статус отзыва.
- `403`: для изменения нужен read-write key.
- `503` для ноды: проверьте DNS, SSH port, credentials и host-key policy.
- `/ready` неуспешен: проверьте БД и миграции.
- расписание исчезло: оно хранится в памяти и не переживает restart.
- Docker-вызов упал: проверьте Docker и доступ SSH-пользователя к daemon.

Используйте request ID и структурированные логи, но не логируйте credentials.
