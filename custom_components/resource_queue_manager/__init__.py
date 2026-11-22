"""Resource Queue Manager: persistent, modular, independent reservations."""

import asyncio
from dataclasses import dataclass

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ConfigEntryNotReady, HomeAssistantError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.storage import Store

from .const import (
    ATTR_RESOURCE_ID,
    ATTR_CONFIG_ENTRY_ID,
    ATTR_ENTITY_ID,
    ATTR_STRATEGY_DATA,
    ATTR_ENGINE_DATA,
    CONF_CAPACITY_MODE,
    CONF_ENTITY_WEIGHTS,
    CONF_RECURRENCE_MODE,
    CONF_ALLOCATION_MODE,
    CONF_MAX_ACTIVE,
    CONF_STRATEGY,
    CONF_STRATEGY_CONFIG,
    CONF_MONITORED_ENTITIES,
    DEFAULT_MAX_ACTIVE,
    DOMAIN,
    EVENT_SLOT_GRANTED,
    SERVICE_CANCEL,
    SERVICE_RELEASE,
    SERVICE_REQUEST,
    SERVICE_RESUME,
    SIGNAL_QUEUE_UPDATED,
)
from .coordinator import ResourceQueueCoordinator, QueueStateError
from .engine import QueueResult
from .strategies import DEFAULT_STRATEGY
from .capacity import DEFAULT_CAPACITY_MODE
from .recurrence import DEFAULT_RECURRENCE_MODE
from .allocation import DEFAULT_ALLOCATION_MODE

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

PLATFORMS = [Platform.SENSOR]
STORAGE_VERSION = 1

REQUEST_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_RESOURCE_ID): cv.string,
        vol.Required(ATTR_ENTITY_ID): cv.entity_id,
        vol.Optional(ATTR_CONFIG_ENTRY_ID): cv.string,
        vol.Optional(ATTR_STRATEGY_DATA): dict,
        vol.Optional(ATTR_ENGINE_DATA): dict,
    }
)
RESOURCE_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_RESOURCE_ID): cv.string,
        vol.Optional(ATTR_CONFIG_ENTRY_ID): cv.string,
    }
)
RESUME_SCHEMA = vol.Schema({vol.Optional(ATTR_CONFIG_ENTRY_ID): cv.string})


