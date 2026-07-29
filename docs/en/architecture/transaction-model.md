---
title: Transaction model
status: stable
translation_key: architecture.transaction-model
source_revision: "2026-07-30"
---

# Transaction model

Request CRUD uses one request-scoped SQLAlchemy session. The provider owns
commit and rollback; internal DAOs flush but do not commit independently.
APP-scoped gateways store an `async_sessionmaker`, never a live session.

Remote operations follow `short read -> immutable DTO -> close session ->
side effect -> short write`. Concurrent workers never receive a session, DAO,
or ORM model. Bulk operations report partial outcomes and do not promise
distributed rollback.

Multi-aggregate operations use dedicated boundaries only when atomicity is a
business requirement. Configuration import owns one transaction for the whole
payload; there is no universal application Unit of Work.
