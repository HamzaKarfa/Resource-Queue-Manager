"""Strategy-independent, pure-Python reservation engine.

Queue strategy controls *only the next-grant order*. Capacity policies
validate admission; active state, de-duplication and persistence remain here.
Physical device switching remains strictly outside the engine.
"""

from collections import deque
from collections.abc import Mapping
from dataclasses import dataclass

from .capacity import DEFAULT_CAPACITY_MODE, get_capacity_policy
from .strategies import (
    DEFAULT_STRATEGY,
    QueueRequest,
    get_strategy,
    validate_request_data,
    validate_strategy_config,
)


@dataclass(frozen=True, slots=True)
class QueueResult:
    """Snapshot after a queue transition, preserving legacy ID-only outputs."""

    granted: tuple[str, ...]
    active: tuple[str, ...]
    waiting: tuple[str, ...]


class ResourceQueue:
    """Hard-capacity queue with an injected scheduling policy."""

    def __init__(
        self,
        max_active: int = 3,
        strategy: str = DEFAULT_STRATEGY,
        strategy_config: Mapping[str, object] | None = None,
        capacity_mode: str = DEFAULT_CAPACITY_MODE,
    ) -> None:
        if (
            type(max_active) is not int
            or max_active < 1
        ):
            raise ValueError("max_active must be a positive integer")
        self.max_active = max_active
        self.strategy = strategy
        self.strategy_config = validate_strategy_config(strategy, strategy_config)
        self._strategy = get_strategy(strategy, self.strategy_config)
        self.capacity_mode = capacity_mode
        self._capacity_policy = get_capacity_policy(capacity_mode)
        self._active: dict[str, None] = {}
        self._waiting: deque[str] = deque()
        self._requests: dict[str, QueueRequest] = {}

    @classmethod
    def from_snapshot(
        cls,
        max_active: int,
        active: object,
        waiting: object,
        strategy: str = DEFAULT_STRATEGY,
        strategy_config: Mapping[str, object] | None = None,
        request_data: object | None = None,
        capacity_mode: str = DEFAULT_CAPACITY_MODE,
    ) -> "ResourceQueue":
        """Restore grants and metadata exactly; never allocate while loading."""
        instance = cls(max_active, strategy, strategy_config, capacity_mode)
        if not isinstance(active, list) or not isinstance(waiting, list):
            raise ValueError("stored active and waiting must be lists")
        combined = active + waiting
        if any(
            not isinstance(value, str)
            or not value.strip()
            or value != value.strip()
            for value in combined
        ):
            raise ValueError("stored resource IDs must be normalized strings")
        if len(combined) != len(set(combined)):
            raise ValueError("duplicate resource ID in saved queue")
        if request_data is None:
            request_data = {}
        if not isinstance(request_data, dict):
            raise ValueError("stored request metadata must be a mapping")
        if set(request_data) - set(combined):
            raise ValueError("saved request metadata contains unknown resources")

        restored: dict[str, QueueRequest] = {}
        for resource_id in combined:
            normalized = validate_request_data(
                strategy, request_data.get(resource_id, {})
            )
            restored[resource_id] = QueueRequest(resource_id, normalized)

        instance._active = dict.fromkeys(active)
        instance._waiting = deque(waiting)
        instance._requests = restored
        # Policies own capacity invariants; classic retains the v1.0 rules.
        # Until weighted request metadata is introduced, each request costs 1.
        instance._capacity_policy.validate_restored(
            active_units=(1,) * len(active),
            waiting_units=(1,) * len(waiting),
            capacity=max_active,
        )
        return instance

    def request(
        self,
        resource_id: str,
        request_data: Mapping[str, object] | None = None,
    ) -> QueueResult:
        """Request a slot with metadata validated by its provider."""
        self._validate_id(resource_id)
        metadata = validate_request_data(self.strategy, request_data)
        existing = self._requests.get(resource_id)
        if existing is not None:
            if dict(existing.data) != metadata:
                raise ValueError(
                    f"Resource {resource_id!r} already has different request metadata"
                )
            return self._allocate()

        request = QueueRequest(resource_id, metadata)
        # A strategy can consult all pending and active request metadata.
        self._strategy.enqueue(
            self._waiting, request, {**self._requests, resource_id: request}
        )
        if resource_id not in self._waiting:
            raise ValueError("Strategy failed to enqueue the resource")
        self._requests[resource_id] = request
        return self._allocate()

    def release(self, resource_id: str) -> QueueResult:
        """Release a reservation or withdraw a pending request."""
        self._validate_id(resource_id)
        self._active.pop(resource_id, None)
        try:
            self._waiting.remove(resource_id)
        except ValueError:
            pass
        self._requests.pop(resource_id, None)
        return self._allocate()

    def snapshot(self) -> QueueResult:
        return QueueResult((), tuple(self._active), tuple(self._waiting))

    def export_request_data(self) -> dict[str, dict[str, str | int | float | bool]]:
        """Persist only non-empty request metadata, keyed by resource ID."""
        return {
            resource_id: dict(request.data)
            for resource_id, request in self._requests.items()
            if request.data
        }

    def allocate_pending(self) -> QueueResult:
        """Only the coordinator calls this after safety/recovery checks."""
        return self._allocate()

    def _allocate(self) -> QueueResult:
        newly_granted: list[str] = []
        while self._waiting:
            candidate = self._waiting[0]
            if candidate in self._active:
                self._waiting.popleft()
                continue
            # Never skip the strategy-selected head of the waiting queue.
            if not self._capacity_policy.can_allocate(
                active_units=(1,) * len(self._active),
                candidate_units=1,
                capacity=self.max_active,
            ):
                break
            self._waiting.popleft()
            self._active[candidate] = None
            newly_granted.append(candidate)
        return QueueResult(
            tuple(newly_granted), tuple(self._active), tuple(self._waiting)
        )

    @staticmethod
    def _validate_id(resource_id: str) -> None:
        if (
            not isinstance(resource_id, str)
            or not resource_id.strip()
            or resource_id != resource_id.strip()
        ):
            raise ValueError("resource_id must be a non-empty normalized string")
