---
title: Документация и перевод
status: stable
translation_key: development.documentation
source_revision: "2026-09-02"
---

# Документация и перевод

Каждая актуальная страница имеет English и Russian версии с одинаковым
относительным путём. Английский язык задаёт канонические identifiers и
terminology; Russian содержит полный, идиоматичный перевод — не дословную кальку. Не переводите class names, paths,
parameters, environment variables, error names и commands.

Используйте task-oriented заголовки, проверенные команды, относительные ссылки
и admonitions для опасных действий. Security и migration изменения требуют синхронного перевода.

## Требование к `source_revision`

Обе страницы `docs/en/...` и `docs/ru/...` связаны одним `translation_key`. При изменении английской версии **обязательно** обновите `source_revision` в **обоих** файлах (например, на `2026-09-02`) и синхронизируйте русский перевод в том же коммите. Не оставляйте `source_revision` устаревшим — он сигнализирует о рассинхронизации перевода.

## Редакционный стандарт

- Начинайте с цели пользователя, предварительных условий и проверяемого результата.
- Сверяйте пути, поля, значения по умолчанию, статусы и ограничения с кодом или
  сгенерированным OpenAPI-контрактом (`openapi.json` / `scripts/openapi.snapshot.json`).
- Приводите полные команды, пригодные для копирования, и явно отмечайте placeholders.
- Объясняйте необратимые, разрушительные и чувствительные к безопасности
  последствия до соответствующей команды.
- Не изменяйте identifiers, enum values, headers и environment variables.
- Не описывайте запланированное поведение как уже реализованное.

Английский — канон: прямые предложения и активный залог. Русский должен быть естественным, а не дословным переводом английского.
После изменения таблиц, admonitions и длинных code blocks просмотрите обе
собранные страницы.

## Сборка

Проверяйте документацию перед ревью строгой сборкой:

```bash
uv run mkdocs build --strict -f mkdocs.en.yml
uv run mkdocs build --strict -f mkdocs.ru.yml
uv run python scripts/docs/check_docs.py
```

Флаг `--strict` падает на любом warning (битые ссылки, отсутствующие страницы). Исправьте все warnings до мержа. Guard покрытия `tests/e2e/test_endpoint_coverage_e2e.py` (с `branch=true`, `fail_under=95`) и `scripts/openapi.snapshot.json` (кеш, игнорируется в git) не связаны со сборкой docs напрямую, но должны оставаться синхронизированными при изменении endpoints — запускайте `make generate-openapi` и `make update-e2e-coverage`.

Новые ADR содержат разделы `Context`, `Decision`, `Alternatives considered` и
`Consequences`. Заменённое решение ссылается на новый ADR и получает статус
`superseded`.
