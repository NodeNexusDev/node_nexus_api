---
title: Совместимость и поддержка
status: stable
translation_key: reference.compatibility
source_revision: "2026-08-11"
---

# Совместимость и поддержка

Проект следует Semantic Versioning. Prefix `/api/v1` обозначает текущий major
HTTP contract; minor versions могут добавлять поля и endpoints. Удаление или
изменение обязательных полей, смысла, paths или status semantics является
breaking change и требует contract review и стратегии major version.

Поддерживаются Python 3.13 и PostgreSQL. Client generators должны использовать
OpenAPI artifact конкретного release.

## Версионирование API

API поддерживает версионирование через заголовок `X-API-Version`. Версия по
умолчанию — `1`. Неподдерживаемые версии возвращают `400 Bad Request`. Endpoints
health, readiness и metrics исключены из проверки версии.

## Changelog

| Версия | Дата | Тип | Основные изменения |
|--------|------|-----|--------------------|
| 0.8.0 | 2026-08-11 | Minor | Docker create/сборка image, bulk по тегам, детальный readiness, request id в ошибках, версионирование API |
| 0.7.1 | 2026-07-30 | Patch | Исправления документации |
| 0.7.0 | 2026-07-29 | Minor |
| 0.6.4 | 2026-07-29 | Patch |
| 0.6.3 | 2026-07-29 | Patch |
| 0.6.2 | 2026-07-28 | Patch |
| 0.6.1 | 2026-07-26 | Patch |
| 0.6.0 | 2026-07-26 | Minor |
| 0.5.0 | 2026-07-26 | Minor |
| 0.4.0 | 2026-07-25 | Minor |
| 0.3.0 | 2026-07-25 | Minor |
| 0.2.1 | 2026-07-19 | Patch |
| 0.2.0 | 2026-07-19 | Minor |
| 0.1.0 | 2026-07-15 | Minor |
| 0.0.1 | 2026-07-15 | Initial |
