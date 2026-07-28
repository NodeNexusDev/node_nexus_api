---
title: Deployment and rollback
status: stable
translation_key: operations.deployment
source_revision: "2026-07-29"
---

# Deployment and rollback

1. Back up the database and configuration export.
2. Build an immutable image and inspect its dependency audit.
3. Apply migrations as a separate deployment step with `AUTO_MIGRATE=false`.
4. Start one instance, wait for `/ready`, then shift traffic.
5. Roll out remaining API replicas.

Run only one scheduler-enabled process because schedules are in-memory and lack
distributed coordination. For rollback, confirm that the previous application
version supports the migrated schema before changing traffic.
