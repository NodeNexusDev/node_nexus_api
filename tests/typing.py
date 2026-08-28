"""Typed boundaries for dynamic test doubles."""

from typing import cast


def as_typed_mock[T](_expected_type: type[T], value: object) -> T:
    """Declare the contract implemented by a dynamically configured test double."""

    return cast(T, value)


def as_typed[T](value: object) -> T:
    """Adapt a structurally compatible fake to the type required by a test subject."""

    return cast(T, value)


def as_unvalidated[T](_expected_type: object, value: object) -> T:
    """Pass malformed external input to runtime validation without an ignore."""

    return cast(T, value)
