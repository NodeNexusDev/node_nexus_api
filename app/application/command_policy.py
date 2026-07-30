"""Pure command security policies."""

import hashlib


def command_fingerprint(command: str) -> str:
    """Return a stable non-reversible identifier for a command."""
    return hashlib.sha256(command.encode()).hexdigest()
