"""Explicit registry for duplicate-request policies."""

from .base import RecurrencePolicy, RecurrenceProvider
from .count import CountRecurrenceProvider
from .ignore import IgnoreRecurrenceProvider

DEFAULT_RECURRENCE_MODE = "ignore"

RECURRENCE_PROVIDERS: dict[str, RecurrenceProvider] = {
    "ignore": IgnoreRecurrenceProvider(),
    "count": CountRecurrenceProvider(),
}


def get_recurrence_policy(key: str = DEFAULT_RECURRENCE_MODE) -> RecurrencePolicy:
    """Return a fresh policy for the selected mode, or fail closed."""
    try:
        return RECURRENCE_PROVIDERS[key].create()
    except (KeyError, TypeError) as err:
        raise ValueError(f"Unsupported recurrence mode: {key!r}") from err
