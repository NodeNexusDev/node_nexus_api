"""Shared E2E settings and constants.

Centralizes values that are duplicated across fixtures, helpers, and tests
so that environment-specific tweaks live in one place.
"""

import os

# Authentication
MASTER_API_KEY = os.getenv("E2E_MASTER_API_KEY", "e2e-master-key-12345")

# Default SSH node connection (matches the ssh-server service in Compose)
SSH_HOST = "ssh-server"
SSH_PORT = 2222
SSH_USERNAME = "testuser"
SSH_PASSWORD = "testpass"

# Docker-in-Docker endpoint exposed to Docker-capable nodes
DOCKER_HOST = "tcp://dind:2375"
DEFAULT_DOCKER_IMAGE = "alpine:latest"
DEFAULT_DOCKER_IMAGE_TAGGED = "alpine:3.20"

# HTTP client defaults
DEFAULT_TIMEOUT = 30.0
