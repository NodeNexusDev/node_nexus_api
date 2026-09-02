---
title: WebSocket streaming команд
status: stable
translation_key: guides.websocket
source_revision: "2026-07-29"
---

# WebSocket streaming команд

Подключитесь к `WS /api/v2/nodes/{node_id}/exec-stream` с `X-API-Key`.
Legacy-вариант `?token=` deprecated, поскольку URL может попасть в логи.
Managed key должен иметь scope `read-write`; master key обрабатывается так же,
как в HTTP.

Запустите команду frame:
`{"version":"1","type":"command","command":"uname -a"}`. Сервер раздельно
передаёт `stdout` и `stderr`, затем отправляет
`{"version":"1","type":"exit","exit_code":0}` с реальным remote status.
Frame `{"version":"1","type":"signal","signal":"SIGINT"}` передаёт сигнал
активному процессу; разрешены `SIGINT`, `SIGTERM` и `SIGHUP`. `signal_ack`
означает успешную передачу. Размер frames ограничен, одновременно выполняется
одна команда, а disconnect отменяет и закрывает remote process.

OpenAPI не описывает WebSocket frames; до появления AsyncAPI эта страница
является нормативным протокольным пояснением.
