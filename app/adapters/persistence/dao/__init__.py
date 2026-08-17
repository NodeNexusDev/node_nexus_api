"""Internal SQLAlchemy data-access objects used by persistence adapters."""

from app.adapters.persistence.dao.base import escape_ilike

__all__ = ["escape_ilike"]
