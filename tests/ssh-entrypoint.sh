#!/bin/sh
# Entry wrapper: run the original LinuxServer init, then inject
# test SSH public keys into the testuser's authorized_keys.
set -e

# Run the original entrypoint (creates user, generates host keys, etc.)
/config/docker-init.sh

# Inject test public keys for e2e SSH key-based auth tests.
PUBKEYS="/config/ssh/test-keys"
AUTH_KEYS="/config/testuser/.ssh/authorized_keys"
if [ -d "$PUBKEYS" ] && [ -f "$AUTH_KEYS" ]; then
    for f in "$PUBKEYS"/*.pub; do
        [ -f "$f" ] || continue
        cat "$f" >> "$AUTH_KEYS"
    done
    chmod 600 "$AUTH_KEYS"
    chown 1000:1000 "$AUTH_KEYS"
fi

exec "$@"
