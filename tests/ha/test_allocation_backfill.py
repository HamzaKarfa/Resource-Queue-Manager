"""Home Assistant v1.2 allocation-mode setup, options, events and reload tests."""

import pytest

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.setup import async_setup_component
from pytest_homeassistant.common import MockConfigEntry

DOMAIN = "resource_queue_manager"


async def setup_queue(
    hass: HomeAssistant,
    title: str,
    monitored: list[str],
    *,
    allocation_mode: str | None = "backfill",
    recurrence_mode: str = "count",
) -> MockConfigEntry:
    assert await async_setup_component(hass, DOMAIN, {})
    data = {
        "max_active": 15,
        "capacity_mode": "weighted",
        "strategy": "priority_fifo",
        "strategy_config": {"priority_order": "highest_first"},
        "recurrence_mode": recurrence_mode,
        "entity_weights": {
            monitored[0]: 10,
            monitored[1]: 10,
            monitored[2]: 3,
            monitored[3]: 2,
        },
        "monitored_entities": monitored,
    }
    if allocation_mode is not None:
        data["allocation_mode"] = allocation_mode
    entry = MockConfigEntry(domain=DOMAIN, title=title, data=data)
    entry.add_to_hass(hass)
    for entity in monitored:
        hass.states.async_set(entity, "off")
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def action(hass: HomeAssistant, name: str, **data):
    await hass.services.async_call(DOMAIN, name, data, blocking=True)
    await hass.async_block_till_done()


def attributes(hass: HomeAssistant, name: str):
    state = hass.states.get(name)
    assert state is not None
    return state.attributes


def options_payload(
    monitored: list[str],
    *,
    allocation_mode: str,
) -> dict:
    return {
        "max_active": 15,
        "capacity_mode": "weighted",
        "allocation_mode": allocation_mode,
        "recurrence_mode": "count",
        "strategy": "priority_fifo",
        "monitored_entities": monitored,
    }


async def test_setup_flow_exposes_allocation_selector_and_saves_backfill(hass: HomeAssistant):
    assert await async_setup_component(hass, DOMAIN, {})
    flow = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    fields = {marker.schema for marker in flow["data_schema"].schema}
    assert "allocation_mode" in fields
    result = await hass.config_entries.flow.async_configure(
        flow["flow_id"], {
            "name": "New Backfill",
            "max_active": 15,
            "capacity_mode": "weighted",
            "allocation_mode": "backfill",
            "recurrence_mode": "count",
            "strategy": "fifo",
            "monitored_entities": [],
        },
    )
    assert result["type"].value == "create_entry"
    assert result["data"]["allocation_mode"] == "backfill"
    assert result["data"]["capacity_mode"] == "weighted"


async def test_backfill_ha_service_events_and_recurrence_during_reload(hass: HomeAssistant):
    monitored = [f"light.backfill_{i}" for i in range(1, 5)]
    entry = await setup_queue(hass, "Backfill Lab", monitored)
    events = []
    hass.bus.async_listen(
        "resource_queue_manager_slot_granted", lambda event: events.append(event.data)
    )
    await action(hass, "resume", config_entry_id=entry.entry_id)
    await action(hass, "request", config_entry_id=entry.entry_id,
                 resource_id="active", entity_id=monitored[0],
                 strategy_data={"priority": 1})
    await action(hass, "request", config_entry_id=entry.entry_id,
                 resource_id="large", entity_id=monitored[1],
                 strategy_data={"priority": 10})
    await action(hass, "request", config_entry_id=entry.entry_id,
                 resource_id="small", entity_id=monitored[2],
                 strategy_data={"priority": 2})
    await action(hass, "request", config_entry_id=entry.entry_id,
                 resource_id="tiny", entity_id=monitored[3],
                 strategy_data={"priority": 3})

    manager = hass.data[DOMAIN][entry.entry_id].manager
    assert manager.capacity_used == 15
    assert manager.snapshot().active == ("active", "small", "tiny")
    assert manager.snapshot().waiting == ("large",)
    assert attributes(hass, "sensor.backfill_lab_available")["allocation_mode"] == "backfill"
    assert attributes(hass, "sensor.backfill_lab_available")["capacity_remaining"] == 0
    assert [event["resource_id"] for event in events] == ["active", "small", "tiny"]
    assert all(event["allocation_mode"] == "backfill" for event in events)
    assert all(event["config_entry_id"] == entry.entry_id for event in events)

    await action(hass, "request", config_entry_id=entry.entry_id,
                 resource_id="large", entity_id=monitored[1],
                 strategy_data={"priority": 10})
    assert manager.queue.occurrences("large") == 2

    events.clear()
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    restored = hass.data[DOMAIN][entry.entry_id].manager
    assert restored.paused
    assert restored.allocation_mode == "backfill"
    assert restored.snapshot().active == ("active", "small", "tiny")
    assert restored.snapshot().waiting == ("large",)
    assert restored.queue.occurrences("large") == 2
    assert events == []

    await action(hass, "resume", config_entry_id=entry.entry_id)
    assert events == []
    await action(hass, "release", config_entry_id=entry.entry_id, resource_id="active")
    assert events[-1]["resource_id"] == "large"
    assert events[-1]["occurrences"] == 2
    assert events[-1]["effective_weight"] == 10
    assert events[-1]["allocation_mode"] == "backfill"
    assert restored.capacity_used == 15


