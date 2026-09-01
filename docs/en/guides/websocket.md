---
title: WebSocket command streaming
status: stable
translation_key: guides.websocket
source_revision: "2026-07-29"
---

# WebSocket command streaming

Connect to `WS /api/v2/nodes/{node_id}/exec-stream` with `X-API-Key`. The
legacy `?token=` form is deprecated because URLs can be logged. Managed keys
need `read-write` scope; the master key follows the same policy as HTTP.

Start a command with
`{"version":"1","type":"command","command":"uname -a"}`. The server emits
separate `stdout` and `stderr` frames and finishes with
`{"version":"1","type":"exit","exit_code":0}` using the real remote status.
Send `{"version":"1","type":"signal","signal":"SIGINT"}` for an active
process; only `SIGINT`, `SIGTERM`, and `SIGHUP` are accepted. A `signal_ack`
means the signal was forwarded. Frames are bounded, only one command may run
per connection, and disconnect cancels and closes the remote process.

OpenAPI does not describe WebSocket frames; this page is the normative protocol
note until an AsyncAPI contract is introduced.
