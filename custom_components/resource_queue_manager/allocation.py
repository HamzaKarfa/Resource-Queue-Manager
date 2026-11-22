"""Allocation traversal modes, independent of strategy, capacity and recurrence.

Strategy determines the order of waiting requests. Allocation determines
whether a capacity-blocked head stops granting or may be bypassed.
"""

DEFAULT_ALLOCATION_MODE = "strict"
ALLOCATION_MODES = frozenset({"strict", "backfill"})


def validate_allocation_mode(mode: object) -> str:
    """Reject unsupported or malformed allocation mode values, including storage."""
    if type(mode) is not str or mode not in ALLOCATION_MODES:
        raise ValueError(f"Unknown allocation mode: {mode!r}")
    return mode
