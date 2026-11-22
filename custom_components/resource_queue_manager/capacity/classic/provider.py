"""Provider registration for v1-compatible classic capacity."""

from .policy import ClassicCapacityPolicy


class ClassicCapacityProvider:
    """The default provider for existing queues and stored snapshots."""

    key = "classic"
    label = "Classic (slots)"
    description = "One reservation uses one available slot."

    def create(self) -> ClassicCapacityPolicy:
        return ClassicCapacityPolicy()
