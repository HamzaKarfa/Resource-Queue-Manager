"""Pluggable duplicate-request handling, independent from scheduling and capacity."""

from .registry import (
    DEFAULT_RECURRENCE_MODE,
    RECURRENCE_PROVIDERS,
    get_recurrence_policy,
)

__all__ = [
    "DEFAULT_RECURRENCE_MODE",
    "RECURRENCE_PROVIDERS",
    "get_recurrence_policy",
]
