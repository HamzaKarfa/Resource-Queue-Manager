"""Weighted capacity provider, independent of scheduling policies."""

from .policy import WeightedCapacityPolicy


class WeightedCapacityProvider:
    """A shared budget of generic units for requests of different weights."""

    key = "weighted"
    label = "Weighted (units)"
    description = "Each active reservation consumes its own integer unit weight."

    def create(self) -> WeightedCapacityPolicy:
        return WeightedCapacityPolicy()
