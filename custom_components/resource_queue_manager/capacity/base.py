"""Pure-Python contracts for pluggable capacity policies.

The engine owns request order and state. A capacity policy resolves each
request's immutable unit cost and decides if the next request can be granted.
Units are generic integers, not necessarily electrical power.
"""

from collections.abc import Mapping, Sequence
from typing import Protocol


class CapacityPolicy(Protocol):
    """Evaluate capacity independently of FIFO/LIFO/priority ordering."""

    key: str

    def resolve_request_units(
        self, *,
        engine_data: Mapping[str, object] | None,
        default_units: int,
        capacity: int,
    ) -> int:
        """Validate a new/duplicate request and resolve its effective cost."""

    def can_allocate(
        self, *,
        active_units: Sequence[int],
        candidate_units: int,
        capacity: int,
    ) -> bool:
        """Return whether the next queued request fits the active budget."""

    def validate_limit(
        self, *,
        active_units: Sequence[int],
        waiting_units: Sequence[int],
        capacity: int,
    ) -> None:
        """Reject a limit that cannot honor active and queued requests."""

    def validate_restored(
        self, *,
        active_units: Sequence[int],
        waiting_units: Sequence[int],
        capacity: int,
    ) -> None:
        """Reject an inconsistent persisted queue, raising ValueError."""


class CapacityProvider(Protocol):
    """A registered provider creates a fresh capacity policy per queue."""

    key: str
    label: str
    description: str

    def create(self) -> CapacityPolicy:
        """Build an isolated policy, without Home Assistant imports."""
