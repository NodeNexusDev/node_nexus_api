"""Shared DAO utilities."""


def escape_ilike(value: str) -> str:
    """Escape special ILIKE characters (%, _) for safe pattern matching."""
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
