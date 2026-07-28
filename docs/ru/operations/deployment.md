---
title: Развёртывание и откат
status: stable
translation_key: operations.deployment
source_revision: "2026-07-29"
---

# Развёртывание и откат

1. Создайте backup БД и экспорт конфигурации.
2. Соберите immutable image и проверьте dependency audit.
3. Примените миграции отдельно с `AUTO_MIGRATE=false`.
4. Запустите один instance, дождитесь `/ready`, затем переключите трафик.
5. Разверните остальные API replicas.

Запускайте только один scheduler-enabled process: расписания находятся в памяти
и не имеют распределённой координации. Перед rollback убедитесь, что предыдущая
версия приложения поддерживает обновлённую схему БД.
