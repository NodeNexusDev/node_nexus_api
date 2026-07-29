"""Pure policies for safe durable audit payloads."""

from app.application.types import JsonObject

_SENSITIVE_DETAIL_KEYS = {
    "password",
    "ssh_key",
    "token",
    "api_key",
    "authorization",
    "command",
    "params",
    "stdout",
    "stderr",
}


def sanitize_audit_details(details: JsonObject) -> JsonObject:
    """Remove credential and command payloads from durable audit details."""
    return {
        key: value
        for key, value in details.items()
        if key.lower() not in _SENSITIVE_DETAIL_KEYS
    }
