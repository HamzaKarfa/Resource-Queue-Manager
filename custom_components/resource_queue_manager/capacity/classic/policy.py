"""Classic capacity, one slot consumed by each active reservation."""

from collections.abc import Mapping, Sequence


class ClassicCapacityPolicy:
    """Mirror v1.0 allocation and strict restoration semantics."""

    key = "classic"

    def resolve_request_units(
        self, *,
        engine_data: Mapping[str, object] | None,
        default_units: int,
        capacity: int,
    ) -> int:
        if engine_data is not None and (
            not isinstance(engine_data, Mapping) or engine_data
        ):
            raise ValueError("Classic capacity does not accept engine_data")
        return 1

    def can_allocate(
        self, *,
        active_units: Sequence[int],
        candidate_units: int,
        capacity: int,
    ) -> bool:
        """Classic requests consume one slot."""
        return len(active_units) < capacity

    def validate_limit(
        self, *,
        active_units: Sequence[int],
        waiting_units: Sequence[int],
        capacity: int,
    ) -> None:
        if len(active_units) > capacity:
            raise ValueError("saved reservations exceed current limit")

    def validate_restored(
        self, *,
        active_units: Sequence[int],
        waiting_units: Sequence[int],
        capacity: int,
    ) -> None:
        """Preserve v1.0 invariants exactly, including no idle free slots."""
        self.validate_limit(
            active_units=active_units, waiting_units=waiting_units, capacity=capacity
        )
        if waiting_units and len(active_units) < capacity:
            raise ValueError("saved waiting queue has unallocated free slots")
