.PHONY: help
help:
	@echo "Available targets:"
	@echo "  e2e-smoke       - fast E2E smoke suite (< 2 min)"
	@echo "  e2e-docker      - Docker API/ops E2E tests"
	@echo "  e2e-scheduler   - scheduler execution and failover tests"
	@echo "  e2e-resilience  - restart/network failure tests"
	@echo "  e2e-migration   - Alembic migration path tests"
	@echo "  e2e-full        - all non-nightly E2E tests"
	@echo "  e2e-nightly     - resilience + migration + slow tests"
	@echo "  e2e-keep-stack  - run smoke suite and keep Docker stack up"
	@echo "  e2e-down        - tear down the E2E Docker stack"
	@echo "  update-e2e-coverage - sync COVERED_ENDPOINTS from openapi.json (no Docker)"

PYTEST := .venv/bin/python -m pytest
E2E_DIR := tests/e2e
COMPOSE_FILE := tests/docker-compose.e2e.yml
SSH_KEYS_DIR := tests/ssh-keys

.PHONY: setup-ssh-keys
setup-ssh-keys:
	@sh tests/setup-ssh-keys.sh $(SSH_KEYS_DIR)

.PHONY: e2e-smoke
e2e-smoke: setup-ssh-keys
	$(PYTEST) $(E2E_DIR) -m e2e_smoke -q

.PHONY: e2e-docker
e2e-docker: setup-ssh-keys
	$(PYTEST) $(E2E_DIR) -m docker -q

.PHONY: e2e-scheduler
e2e-scheduler: setup-ssh-keys
	$(PYTEST) $(E2E_DIR) -m e2e_scheduler -q

.PHONY: e2e-resilience
e2e-resilience: setup-ssh-keys
	$(PYTEST) $(E2E_DIR) -m e2e_resilience -q

.PHONY: e2e-migration
e2e-migration: setup-ssh-keys
	$(PYTEST) $(E2E_DIR) -m e2e_migration -q

.PHONY: e2e-full
e2e-full: setup-ssh-keys
	$(PYTEST) $(E2E_DIR) -m "docker and not (e2e_resilience or e2e_migration or e2e_slow)" -q

.PHONY: e2e-nightly
e2e-nightly: setup-ssh-keys
	$(PYTEST) $(E2E_DIR) -m "docker and (e2e_resilience or e2e_migration or e2e_slow)" -q

.PHONY: e2e-keep-stack
e2e-keep-stack: setup-ssh-keys
	$(PYTEST) $(E2E_DIR) -m e2e_smoke -q --keep-stack

.PHONY: e2e-down
e2e-down:
	docker compose -f $(COMPOSE_FILE) down -v --remove-orphans
	rm -rf $(SSH_KEYS_DIR)

.PHONY: generate-openapi
generate-openapi:
	uv run python scripts/generate_openapi_snapshot.py

.PHONY: update-e2e-coverage
update-e2e-coverage:
	uv run python scripts/update_e2e_coverage.py

.PHONY: e2e-fast
e2e-fast: setup-ssh-keys
	$(PYTEST) $(E2E_DIR) -m "e2e_smoke and not docker" -q

.PHONY: e2e-docker-ops
e2e-docker-ops: setup-ssh-keys
	$(PYTEST) $(E2E_DIR)/test_docker_ops_e2e.py -q

.PHONY: check
check:
	uv run ruff check app/ tests/
	uv run ty check .
	uv run pytest tests/e2e/test_endpoint_coverage_e2e.py -q
