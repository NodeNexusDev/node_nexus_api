---
title: Совместимость и поддержка
status: stable
translation_key: reference.compatibility
source_revision: "2026-07-29"
---

# Совместимость и поддержка

Проект следует Semantic Versioning. Prefix `/api/v1` обозначает текущий major
HTTP contract; minor versions могут добавлять поля и endpoints. Удаление или
изменение обязательных полей, смысла, paths или status semantics является
breaking change и требует contract review и стратегии major version.

Поддерживаются Python 3.13 и PostgreSQL. Client generators должны использовать
OpenAPI artifact конкретного release.
