---
title: Backup and restore
status: stable
translation_key: operations.backup-and-restore
source_revision: "2026-07-30"
---

# Backup and restore

Database backup is the authoritative disaster-recovery artifact. The API
configuration export is portable but excludes credentials and is not a database
backup. Encrypt backups, restrict access, define retention, and test restoration
regularly. After restore, run migrations, verify `/ready`, and test one node
before reopening traffic.