@dataclass
class QueueRuntime:
    """Queue, persistence and lock owned by one config entry."""

    manager: ResourceQueueCoordinator
    store: Store
    lock: asyncio.Lock


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Expose actions once; every queue change is serialized and saved."""
    hass.data.setdefault(DOMAIN, {})

    def _get_runtime(call: ServiceCall) -> tuple[str, QueueRuntime]:
        """Route an action to the selected queue without implicit cross-entry writes."""
        loaded: dict[str, QueueRuntime] = hass.data[DOMAIN]
        entry_id = call.data.get(ATTR_CONFIG_ENTRY_ID)
        if entry_id is not None:
            runtime = loaded.get(entry_id)
            if runtime is None:
                raise HomeAssistantError(
                    f"Resource Queue Manager entry {entry_id!r} is not loaded"
                )
            return entry_id, runtime

        # Preserve v0.4 automations ONLY when exactly one entry is configured.
        # A second entry being temporarily unloaded must not make routing implicit.
        if len(hass.config_entries.async_entries(DOMAIN)) > 1:
            raise HomeAssistantError(
                "Multiple resource queues are configured; specify config_entry_id"
            )
        if len(loaded) == 1:
            return next(iter(loaded.items()))
        raise HomeAssistantError("No Resource Queue Manager entry is loaded")

    def _publish(entry_id: str, runtime: QueueRuntime, result: QueueResult) -> None:
        """Publish only after the queue snapshot has been written to disk."""
        async_dispatcher_send(hass, SIGNAL_QUEUE_UPDATED, entry_id)
        for resource_id in result.granted:
            hass.bus.async_fire(
                EVENT_SLOT_GRANTED,
                {
                    ATTR_RESOURCE_ID: resource_id,
                    ATTR_ENTITY_ID: runtime.manager.entity_for(resource_id),
                    "config_entry_id": entry_id,
                    "occurrences": runtime.manager.queue.occurrences(resource_id),
                    "effective_weight": runtime.manager.queue.effective_weight(resource_id),
                    "capacity_mode": runtime.manager.capacity_mode,
                    "allocation_mode": runtime.manager.allocation_mode,
                },
            )

    async def _persist(runtime: QueueRuntime) -> None:
        """Write through synchronously before announcing new grants."""
        try:
            await runtime.store.async_save(runtime.manager.export_state())
        except Exception as err:
            runtime.manager.pause()
            raise HomeAssistantError(
                "Unable to save resource queue state; queue has been paused"
            ) from err

    async def _mutate(call: ServiceCall, operation: str) -> None:
        entry_id, runtime = _get_runtime(call)
        async with runtime.lock:
            try:
                if operation == SERVICE_REQUEST:
                    result = runtime.manager.request(
                        call.data[ATTR_RESOURCE_ID],
                        call.data[ATTR_ENTITY_ID],
                        call.data.get(ATTR_STRATEGY_DATA),
                        engine_data=call.data.get(ATTR_ENGINE_DATA),
                    )
                elif operation == SERVICE_RELEASE:
                    result = runtime.manager.release(call.data[ATTR_RESOURCE_ID])
                elif operation == SERVICE_CANCEL:
                    result = runtime.manager.cancel(call.data[ATTR_RESOURCE_ID])
                else:
                    raise HomeAssistantError("Unsupported queue operation")
            except QueueStateError as err:
                # Also notify dashboards if a safety check paused the manager.
                async_dispatcher_send(hass, SIGNAL_QUEUE_UPDATED, entry_id)
                raise HomeAssistantError(str(err)) from err

            try:
                await _persist(runtime)
            except HomeAssistantError:
                async_dispatcher_send(hass, SIGNAL_QUEUE_UPDATED, entry_id)
                raise
            _publish(entry_id, runtime, result)

    async def async_request(call: ServiceCall) -> None:
        await _mutate(call, SERVICE_REQUEST)

    async def async_release(call: ServiceCall) -> None:
        await _mutate(call, SERVICE_RELEASE)

    async def async_cancel(call: ServiceCall) -> None:
        await _mutate(call, SERVICE_CANCEL)

    async def async_resume(call: ServiceCall) -> None:
        """Explicitly re-enable grants after entity state inspection."""
        entry_id, runtime = _get_runtime(call)
        async with runtime.lock:
            try:
                result = runtime.manager.resume()
            except QueueStateError as err:
                raise HomeAssistantError(str(err)) from err
            try:
                await _persist(runtime)
            except HomeAssistantError:
                async_dispatcher_send(hass, SIGNAL_QUEUE_UPDATED, entry_id)
                raise
            _publish(entry_id, runtime, result)

    hass.services.async_register(
        DOMAIN, SERVICE_REQUEST, async_request, schema=REQUEST_SCHEMA
    )
    hass.services.async_register(
        DOMAIN, SERVICE_RELEASE, async_release, schema=RESOURCE_SCHEMA
    )
    hass.services.async_register(
        DOMAIN, SERVICE_CANCEL, async_cancel, schema=RESOURCE_SCHEMA
    )
    hass.services.async_register(
        DOMAIN, SERVICE_RESUME, async_resume, schema=RESUME_SCHEMA
    )
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Restore reservations and known entities; always boot paused."""
    def get_entity_state(entity_id: str) -> str | None:
        state = hass.states.get(entity_id)
        return state.state if state is not None else None

    # Independent queues must never supervise the same physical entity.
    supervised = set(
        entry.options.get(
            CONF_MONITORED_ENTITIES,
            entry.data.get(CONF_MONITORED_ENTITIES, []),
        )
    )
    for other_id, other in hass.data.get(DOMAIN, {}).items():
        conflict = supervised.intersection(other.manager.monitored_entities)
        if conflict:
            raise ConfigEntryNotReady(
                f"Entities already supervised by queue {other_id}: "
                + ", ".join(sorted(conflict))
            )

    strategy = entry.options.get(
        CONF_STRATEGY, entry.data.get(CONF_STRATEGY, DEFAULT_STRATEGY)
    )
    strategy_config = entry.options.get(
        CONF_STRATEGY_CONFIG, entry.data.get(CONF_STRATEGY_CONFIG, {})
    )
    capacity_mode = entry.options.get(
        CONF_CAPACITY_MODE, entry.data.get(CONF_CAPACITY_MODE, DEFAULT_CAPACITY_MODE)
    )
    entity_weights = entry.options.get(
        CONF_ENTITY_WEIGHTS, entry.data.get(CONF_ENTITY_WEIGHTS)
    )
    recurrence_mode = entry.options.get(
        CONF_RECURRENCE_MODE,
        entry.data.get(CONF_RECURRENCE_MODE, DEFAULT_RECURRENCE_MODE),
    )
    allocation_mode = entry.options.get(
        CONF_ALLOCATION_MODE,
        entry.data.get(CONF_ALLOCATION_MODE, DEFAULT_ALLOCATION_MODE),
    )
    store = Store(
        hass, STORAGE_VERSION, f"{DOMAIN}.{entry.entry_id}"
    )
    try:
        saved = await store.async_load()
        if saved is None:
            manager = ResourceQueueCoordinator(
                max_active=entry.options.get(
                    CONF_MAX_ACTIVE,
                    entry.data.get(CONF_MAX_ACTIVE, DEFAULT_MAX_ACTIVE),
                ),
                entity_state=get_entity_state,
                monitored_entities=supervised,
                strategy=strategy,
                strategy_config=strategy_config,
                capacity_mode=capacity_mode,
                entity_weights=entity_weights,
                recurrence_mode=recurrence_mode,
                allocation_mode=allocation_mode,
            )
        else:
            manager = ResourceQueueCoordinator.from_state(
                max_active=entry.options.get(
                    CONF_MAX_ACTIVE,
                    entry.data.get(CONF_MAX_ACTIVE, DEFAULT_MAX_ACTIVE),
                ),
                entity_state=get_entity_state,
                saved=saved,
                monitored_entities=supervised,
                strategy=strategy,
                strategy_config=strategy_config,
                capacity_mode=capacity_mode,
                entity_weights=entity_weights,
                recurrence_mode=recurrence_mode,
                allocation_mode=allocation_mode,
                legacy_max_active=entry.data.get(
                    CONF_MAX_ACTIVE, DEFAULT_MAX_ACTIVE
                ),
            )
    except Exception as err:
        # Never reset to an empty queue on a corrupt/unreadable snapshot.
        raise ConfigEntryNotReady(
            "Unable to restore resource queue state; preserving existing storage"
        ) from err

    manager.pause()
    runtime = QueueRuntime(manager, store, asyncio.Lock())
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = runtime

    try:
        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    except Exception:
        hass.data[DOMAIN].pop(entry.entry_id, None)
        raise
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload sensors before disposing of the queue runtime."""
    if not await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        return False
    hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)
    return True
