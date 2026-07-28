---
title: WebSocket command streaming
status: stable
translation_key: guides.websocket
source_revision: "2026-07-29"
---

# WebSocket command streaming

Connect to `WS /api/v1/nodes/{node_id}/exec-stream` and pass the API key using
the protocol expected by the endpoint. Send a JSON command request. The server
emits output events followed by a terminal completion or error event. Clients
must handle disconnects and must not assume a command can be resumed.

OpenAPI does not describe WebSocket frames; this page is the normative protocol
note until an AsyncAPI contract is introduced.
