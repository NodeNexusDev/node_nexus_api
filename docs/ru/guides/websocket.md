---
title: WebSocket streaming команд
status: stable
translation_key: guides.websocket
source_revision: "2026-07-29"
---

# WebSocket streaming команд

Подключитесь к `WS /api/v1/nodes/{node_id}/exec-stream` и передайте API key
способом, который ожидает endpoint. Отправьте JSON-запрос команды. Сервер
передаёт события вывода, затем финальное событие завершения или ошибки. Клиент
должен обрабатывать разрыв соединения и не считать команду возобновляемой.

OpenAPI не описывает WebSocket frames; до появления AsyncAPI эта страница
является нормативным протокольным пояснением.
