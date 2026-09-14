"""Tests for canonical pagination helpers in app.api.pagination."""

from __future__ import annotations

import pytest
from fastapi import HTTPException

import app.api.v2._bulk as bulk_module
import app.api.v2._shared as shared_module
from app.api import pagination
from app.api.pagination import (
    cursor_next,
    encode_offset,
    pagination_params,
    parse_cursor_offset,
)


def test_parse_none_and_empty_return_zero():
    assert parse_cursor_offset(None) == 0
    assert parse_cursor_offset("") == 0


def test_parse_valid_roundtrip():
    assert parse_cursor_offset(encode_offset(7)) == 7


def test_parse_invalid_raises_422():
    with pytest.raises(HTTPException) as exc:
        parse_cursor_offset("not-a-cursor!!!")
    assert exc.value.status_code == 422
    assert exc.value.detail == "Invalid cursor"


def test_parse_invalid_via_shared_reexport_raises_422():
    with pytest.raises(HTTPException) as exc:
        shared_module.parse_cursor_offset("not-a-cursor!!!")
    assert exc.value.status_code == 422


def test_pagination_params_values():
    assert pagination_params(0, 20) == (1, 20, 0)
    assert pagination_params(25, 10) == (3, 15, 5)
    assert pagination_params(10, 10) == (2, 10, 0)


def test_cursor_next_has_more_and_end():
    nxt, has_more = cursor_next(0, 2, 5, 2)
    assert has_more is True
    assert nxt == encode_offset(2)
    nxt_end, has_more_end = cursor_next(4, 2, 5, 1)
    assert has_more_end is False
    assert nxt_end is None


def test_shared_reexports_are_canonical():
    assert shared_module.parse_cursor_offset is pagination.parse_cursor_offset
    assert shared_module.pagination_params is pagination.pagination_params
    assert shared_module.cursor_next is pagination.cursor_next


def test_bulk_duplicates_removed():
    assert not hasattr(bulk_module, "pagination_offset_params")
    assert not hasattr(bulk_module, "pagination_cursor_next")


@pytest.mark.parametrize(
    ("items", "cursor", "limit"),
    [
        (list(range(10)), None, 3),
        (list(range(10)), "", 3),
        (list(range(10)), encode_offset(0), 4),
        (list(range(10)), encode_offset(3), 4),
        (list(range(10)), encode_offset(8), 5),
        (list(range(10)), encode_offset(10), 5),
        (list(range(3)), encode_offset(1), 10),
        ([], None, 5),
    ],
)
def test_manual_composition_slices(items, cursor, limit):
    offset = parse_cursor_offset(cursor)
    sliced = items[offset : offset + limit]
    next_cursor, has_more = cursor_next(offset, limit, len(items), len(sliced))
    assert sliced == items[offset : offset + limit]
    assert has_more == ((offset + len(sliced)) < len(items))
    if has_more:
        assert next_cursor == encode_offset(offset + limit)
    else:
        assert next_cursor is None
