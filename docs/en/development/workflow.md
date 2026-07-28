---
title: Development workflow
status: stable
translation_key: development.workflow
source_revision: "2026-07-29"
---

# Development workflow

Create a `feature/`, `fix/`, `refactor/`, or `docs/` branch from `dev`. Use
Conventional Commits, validate locally, and merge the reviewed branch into
`dev`. Feature branches are local and are not pushed; only `dev` and `main` are
pushed. Never change `.gitignore` without explicit approval.
