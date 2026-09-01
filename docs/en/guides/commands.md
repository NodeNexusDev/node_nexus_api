---
title: Reusable commands
status: stable
translation_key: guides.commands
source_revision: "2026-08-12"
---

# Reusable commands

Command templates define named parameters and can be tagged. Create the
template, execute it against a node with parameter values, and inspect each
result's exit code, stdout, and stderr. Parameters are validated before remote
execution; never build an untrusted shell fragment outside the template model.

## Create and execute a template

```bash
curl --fail-with-body -X POST "${NODE_NEXUS_URL}/api/v2/commands/" \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  -H 'Content-Type: application/json' \
  -d '{
    "name": "disk-usage",
    "command": "df -h {{ mount }}",
    "parameters": [{
      "name": "mount",
      "type": "string",
      "required": true,
      "description": "Absolute mount path"
    }],
    "tags": ["diagnostics"]
  }'
```

Save the returned UUID, then execute the template:

```bash
curl --fail-with-body -X POST \
  "${NODE_NEXUS_URL}/api/v2/commands/${COMMAND_ID}/execute" \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  -H 'Content-Type: application/json' \
  -d "{\"node_id\": \"${NODE_ID}\", \"params\": {\"mount\": \"/\"}}"
```

An `exit_code` of zero indicates success. Preserve `stderr` because utilities
can write warnings there. Parameters support `string`, `integer`, and `boolean`;
a missing required value fails before SSH execution.

## Search commands

Add the `search` query parameter to filter by name or description:

```bash
curl --fail-with-body --get \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  --data-urlencode 'search=disk' \
  "${NODE_NEXUS_URL}/api/v2/commands/"
```

Search matches against the `name` and `description` fields using
case-insensitive comparison (ILIKE). The response returns only templates whose
name or description contain the search substring.

## Global command tags

```bash
curl --fail-with-body \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v2/commands/tags"
```

Returns a sorted list of unique tags used across all command templates. Useful
for building autocomplete and filter UIs.
