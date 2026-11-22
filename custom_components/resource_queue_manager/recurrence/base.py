"""Pure-Python policy contract for repeated reservation requests."""

from typing import Protocol


class RecurrencePolicy(Protocol):
    """Determine the occurrence count of an identical duplicate request."""

    key: str

    def on_duplicate(self, *, pending: bool, occurrences: int) -> int:
        """Return a count; never change queue position or capacity."""


class RecurrenceProvider(Protocol):
    """Create one recurrence policy per queue (no dynamic user module loading)."""

    key: str
    label: str
    description: str

    def create(self) -> RecurrencePolicy:
        """Return an isolated recurrence policy."""
