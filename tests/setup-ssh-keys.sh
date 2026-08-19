#!/bin/sh
# Generate test SSH key pairs for e2e tests.
# Run this before docker-compose up so the volume mount has keys.
set -e

KEYS_DIR="${1:-tests/ssh-keys}"
mkdir -p "$KEYS_DIR"

if [ ! -f "$KEYS_DIR/test-key" ]; then
    ssh-keygen -t ed25519 -f "$KEYS_DIR/test-key" -N "" -C "e2e-unencrypted"
fi
if [ ! -f "$KEYS_DIR/test-key-enc" ]; then
    ssh-keygen -t ed25519 -f "$KEYS_DIR/test-key-enc" -N "keypass123" -C "e2e-encrypted"
fi

chmod 644 "$KEYS_DIR"/test-key "$KEYS_DIR"/test-key-enc
chmod 644 "$KEYS_DIR"/test-key.pub "$KEYS_DIR"/test-key-enc.pub
