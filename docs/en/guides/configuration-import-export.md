---
title: Import and export configuration
status: stable
translation_key: guides.configuration-import-export
source_revision: "2026-07-29"
---

# Import and export configuration

Export nodes, commands, and scripts before a risky change. The export excludes
secrets, so restored nodes require credentials to be supplied again. Treat an
export as configuration data, review it before import, and verify the reported
created, updated, and skipped counts.
