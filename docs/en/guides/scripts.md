---
title: Scripts and schedules
status: stable
translation_key: guides.scripts
source_revision: "2026-07-29"
---

# Scripts and schedules

A script is an ordered pipeline of inline commands and saved command templates.
Each step chooses `stop` or `continue` failure behavior. Execution can target
multiple nodes and produces per-node results.

Schedules are kept in process memory. They disappear on restart and are not
coordinated between replicas; use one scheduler process only.
