"""Tests for model default values."""

from app.models.node import _default_port, _default_status
from app.models.script_execution import _default_status as _default_exec_status


def test_node_default_port_function() -> None:
    assert _default_port() == 22


def test_node_default_status_function() -> None:
    assert _default_status() == "active"


def test_script_execution_default_status_function() -> None:
    assert _default_exec_status() == "pending"