async def test_options_change_requires_empty_queue_and_reload(hass: HomeAssistant):
    monitored = [f"light.options_{i}" for i in range(1, 5)]
    entry = await setup_queue(hass, "Options Mode", monitored, allocation_mode=None)
    manager = hass.data[DOMAIN][entry.entry_id].manager
    assert manager.allocation_mode == "strict"
    flow = await hass.config_entries.options.async_init(entry.entry_id)
    fields = {marker.schema for marker in flow["data_schema"].schema}
    assert "allocation_mode" in fields

    result = await hass.config_entries.options.async_configure(
        flow["flow_id"], options_payload(monitored, allocation_mode="backfill")
    )
    assert result["step_id"] == "strategy"
    result = await hass.config_entries.options.async_configure(
        flow["flow_id"], {"priority_order": "highest_first"}
    )
    assert result["step_id"] == "weights"
    result = await hass.config_entries.options.async_configure(
        flow["flow_id"], {
            monitored[0]: 10, monitored[1]: 10, monitored[2]: 3, monitored[3]: 2,
        }
    )
    assert result["type"].value == "create_entry"
    await hass.async_block_till_done()
    assert entry.options["allocation_mode"] == "backfill"
    assert hass.data[DOMAIN][entry.entry_id].manager.paused
    await action(hass, "resume", config_entry_id=entry.entry_id)
    await action(hass, "request", config_entry_id=entry.entry_id,
                 resource_id="active", entity_id=monitored[0],
                 strategy_data={"priority": 1})

    flow = await hass.config_entries.options.async_init(entry.entry_id)
    rejected = await hass.config_entries.options.async_configure(
        flow["flow_id"], options_payload(monitored, allocation_mode="strict")
    )
    assert rejected["type"].value == "form"
    assert rejected["errors"]["base"] == "allocation_mode_in_use"
    assert hass.data[DOMAIN][entry.entry_id].manager.allocation_mode == "backfill"
    assert not hass.data[DOMAIN][entry.entry_id].manager.paused

    await action(hass, "release", config_entry_id=entry.entry_id, resource_id="active")
    flow = await hass.config_entries.options.async_init(entry.entry_id)
    changed = await hass.config_entries.options.async_configure(
        flow["flow_id"], options_payload(monitored, allocation_mode="strict")
    )
    assert changed["step_id"] == "strategy"
    changed = await hass.config_entries.options.async_configure(
        flow["flow_id"], {"priority_order": "highest_first"}
    )
    assert changed["step_id"] == "weights"
    changed = await hass.config_entries.options.async_configure(
        flow["flow_id"], {
            monitored[0]: 10, monitored[1]: 10, monitored[2]: 3, monitored[3]: 2,
        }
    )
    assert changed["type"].value == "create_entry"
    await hass.async_block_till_done()
    assert entry.options["allocation_mode"] == "strict"
    assert hass.data[DOMAIN][entry.entry_id].manager.allocation_mode == "strict"


async def test_two_queues_keep_independent_allocation_modes(hass: HomeAssistant):
    a_entities = [f"light.queue_a_{i}" for i in range(1, 5)]
    b_entities = [f"light.queue_b_{i}" for i in range(1, 5)]
    a = await setup_queue(hass, "Queue Alpha", a_entities, allocation_mode="backfill")
    b = await setup_queue(hass, "Queue Beta", b_entities, allocation_mode="strict")
    events = []
    hass.bus.async_listen(
        "resource_queue_manager_slot_granted", lambda event: events.append(event.data)
    )
    with pytest.raises(HomeAssistantError, match="config_entry_id"):
        await action(hass, "resume")
    for entry in (a, b):
        await action(hass, "resume", config_entry_id=entry.entry_id)
    for entry, entities in ((a, a_entities), (b, b_entities)):
        for name, entity, priority in (
            ("busy", entities[0], 1), ("head", entities[1], 10), ("small", entities[2], 2),
        ):
            await action(hass, "request", config_entry_id=entry.entry_id,
                         resource_id=name, entity_id=entity,
                         strategy_data={"priority": priority})
    alpha = hass.data[DOMAIN][a.entry_id].manager
    beta = hass.data[DOMAIN][b.entry_id].manager
    assert alpha.snapshot().active == ("busy", "small")
    assert alpha.snapshot().waiting == ("head",)
    assert beta.snapshot().active == ("busy",)
    assert beta.snapshot().waiting == ("head", "small")
    assert alpha.capacity_remaining == 2
    assert beta.capacity_remaining == 5
    assert attributes(hass, "sensor.queue_alpha_status")["allocation_mode"] == "backfill"
    assert attributes(hass, "sensor.queue_beta_status")["allocation_mode"] == "strict"
    assert {event["config_entry_id"] for event in events} == {a.entry_id, b.entry_id}
