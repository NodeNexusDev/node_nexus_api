from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

type AuditExportFormat = Literal["csv", "json"]


@dataclass(frozen=True, slots=True)
class AuditExportQueryDTO:
    date_from: datetime | None = None
    date_to: datetime | None = None
    action: str | None = None
    node_id: uuid.UUID | None = None
    fmt: AuditExportFormat = "csv"


@dataclass(frozen=True, slots=True)
class AuditExportRowDTO:
    id: str
    action: str
    node_id: str | None
    user: str | None
    details: str | None
    created_at: str
