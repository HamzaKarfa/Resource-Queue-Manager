"""Pure-Python resource coordinator with conservative restart recovery.

No Home Assistant imports and NO physical entity control. All operations are
synchronous; the HA adapter serializes state mutations and disk writes.
"""

from collections.abc import Callable, Iterable, Mapping
from .capacity import DEFAULT_CAPACITY_MODE
from .recurrence import DEFAULT_RECURRENCE_MODE
from .engine import ResourceQueue, QueueResult
from .strategies import DEFAULT_STRATEGY, validate_strategy_config
from .entity_supervision import (
    recovery_issue,
    release_issue,
    validate_entity_id,
)


class QueueStateError(ValueError):
    """A request or a recovery operation is unsafe."""


class ResourceQueueCoordinator:
    """Reserve slots only for explicitly supervised entities.

    A saved booking retains its binding. Historical entities are NOT supervised:
    monitoring is controlled by a separate configuration-entry option.
    """

    def __init__(
        self,
        max_active: int,
        entity_state: Callable[[str], str | None],
        monitored_entities: Iterable[str] = (),
        strategy: str = DEFAULT_STRATEGY,
        strategy_config: Mapping[str, object] | None = None,
        capacity_mode: str = DEFAULT_CAPACITY_MODE,
        entity_weights: Mapping[str, int] | None = None,
        recurrence_mode: str = DEFAULT_RECURRENCE_MODE,
    ) -> None:
        self.queue = ResourceQueue(
            max_active, strategy, strategy_config,
            capacity_mode=capacity_mode, recurrence_mode=recurrence_mode,
        )
        self._entity_state = entity_state
        self._entities: dict[str, str] = {}
        monitored = list(monitored_entities)
        for entity in monitored:
            self._validate_entity_id(entity)
        if len(set(monitored)) != len(monitored):
            raise QueueStateError("Duplicate supervised entity")
        self._monitored_entities = frozenset(monitored)
        weights = dict(entity_weights or {})
        if capacity_mode == "classic" and weights:
            raise QueueStateError("Classic capacity does not configure entity weights")
        if set(weights) - self._monitored_entities:
            raise QueueStateError("Weights refer to entities that are not supervised")
        if capacity_mode == "weighted":
            self._entity_weights = {}
            for entity in monitored:
                weight = weights.get(entity, 1)
                try:
                    self._entity_weights[entity] = self.queue._capacity_policy.resolve_request_units(
                        engine_data=None, default_units=weight, capacity=max_active
                    )
                except ValueError as err:
                    raise QueueStateError(f"Invalid weight for {entity!r}: {err}") from err
        else:
            self._entity_weights = {}
        self.paused = False

    @classmethod
    def from_state(
        cls,
        max_active: int,
        entity_state: Callable[[str], str | None],
        saved: object,
        monitored_entities: Iterable[str] = (),
        legacy_max_active: int | None = None,
        strategy: str = DEFAULT_STRATEGY,
        strategy_config: Mapping[str, object] | None = None,
        capacity_mode: str = DEFAULT_CAPACITY_MODE,
        entity_weights: Mapping[str, int] | None = None,
        recurrence_mode: str = DEFAULT_RECURRENCE_MODE,
    ) -> "ResourceQueueCoordinator":
        """Restore saved request order and entity registry; always start paused."""
        if not isinstance(saved, dict):
            raise QueueStateError("Invalid stored coordinator state")

        # The saved limit validates the original reservation invariants. The new
        # configured limit can be larger without allocating extra slots yet.
        # Old 0.2 snapshots lacked max_active; use the initial entry limit.
        stored_limit = saved.get(
            "max_active",
            legacy_max_active if legacy_max_active is not None else max_active,
        )
        saved_strategy = saved.get("strategy", DEFAULT_STRATEGY)
        saved_config = saved.get("strategy_config", {})
        saved_capacity_mode = saved.get("capacity_mode", DEFAULT_CAPACITY_MODE)
        saved_recurrence_mode = saved.get("recurrence_mode", DEFAULT_RECURRENCE_MODE)
        configured = validate_strategy_config(strategy, strategy_config)
        saved_active = saved.get("active")
        saved_waiting = saved.get("waiting")
        # Never silently reinterpret already queued requests under a new policy.
        if (saved_strategy != strategy or saved_config != configured) and (
            saved_active or saved_waiting
        ):
            raise QueueStateError(
                "Cannot change strategy or settings while reservations or requests are pending"
            )
        if saved_capacity_mode != capacity_mode and (saved_active or saved_waiting):
            raise QueueStateError(
                "Cannot change capacity mode while reservations or requests are pending"
            )
        if saved_recurrence_mode != recurrence_mode and (saved_active or saved_waiting):
            raise QueueStateError(
                "Cannot change recurrence mode while reservations or requests are pending"
            )
        queue = ResourceQueue.from_snapshot(
            stored_limit, saved_active, saved_waiting,
            strategy=strategy, strategy_config=configured,
            request_data=saved.get("request_data", {}),
            capacity_mode=capacity_mode,
            engine_request_data=saved.get("engine_request_data", {}),
            recurrence_mode=recurrence_mode,
            occurrence_counts=saved.get("occurrence_counts"),
        )
        try:
            queue.validate_capacity_limit(max_active)
        except ValueError as err:
            raise QueueStateError(
                "New maximum cannot honor saved active or waiting reservations"
            ) from err
        queue.max_active = max_active
        bindings = saved.get("bindings")
        if not isinstance(bindings, dict):
            raise QueueStateError("Invalid saved entity assignments")
        current_ids = set(queue.snapshot().active + queue.snapshot().waiting)
        if set(bindings) != current_ids:
            raise QueueStateError("Saved queue and entity assignments disagree")

        # Accept version 0.2 storage containing historical known_entities,
        # but never treat that history as the current supervision registry.
        known = saved.get("known_entities")
        if known is not None:
            if not isinstance(known, dict) or any(
                known.get(resource) != entity for resource, entity in bindings.items()
            ):
                raise QueueStateError("Legacy entity registry disagrees with queue")

        if entity_weights is None and capacity_mode == "weighted":
            entity_weights = saved.get("entity_weights", {})
        instance = cls(
            max_active, entity_state, monitored_entities,
            strategy=strategy, strategy_config=configured,
            capacity_mode=capacity_mode, entity_weights=entity_weights,
            recurrence_mode=recurrence_mode,
        )
        for resource, entity in bindings.items():
            instance._validate_resource_id(resource)
            instance._validate_entity_id(entity)
        if len(set(bindings.values())) != len(bindings):
            raise QueueStateError("Multiple queued resources share a entity")

        # Refuse a changed configuration that would silently abandon a
        # reserved or waiting resource. The options flow also guards this.
        unmanaged = set(bindings.values()) - instance._monitored_entities
        if unmanaged:
            raise QueueStateError(
                "Saved queued entities are not supervised: "
                + ", ".join(sorted(unmanaged))
            )

        instance.queue = queue
        instance._entities = dict(bindings)
        instance.pause()
        return instance

    def export_state(self) -> dict:
        """JSON-safe snapshot for Home Assistant's persistent Store."""
        snapshot = self.queue.snapshot()
        return {
            "active": list(snapshot.active),
            "waiting": list(snapshot.waiting),
            "max_active": self.max_active,
            "strategy": self.strategy,
            "strategy_config": dict(self.queue.strategy_config),
            "request_data": self.queue.export_request_data(),
            "capacity_mode": self.capacity_mode,
            "engine_request_data": self.queue.export_engine_request_data(),
            "entity_weights": dict(self._entity_weights),
            "recurrence_mode": self.recurrence_mode,
            "occurrence_counts": self.queue.export_occurrence_counts(),
            "bindings": dict(self._entities),
        }

    def snapshot(self) -> QueueResult:
        """Return an immutable view of reservations."""
        return self.queue.snapshot()

    @property
    def strategy(self) -> str:
        return self.queue.strategy

    @property
    def max_active(self) -> int:
        return self.queue.max_active

    @property
    def capacity_mode(self) -> str:
        return self.queue.capacity_mode

    @property
    def recurrence_mode(self) -> str:
        return self.queue.recurrence_mode

    @property
    def entity_weights(self) -> dict[str, int]:
        return dict(self._entity_weights)

    @property
    def capacity_used(self) -> int:
        return self.queue.capacity_used

    @property
    def capacity_remaining(self) -> int:
        return self.queue.capacity_remaining

    @property
    def monitored_entities(self) -> tuple[str, ...]:
        """Explicit entity supervision list from Home Assistant options."""
        return tuple(sorted(self._monitored_entities))

    def entity_for(self, resource_id: str) -> str | None:
        """Return the entity for a current reservation or waiting request."""
        return self._entities.get(resource_id)

    def pause(self) -> None:
        """Stop granting or releasing slots until a recovery check completes."""
        self.paused = True

    def recovery_issues(self) -> tuple[str, ...]:
        """Check configured entities, never historical test associations."""
        active_entities = {
            self._entities[resource_id] for resource_id in self.queue.snapshot().active
        }
        problems: list[str] = []
        for entity in sorted(self._monitored_entities):
            issue = recovery_issue(
                entity, self._entity_state(entity), entity in active_entities
            )
            if issue:
                problems.append(issue)
        return tuple(problems)

    def resume(self) -> QueueResult:
        """Resume after checking supervised entities, filling increased slots.

        Existing active bookings remain allocated. If the limit was raised
        while waiting requests existed, the oldest requests receive the new
        slots. The HA adapter persists this result BEFORE firing their grants.
        """
        problems = self.recovery_issues()
        if problems:
            raise QueueStateError("Recovery blocked: " + "; ".join(problems))
        self.paused = False
        return self.queue.allocate_pending()

    def _require_ready(self) -> None:
        if self.paused:
            raise QueueStateError(
                "Queue is paused after startup; check entities and call resume"
            )

    def request(
        self, resource_id: str, entity_id: str,
        request_data: Mapping[str, object] | None = None,
        *,
        engine_data: Mapping[str, object] | None = None,
    ) -> QueueResult:
        """Ask for a slot, without switching any real device."""
        self._require_ready()
        self._validate_resource_id(resource_id)
        self._validate_entity_id(entity_id)
        if entity_id not in self._monitored_entities:
            raise QueueStateError(
                f"Entity {entity_id!r} is not supervised; configure it first"
            )
        old = self._entities.get(resource_id)
        if old is not None and old != entity_id:
            raise QueueStateError(
                f"{resource_id!r} is already bound to {old!r}"
            )
        if any(
            other_id != resource_id and bound_relay == entity_id
            for other_id, bound_relay in self._entities.items()
        ):
            raise QueueStateError(
                f"Entity {entity_id!r} is bound to another resource"
            )

        # Check every explicitly supervised entity before granting.
        problems = self.recovery_issues()
        if problems:
            self.pause()
            raise QueueStateError(
                "Queue paused on unsafe entity state: " + "; ".join(problems)
            )

        state = self._entity_state(entity_id)
        issue = recovery_issue(
            entity_id, state, resource_id in self.queue.snapshot().active
        )
        if issue:
            raise QueueStateError(issue)

        try:
            result = self.queue.request(
                resource_id, request_data,
                engine_data=engine_data,
                default_weight=self._entity_weights.get(entity_id, 1),
            )
        except ValueError as err:
            raise QueueStateError(str(err)) from err
        self._entities[resource_id] = entity_id
        return result

    def release(self, resource_id: str) -> QueueResult:
        """Release a slot only if the entity is observed OFF."""
        return self._discard(resource_id)

    def cancel(self, resource_id: str) -> QueueResult:
        """Cancel a pending request or release an OFF reservation."""
        return self._discard(resource_id)

    def _discard(self, resource_id: str) -> QueueResult:
        self._require_ready()
        self._validate_resource_id(resource_id)
        if resource_id in self.queue.snapshot().active:
            entity = self._entities[resource_id]
            state = self._entity_state(entity)
            issue = release_issue(entity, state)
            if issue:
                raise QueueStateError(
                    f"Cannot release {resource_id!r}: {issue}"
                )
        problems = self.recovery_issues()
        if problems:
            self.pause()
            raise QueueStateError(
                "Queue paused on unsafe entity state: " + "; ".join(problems)
            )

        result = self.queue.release(resource_id)
        self._entities.pop(resource_id, None)
        return result

    @staticmethod
    def _validate_resource_id(resource_id: str) -> None:
        if not isinstance(resource_id, str) or not resource_id.strip():
            raise QueueStateError("resource_id must be a non-empty string")
        if resource_id != resource_id.strip():
            raise QueueStateError("resource_id must not have surrounding whitespace")

    @staticmethod
    def _validate_entity_id(entity_id: str) -> None:
        try:
            validate_entity_id(entity_id)
        except ValueError as err:
            raise QueueStateError(str(err)) from err
