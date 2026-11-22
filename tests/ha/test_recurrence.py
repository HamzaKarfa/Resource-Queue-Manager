"""Home Assistant recurrence setup, service, sensor, event and restart coverage."""

import pytest

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.setup import async_setup_component
from pytest_homeassistant.common import MockConfigEntry

DOMAIN = "resource_queue_manager"
ENTITIES = ("light.garage_test", "light.entrance_test")


async def setup_queue(
    hass: HomeAssistant,
    *,
    recurrence_mode: str | None = "count",
    capacity_mode: str = "classic",
) -> MockConfigEntry:
    assert await async_setup_component(hass, DOMAIN, {})
    data = {
        "max_active": 1 if capacity_mode == "classic" else 10,
        "capacity_mode": capacity_mode,
        "strategy": "fifo",
        "monitored_entities": list(ENTITIES),
    }
    if recurrence_mode is not None:
        data["recurrence_mode"] = recurrence_mode
    if capacity_mode == "weighted":
        data["entity_weights"] = {ENTITIES[0]: 10, ENTITIES[1]: 4}
    entry = MockConfigEntry(
        domain=DOMAIN, title="Recurrence Test Queue", data=data,
    )
    entry.add_to_hass(hass)
    for entity in ENTITIES:
        hass.states.async_set(entity, "off")
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def action(hass: HomeAssistant, name: str, **fields) -> None:
    await hass.services.async_call(DOMAIN, name, fields, blocking=True)
    await hass.async_block_till_done()


def waiting_sensor(hass: HomeAssistant):
    result = hass.states.get("sensor.recurrence_test_queue_waiting")
    assert result is not None
    return result


async def test_setup_flow_exposes_recurrence_mode_and_persists_count(hass: HomeAssistant):
    assert await async_setup_component(hass, DOMAIN, {})
    flow = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    first = await hass.config_entries.flow.async_configure(
        flow["flow_id"], {"name": "Recurring TTS", "monitored_entities": []}
    )
    assert first["step_id"] == "setup_capacity"
    step = await hass.config_entries.flow.async_configure(
        flow["flow_id"], {"max_active": 1, "capacity_mode": "classic"}
    )
    assert step["step_id"] == "setup_scheduling"
    step = await hass.config_entries.flow.async_configure(
        flow["flow_id"], {"strategy": "fifo", "allocation_mode": "strict"}
    )
    assert step["step_id"] == "setup_recurrence"
    assert "recurrence_mode" in {marker.schema for marker in step["data_schema"].schema}
    created = await hass.config_entries.flow.async_configure(
        flow["flow_id"], {"recurrence_mode": "count"}
    )
    assert created["type"].value == "create_entry"
    assert created["data"]["recurrence_mode"] == "count"


async def test_count_mode_exposes_pending_counts_and_grant_event(hass: HomeAssistant):
    entry = await setup_queue(hass)
    events = []
    hass.bus.async_listen(
        "resource_queue_manager_slot_granted", lambda event: events.append(event.data)
    )
    await action(hass, "resume")
    await action(hass, "request", resource_id="busy", entity_id=ENTITIES[0])
    await action(hass, "request", resource_id="garage", entity_id=ENTITIES[1])
    await action(hass, "request", resource_id="garage", entity_id=ENTITIES[1])
    await action(hass, "request", resource_id="garage", entity_id=ENTITIES[1])
    assert waiting_sensor(hass).state == "1"
    assert waiting_sensor(hass).attributes["waiting"] == ["garage"]
    assert waiting_sensor(hass).attributes["recurrence_mode"] == "count"
    assert waiting_sensor(hass).attributes["occurrence_counts"] == {
        "busy": 1, "garage": 3,
    }
    assert hass.data[DOMAIN][entry.entry_id].manager.export_state()["occurrence_counts"] == {
        "busy": 1, "garage": 3,
    }
    await action(hass, "release", resource_id="busy")
    assert events[-1]["resource_id"] == "garage"
    assert events[-1]["occurrences"] == 3
    assert events[-1]["config_entry_id"] == entry.entry_id
    assert waiting_sensor(hass).attributes["occurrence_counts"] == {"garage": 3}
    await action(hass, "request", resource_id="garage", entity_id=ENTITIES[1])
    assert waiting_sensor(hass).attributes["occurrence_counts"] == {"garage": 3}
    await action(hass, "release", resource_id="garage")
    assert waiting_sensor(hass).attributes["occurrence_counts"] == {}


