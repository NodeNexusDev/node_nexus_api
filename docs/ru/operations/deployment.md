---
title: Развёртывание и откат
status: stable
translation_key: operations.deployment
source_revision: "2026-09-02"
---

# Развёртывание и откат

## Требования к production

- Завершайте TLS на доверенном reverse proxy и публикуйте только порт API.
- Размещайте PostgreSQL и telemetry receivers в закрытых сетях.
- Храните переменные окружения в хранилище секретов платформы
  (`DATABASE_URL`, `SECRET_KEY` 32 символа, `ENCRYPTION_SALT` 16 символов,
  `MASTER_API_KEY` 32 символа, `REQUEST_TIMEOUT`, `PROMETHEUS_ENABLED`,
  `PROMETHEUS_PATH`, `SCHEDULER_ENABLED`, `AUTO_MIGRATE` и т.д. — см.
  `.env.example` и `app/core/config.py`).
- Создайте независимые случайные `SECRET_KEY` и `MASTER_API_KEY`.
- Подключите постоянное хранилище PostgreSQL и проверьте резервные копии.
- Установите `AUTO_MIGRATE=false`, если миграциями управляет release process.

Compose-файл подходит как основа, но примерные учётные данные БД и опубликованный порт
PostgreSQL нельзя считать безопасными production-настройками. Compose-проекты
(`compose_projects`) и реестры/паки/ассеты/установки шаблонов — опциональные
возможности 2.0, они не требуются для базового развёртывания и могут быть
включены позже.

## Последовательность выпуска

1. Зафиксируйте версию приложения и текущую ревизию Alembic.
2. Создайте резервную копию PostgreSQL и экспорт конфигурации.
3. Соберите неизменяемый image из проверенного коммита и проверьте зависимости.
4. Выполните `uv run alembic upgrade head` одной контролируемой задачей.
5. Запустите один экземпляр и дождитесь успеха `/health` и `/ready`.
6. Smoke-проверка с cursor-пагинацией и API-ключом:

   ```bash
   curl --fail-with-body \
     -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
     "${NODE_NEXUS_URL}/api/v2/nodes/?cursor=&limit=1"
   ```

7. Переключайте трафик постепенно, наблюдая за ошибками, тайм-аутами и БД.

Оставьте `SCHEDULER_ENABLED=true` на репликах, которые могут выполнять jobs.
Расписания сохраняются в PostgreSQL, а advisory lock выбирает одного owner.
Schedule API доступен на каждой реплике, но jobs запускает только owner.
Смонтируйте проверенный OpenSSH `known_hosts` по `SSH_KNOWN_HOSTS_PATH`; не
отключайте строгую проверку host key в production.

## Откат

До возврата трафика на предыдущий image убедитесь, что он поддерживает
обновлённую схему. Не выполняйте `alembic downgrade`, пока не оценён риск потери
данных и не создана свежая резервная копия. После отката проверьте `/ready`,
повторите аутентифицированный smoke-запрос
(`GET /api/v2/nodes/?cursor=&limit=1` с `X-API-Key`) и зафиксируйте проблемную
версию, ревизию миграции и наблюдаемые симптомы.
