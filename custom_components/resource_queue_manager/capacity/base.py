"""Pure-Python contracts for pluggable capacity policies.

The engine owns request order and state. A policy only decides whether
an ordered request fits and validates restored capacity invariants.
Values are generic integer units, not necessarily electrical power.
"""

from collections.abc import Sequence
from typing import Protocol


class CapacityPolicy(Protocol):
    """Evaluate capacity independently of FIFO/LIFO/priority ordering."""

    key: str

    def can_allocate(
        self,
        *,
        active_units: Sequence[int],
        candidate_units: int,
        capacity: int,
    ) -> bool:
        """Return whether the next queued request fits the active budget."""

    def validate_restored(
        self,
        *,
        active_units: Sequence[int],
        waiting_units: Sequence[int],
        capacity: int,
    ) -> None:
        """Reject invalid persisted capacity states, raising ValueError."""


class CapacityProvider(Protocol):
    """A registered provider creates a fresh capacity policy per queue."""

    key: str
    label: str
    description: str

    def create(self) -> CapacityPolicy:
        """Build an isolated policy, without Home Assistant imports."""
