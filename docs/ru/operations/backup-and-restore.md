---
title: Резервное копирование и восстановление
status: stable
translation_key: operations.backup-and-restore
source_revision: "2026-07-29"
---

# Резервное копирование и восстановление

Backup БД — основной disaster-recovery artifact. Экспорт конфигурации переносим,
но не содержит credentials и не заменяет backup БД. Шифруйте backups,
ограничивайте доступ, задайте retention и регулярно проверяйте восстановление.
После restore примените миграции, проверьте `/ready` и одну ноду.
