---
title: Reusable commands
status: stable
translation_key: guides.commands
source_revision: "2026-07-29"
---

# Reusable commands

Command templates define named parameters and can be tagged. Create the
template, execute it against a node with parameter values, and inspect each
result's exit code, stdout, and stderr. Parameters are validated before remote
execution; never build an untrusted shell fragment outside the template model.
