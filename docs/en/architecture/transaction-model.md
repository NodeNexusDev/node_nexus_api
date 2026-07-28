---
title: Transaction model
status: stable
translation_key: architecture.transaction-model
source_revision: "2026-07-29"
---

# Transaction model

One request scope owns one async SQLAlchemy session. The service/use-case
boundary owns commit and rollback; repositories flush when an identifier is
needed but do not commit independently.

Short CRUD work happens in one transaction. Remote SSH and Docker operations
read required state, release database work, perform the side effect, then write
the result in a new short transaction when needed. Bulk operations report
partial outcomes and do not promise distributed rollback.
