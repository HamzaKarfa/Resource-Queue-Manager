"""Explicit registry for capacity policies; never dynamic-import user code."""

from .base import CapacityPolicy, CapacityProvider
from .classic import ClassicCapacityProvider
from .weighted import WeightedCapacityProvider

DEFAULT_CAPACITY_MODE = "classic"

CAPACITY_PROVIDERS: dict[str, CapacityProvider] = {
    "classic": ClassicCapacityProvider(),
    "weighted": WeightedCapacityProvider(),
}


def get_capacity_provider(key: str) -> CapacityProvider:
    """Return a registered provider or fail on an unsupported mode."""
    try:
        return CAPACITY_PROVIDERS[key]
    except (KeyError, TypeError) as err:
        raise ValueError(f"Unsupported capacity mode: {key!r}") from err


def get_capacity_policy(key: str = DEFAULT_CAPACITY_MODE) -> CapacityPolicy:
    """Create a fresh policy for this queue, never a shared singleton."""
    return get_capacity_provider(key).create()
