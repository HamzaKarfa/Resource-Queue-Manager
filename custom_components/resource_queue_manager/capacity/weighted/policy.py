"""Strict weighted capacity accounting, using positive integer units."""

from collections.abc import Mapping, Sequence


class WeightedCapacityPolicy:
    """Grant requests only when their frozen weight fits the shared unit budget."""

    key = "weighted"

    def resolve_request_units(
        self, *,
        engine_data: Mapping[str, object] | None,
        default_units: int,
        capacity: int,
    ) -> int:
        """An explicit weight overrides the entity default for one request."""
        if engine_data is None:
            engine_data = {}
        if not isinstance(engine_data, Mapping):
            raise ValueError("engine_data must be a mapping")
        unknown = set(engine_data) - {"weight"}
        if unknown:
            raise ValueError("Unsupported weighted engine_data fields")
        weight = engine_data.get("weight", default_units)
        if type(weight) is not int or weight < 1:
            raise ValueError("weight must be a positive integer")
        if weight > capacity:
            raise ValueError("weight exceeds capacity")
        return weight

    def can_allocate(
        self, *,
        active_units: Sequence[int],
        candidate_units: int,
        capacity: int,
    ) -> bool:
        """No additional active-reservation count limit applies."""
        return sum(active_units) + candidate_units <= capacity

    def validate_limit(
        self, *,
        active_units: Sequence[int],
        waiting_units: Sequence[int],
        capacity: int,
    ) -> None:
        if type(capacity) is not int or capacity < 1:
            raise ValueError("capacity must be a positive integer")
        for units in (*active_units, *waiting_units):
            if type(units) is not int or units < 1 or units > capacity:
                raise ValueError("saved request weight exceeds capacity or is invalid")
        if sum(active_units) > capacity:
            raise ValueError("saved active units exceed current capacity")

    def validate_restored(
        self, *,
        active_units: Sequence[int],
        waiting_units: Sequence[int],
        capacity: int,
    ) -> None:
        """A blocked head may leave spare units; a grantable head may not."""
        self.validate_limit(
            active_units=active_units, waiting_units=waiting_units, capacity=capacity
        )
        if waiting_units and self.can_allocate(
            active_units=active_units,
            candidate_units=waiting_units[0],
            capacity=capacity,
        ):
            raise ValueError("saved waiting queue has a grantable head request")
