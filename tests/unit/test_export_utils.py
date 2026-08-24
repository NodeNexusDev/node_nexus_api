"""Tests for audit export utility functions."""

import csv
import io

from app.application.dto.export import AuditExportRowDTO
from app.application.export_utils import rows_to_csv, rows_to_json


def _row(**changes: object) -> AuditExportRowDTO:
    values = {
        "id": "abc-123",
        "action": "node.create",
        "node_id": "node-456",
        "user": "admin",
        "details": '{"name": "web-1"}',
        "created_at": "2026-01-15T10:30:00Z",
        **changes,
    }
    return AuditExportRowDTO(**values)  # type: ignore[arg-type]


class TestRowsToCsv:
    def test_empty_returns_empty_string(self) -> None:
        assert rows_to_csv([]) == ""

    def test_single_row(self) -> None:
        result = rows_to_csv([_row()])
        reader = csv.reader(io.StringIO(result))
        rows = list(reader)
        assert rows[0] == ["id", "action", "node_id", "user", "details", "created_at"]
        assert rows[1] == [
            "abc-123",
            "node.create",
            "node-456",
            "admin",
            '{"name": "web-1"}',
            "2026-01-15T10:30:00Z",
        ]

    def test_multiple_rows(self) -> None:
        result = rows_to_csv([_row(), _row(id="def-456", action="node.delete")])
        reader = csv.reader(io.StringIO(result))
        rows = list(reader)
        assert len(rows) == 3  # header + 2 data rows

    def test_special_characters_escaped(self) -> None:
        result = rows_to_csv([_row(details="has,comma")])
        reader = csv.reader(io.StringIO(result))
        rows = list(reader)
        assert rows[1][4] == "has,comma"

    def test_quotes_in_data(self) -> None:
        result = rows_to_csv([_row(details='has"quote')])
        reader = csv.reader(io.StringIO(result))
        rows = list(reader)
        assert rows[1][4] == 'has"quote'

    def test_none_fields_rendered_as_empty(self) -> None:
        result = rows_to_csv([_row(node_id=None, user=None)])
        reader = csv.reader(io.StringIO(result))
        rows = list(reader)
        assert rows[1][2] == ""
        assert rows[1][3] == ""


class TestRowsToJson:
    def test_empty_returns_empty_list(self) -> None:
        assert rows_to_json([]) == []

    def test_single_row(self) -> None:
        result = rows_to_json([_row()])
        assert len(result) == 1
        assert result[0]["id"] == "abc-123"
        assert result[0]["action"] == "node.create"
        assert result[0]["node_id"] == "node-456"
        assert result[0]["user"] == "admin"
        assert result[0]["details"] == '{"name": "web-1"}'
        assert result[0]["created_at"] == "2026-01-15T10:30:00Z"

    def test_multiple_rows(self) -> None:
        result = rows_to_json([_row(), _row(id="def-456")])
        assert len(result) == 2
        assert result[0]["id"] == "abc-123"
        assert result[1]["id"] == "def-456"

    def test_none_fields_preserved(self) -> None:
        result = rows_to_json([_row(node_id=None, user=None)])
        assert result[0]["node_id"] is None
        assert result[0]["user"] is None
