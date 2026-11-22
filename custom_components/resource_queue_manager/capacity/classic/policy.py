"""Classic capacity, one slot consumed by each active reservation."""

from collections.abc import Sequence


class ClassicCapacityPolicy:
    """Mirror v1.0 allocation and strict restoration semantics."""

    key = "classic"

    def can_allocate(
        self,
        *,
        active_units: Sequence[int],
        candidate_units: int,
        capacity: int,
    ) -> bool:
        """Classic requests consume one slot regardless of provided units."""
        return len(active_units) < capacity

    def validate_restored(
        self,
        *,
        active_units: Sequence[int],
        waiting_units: Sequence[int],
        capacity: int,
    ) -> None:
        """Preserve v1.0 invariants exactly, including no idle free slots."""
        if len(active_units) > capacity:
            raise ValueError("saved reservations exceed current limit")
        if waiting_units and len(active_units) < capacity:
            raise ValueError("saved waiting queue has unallocated free slots")
