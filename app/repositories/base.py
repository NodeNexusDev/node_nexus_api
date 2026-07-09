"""Base repository interface."""

from abc import ABC, abstractmethod
from typing import Generic, TypeVar
from uuid import UUID

ModelType = TypeVar("ModelType")


class IRepository(ABC, Generic[ModelType]):
    """Abstract base repository interface."""

    @abstractmethod
    async def get_by_id(self, id: UUID) -> ModelType | None:
        """Get a record by ID."""

    @abstractmethod
    async def get_all(self, skip: int = 0, limit: int = 100) -> list[ModelType]:
        """Get all records with pagination."""

    @abstractmethod
    async def create(self, data: dict) -> ModelType:
        """Create a new record."""

    @abstractmethod
    async def update(self, id: UUID, data: dict) -> ModelType | None:
        """Update an existing record."""

    @abstractmethod
    async def delete(self, id: UUID) -> bool:
        """Delete a record by ID."""
