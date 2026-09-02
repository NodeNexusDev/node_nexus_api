---
title: Import and export configuration
status: stable
translation_key: guides.configuration-import-export
source_revision: "2026-09-02"
---

# Import and export configuration

Export nodes, commands, and scripts before a risky change. The export excludes
secrets, so restored nodes require credentials to be supplied again. Treat an
export as configuration data, review it before import, and verify the reported
created, updated, and skipped counts.

The envelope contains independent `format_version` and `application_version`
fields. Imports validate the format before writing anything and reject an
unknown major version with `422` (`UnsupportedConfigFormatError`). Only
`format_version` is accepted — an import payload with an old or unsupported
version (for example the legacy `version` field or a mismatched major) fails
with `422`.

## Dry-run mode

Add `"dry_run": true` to the import payload to preview what would be imported
without writing to the database. The response includes:

- `would_create` — lists of nodes, commands, and scripts that would be created
- `duplicates` — names of entities that already exist and would be skipped
- `errors` — validation errors (e.g., incompatible format version)

Request example:

```json
POST /api/v2/config/import
{
  "dry_run": true,
  "nodes": [
    {"name": "web-01", "host": "10.0.0.1", "port": 22, "connection_type": "ssh"}
  ]
}
```

Response example:

```json
{
  "dry_run": true,
  "would_create": {
    "nodes": [{"name": "web-01", "host": "10.0.0.1", "port": 22, "connection_type": "ssh"}],
    "commands": [],
    "scripts": []
  },
  "duplicates": [],
  "errors": []
}
```