async def test_recurring_pending_counts_survive_reload_and_grant(hass: HomeAssistant):
    entry = await setup_queue(hass, capacity_mode="weighted")
    events = []
    hass.bus.async_listen(
        "resource_queue_manager_slot_granted", lambda event: events.append(event.data)
    )
    await action(hass, "resume")
    await action(hass, "request", resource_id="busy", entity_id=ENTITIES[0])
    await action(
        hass, "request", resource_id="notice", entity_id=ENTITIES[1],
        engine_data={"weight": 2},
    )
    await action(hass, "request", resource_id="notice", entity_id=ENTITIES[1])
    await action(hass, "request", resource_id="notice", entity_id=ENTITIES[1])
    assert waiting_sensor(hass).attributes["occurrence_counts"]["notice"] == 3
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    manager = hass.data[DOMAIN][entry.entry_id].manager
    assert manager.paused
    assert manager.queue.occurrences("notice") == 3
    assert manager.queue.effective_weight("notice") == 2
    await action(hass, "resume")
    await action(hass, "release", resource_id="busy")
    assert events[-1]["resource_id"] == "notice"
    assert events[-1]["occurrences"] == 3
    assert manager.capacity_used == 2


async def test_options_cannot_change_mode_with_reservations(hass: HomeAssistant):
    entry = await setup_queue(hass, recurrence_mode="ignore")
    await action(hass, "resume")
    await action(hass, "request", resource_id="busy", entity_id=ENTITIES[0])
    menu = await hass.config_entries.options.async_init(entry.entry_id)
    flow = await hass.config_entries.options.async_configure(
        menu["flow_id"], {"next_step_id": "recurrence"}
    )
    result = await hass.config_entries.options.async_configure(
        flow["flow_id"], {"recurrence_mode": "count"}
    )
    assert result["type"].value == "form"
    assert result["errors"]["base"] == "recurrence_mode_in_use"
    manager = hass.data[DOMAIN][entry.entry_id].manager
    assert manager.recurrence_mode == "ignore"
    assert not manager.paused

    await action(hass, "release", resource_id="busy")
    menu = await hass.config_entries.options.async_init(entry.entry_id)
    second = await hass.config_entries.options.async_configure(
        menu["flow_id"], {"next_step_id": "recurrence"}
    )
    updated = await hass.config_entries.options.async_configure(
        second["flow_id"], {"recurrence_mode": "count"}
    )
    assert updated["type"].value == "create_entry"
    await hass.async_block_till_done()
    assert entry.options["recurrence_mode"] == "count"
    assert hass.data[DOMAIN][entry.entry_id].manager.paused


async def test_old_entry_defaults_to_ignore_and_no_double_count(hass: HomeAssistant):
    entry = await setup_queue(hass, recurrence_mode=None)
    await action(hass, "resume")
    await action(hass, "request", resource_id="busy", entity_id=ENTITIES[0])
    await action(hass, "request", resource_id="notice", entity_id=ENTITIES[1])
    await action(hass, "request", resource_id="notice", entity_id=ENTITIES[1])
    manager = hass.data[DOMAIN][entry.entry_id].manager
    assert manager.recurrence_mode == "ignore"
    assert manager.queue.occurrences("notice") == 1
    assert waiting_sensor(hass).attributes["waiting"] == ["notice"]
