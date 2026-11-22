"""Read-only sensors exposing resource reservations and recovery readiness."""

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, SIGNAL_QUEUE_UPDATED
from .coordinator import ResourceQueueCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Expose counts and a status sensor for recovery."""
    manager: ResourceQueueCoordinator = hass.data[DOMAIN][entry.entry_id].manager
    async_add_entities(
        [
            ResourceQueueSensor(hass, entry.entry_id, manager, metric)
            for metric in ("active", "waiting", "available", "status")
        ]
    )


class ResourceQueueSensor(SensorEntity):
    """A queue counter or a readiness indicator with reservation attributes."""

    _attr_should_poll = False
    _attr_icon = "mdi:playlist-check"

    def __init__(
        self,
        hass: HomeAssistant,
        entry_id: str,
        manager: ResourceQueueCoordinator,
        metric: str,
    ) -> None:
        self.hass = hass
        self._entry_id = entry_id
        self._manager = manager
        self._metric = metric
        self._attr_unique_id = f"{entry_id}_{metric}"
        # Preserve existing entity identifiers for the original v0.4 entry.
        self._attr_name = (
            f"Resource Queue {metric.capitalize()}"
            if getattr(hass.config_entries.async_get_entry(entry_id), "title", "") == "Resource Queue Manager (FIFO)"
            else f"{hass.config_entries.async_get_entry(entry_id).title} {metric.capitalize()}"
        )

    @property
    def native_value(self) -> int | str:
        """Return a count or the safety state (paused/ready)."""
        snapshot = self._manager.snapshot()
        if self._metric == "active":
            return len(snapshot.active)
        if self._metric == "waiting":
            return len(snapshot.waiting)
        if self._metric == "status":
            return "paused" if self._manager.paused else "ready"
        # Classic reports free slots; weighted reports remaining integer units.
        # A positive weighted remainder does not override strict head-of-line.
        if self._manager.paused:
            return 0
        if self._manager.capacity_mode == "weighted":
            return self._manager.capacity_remaining
        return self._manager.max_active - len(snapshot.active)

    @property
    def extra_state_attributes(self) -> dict:
        """Include current and pending request order for dashboards."""
        snapshot = self._manager.snapshot()
        return {
            "active": list(snapshot.active),
            "waiting": list(snapshot.waiting),
            "max_active": self._manager.max_active,
            "capacity_mode": self._manager.capacity_mode,
            "capacity_unit": "slots" if self._manager.capacity_mode == "classic" else "units",
            "capacity_total": self._manager.max_active,
            "capacity_used": self._manager.capacity_used,
            "capacity_remaining": self._manager.capacity_remaining,
            "effective_weights": {
                resource: self._manager.queue.effective_weight(resource)
                for resource in (*snapshot.active, *snapshot.waiting)
            },
            "strategy": self._manager.strategy,
            "recurrence_mode": self._manager.recurrence_mode,
            "occurrence_counts": self._manager.queue.export_occurrence_counts(),
            "config_entry_id": self._entry_id,
            "paused": self._manager.paused,
            "monitored_entities": list(self._manager.monitored_entities),
            "recovery_issues": list(self._manager.recovery_issues()),
        }

    async def async_added_to_hass(self) -> None:
        """Track changes through dispatcher, without polling."""
        await super().async_added_to_hass()
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass, SIGNAL_QUEUE_UPDATED, self._handle_queue_change
            )
        )

    @callback
    def _handle_queue_change(self, entry_id: str) -> None:
        if entry_id == self._entry_id:
            self.async_write_ha_state()
