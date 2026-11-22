"""Home Assistant restart migration and fail-closed snapshot checks."""

import pytest

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.setup import async_setup_component
from pytest_homeassistant.common import MockConfigEntry

DOMAIN = "resource_queue_manager"
ENTITIES = ("light.migration_a", "light.migration_b")


async def prepare(hass: HomeAssistant) -> MockConfigEntry:
    assert await async_setup_component(hass, DOMAIN, {})
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Migration Test Queue",
        data={
            "max_active": 1,
            "strategy": "fifo",
            "monitored_entities": list(ENTITIES),
        },
    )
    entry.add_to_hass(hass)
    for entity in ENTITIES:
        hass.states.async_set(entity, "off")
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def perform(hass: HomeAssistant, action: str, **data):
    await hass.services.async_call(DOMAIN, action, data, blocking=True)
    await hass.async_block_till_done()


async def test_old_populated_store_keeps_reservations_and_never_regrants_on_reload(
    hass: HomeAssistant,
):
    entry = await prepare(hass)
    await perform(hass, "resume")
    await perform(hass, "request", resource_id="first", entity_id=ENTITIES[0])
    await perform(hass, "request", resource_id="second", entity_id=ENTITIES[1])
    runtime = hass.data[DOMAIN][entry.entry_id]
    saved = runtime.manager.export_state()
    legacy = {
        "max_active": saved["max_active"],
        "active": saved["active"],
        "waiting": saved["waiting"],
        "bindings": saved["bindings"],
    }
    await runtime.store.async_save(legacy)
    events = []
    hass.bus.async_listen(
        "resource_queue_manager_slot_granted", lambda event: events.append(event.data)
    )

    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    restored = hass.data[DOMAIN][entry.entry_id].manager
    assert restored.paused
    assert restored.snapshot().granted == ()
    assert restored.snapshot().active == ("first",)
    assert restored.snapshot().waiting == ("second",)
    assert restored.capacity_mode == "classic"
    assert restored.recurrence_mode == "ignore"
    assert restored.export_state()["occurrence_counts"] == {"first": 1, "second": 1}
    assert events == []

    await perform(hass, "resume")
    assert events == []
    await perform(hass, "release", resource_id="first")
    assert [event["resource_id"] for event in events] == ["second"]
    assert events[0]["occurrences"] == 1
    assert events[0]["capacity_mode"] == "classic"


async def test_corrupted_persisted_weight_does_not_overwrite_store_or_grant(
    hass: HomeAssistant,
):
    from custom_components.resource_queue_manager import async_setup_entry

    entry = await prepare(hass)
    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    from homeassistant.helpers.storage import Store

    store = Store(hass, 1, f"{DOMAIN}.{entry.entry_id}")
    bad = {
        "max_active": 10,
        "capacity_mode": "weighted",
        "strategy": "fifo",
        "strategy_config": {},
        "recurrence_mode": "count",
        "active": ["first"],
        "waiting": ["second"],
        "engine_request_data": {
            "first": {"weight": 8},
            "second": {"weight": True},
        },
        "occurrence_counts": {"first": 1, "second": 3},
        "bindings": {"first": ENTITIES[0], "second": ENTITIES[1]},
    }
    await store.async_save(bad)
    calls = []
    hass.bus.async_listen(
        "resource_queue_manager_slot_granted", lambda event: calls.append(event.data)
    )
    # The entry is configured as classic: mode mismatch with a populated queue
    # and invalid frozen weight must not be translated into an empty queue.
    with pytest.raises(ConfigEntryNotReady):
        await async_setup_entry(hass, entry)

    assert entry.entry_id not in hass.data[DOMAIN]
    assert await store.async_load() == bad
    assert calls == []
