"""Home Assistant integration coverage for v1.1 capacity configuration."""

import pytest

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.setup import async_setup_component
from pytest_homeassistant.common import MockConfigEntry

DOMAIN = "resource_queue_manager"
ENTITIES = ["light.relay_1", "light.relay_2", "light.relay_3"]


async def setup_queue(
    hass: HomeAssistant,
    *,
    mode: str = "weighted",
    capacity: int = 100,
    weights: dict[str, int] | None = None,
) -> MockConfigEntry:
    assert await async_setup_component(hass, DOMAIN, {})
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Weighted Test Queue",
        data={
            "max_active": capacity,
            "capacity_mode": mode,
            "entity_weights": weights or {},
            "strategy": "fifo",
            "strategy_config": {},
            "monitored_entities": ENTITIES,
        },
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


async def test_weighted_setup_flow_collects_per_entity_defaults(hass: HomeAssistant):
    assert await async_setup_component(hass, DOMAIN, {})
    flow = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    result = await hass.config_entries.flow.async_configure(
        flow["flow_id"],
        {
            "name": "New weighted queue",
            "max_active": 100,
            "capacity_mode": "weighted",
            "strategy": "fifo",
            "monitored_entities": ENTITIES[:2],
        },
    )
    assert result["type"].value == "form"
    assert result["step_id"] == "weights"
    fields = {marker.schema for marker in result["data_schema"].schema}
    assert fields == set(ENTITIES[:2])

    created = await hass.config_entries.flow.async_configure(
        flow["flow_id"], {ENTITIES[0]: 30, ENTITIES[1]: 40}
    )
    assert created["type"].value == "create_entry"
    assert created["data"]["capacity_mode"] == "weighted"
    assert created["data"]["max_active"] == 100
    assert created["data"]["entity_weights"] == {ENTITIES[0]: 30, ENTITIES[1]: 40}


async def test_weighted_priority_setup_composes_strategy_and_weights(hass: HomeAssistant):
    assert await async_setup_component(hass, DOMAIN, {})
    flow = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    step = await hass.config_entries.flow.async_configure(
        flow["flow_id"],
        {
            "name": "Weighted priority queue",
            "max_active": 100,
            "capacity_mode": "weighted",
            "strategy": "priority_fifo",
            "monitored_entities": ENTITIES[:1],
        },
    )
    assert step["step_id"] == "strategy"
    step = await hass.config_entries.flow.async_configure(
        flow["flow_id"], {"priority_order": "lowest_first"}
    )
    assert step["step_id"] == "weights"
    created = await hass.config_entries.flow.async_configure(
        flow["flow_id"], {ENTITIES[0]: 25}
    )
    assert created["type"].value == "create_entry"
    assert created["data"]["strategy_config"] == {"priority_order": "lowest_first"}
    assert created["data"]["entity_weights"] == {ENTITIES[0]: 25}


async def test_weighted_request_service_defaults_overrides_and_restoration(hass: HomeAssistant):
    entry = await setup_queue(
        hass, weights={ENTITIES[0]: 30, ENTITIES[1]: 40, ENTITIES[2]: 1}
    )
    await action(hass, "resume")
    await action(hass, "request", resource_id="h1", entity_id=ENTITIES[0])
    await action(
        hass, "request", resource_id="h2", entity_id=ENTITIES[1],
        engine_data={"weight": 25},
    )
    manager = hass.data[DOMAIN][entry.entry_id].manager
    assert manager.capacity_mode == "weighted"
    assert manager.capacity_used == 55
    assert manager.capacity_remaining == 45
    assert manager.queue.effective_weight("h1") == 30
    assert manager.queue.effective_weight("h2") == 25
    available = hass.states.get("sensor.weighted_test_queue_available")
    assert available is not None
    assert available.state == "45"
    assert available.attributes["capacity_mode"] == "weighted"
    assert available.attributes["capacity_total"] == 100
    assert available.attributes["capacity_used"] == 55
    assert available.attributes["effective_weights"] == {"h1": 30, "h2": 25}

    # Omitting the override does not re-evaluate the entity's default.
    await action(hass, "request", resource_id="h2", entity_id=ENTITIES[1])
    assert manager.capacity_used == 55
    with pytest.raises(HomeAssistantError, match="different effective weight"):
        await action(
            hass, "request", resource_id="h2", entity_id=ENTITIES[1],
            engine_data={"weight": 30},
        )

    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    restored = hass.data[DOMAIN][entry.entry_id].manager
    assert restored.paused
    assert restored.capacity_used == 55
    assert restored.queue.effective_weight("h2") == 25
    await action(hass, "resume")
    assert restored.capacity_remaining == 45


async def test_options_switch_to_weighted_and_block_switch_with_bookings(hass: HomeAssistant):
    entry = await setup_queue(hass, mode="classic", capacity=3)
    flow = await hass.config_entries.options.async_init(entry.entry_id)
    step = await hass.config_entries.options.async_configure(
        flow["flow_id"],
        {
            "max_active": 100,
            "capacity_mode": "weighted",
            "strategy": "fifo",
            "monitored_entities": ENTITIES,
        },
    )
    assert step["step_id"] == "weights"
    finished = await hass.config_entries.options.async_configure(
        flow["flow_id"], {ENTITIES[0]: 30, ENTITIES[1]: 40, ENTITIES[2]: 1}
    )
    assert finished["type"].value == "create_entry"
    await hass.async_block_till_done()
    assert entry.options["capacity_mode"] == "weighted"
    assert entry.options["entity_weights"][ENTITIES[0]] == 30
    assert hass.data[DOMAIN][entry.entry_id].manager.paused

    await action(hass, "resume")
    await action(hass, "request", resource_id="h1", entity_id=ENTITIES[0])
    flow = await hass.config_entries.options.async_init(entry.entry_id)
    rejected = await hass.config_entries.options.async_configure(
        flow["flow_id"],
        {
            "max_active": 3,
            "capacity_mode": "classic",
            "strategy": "fifo",
            "monitored_entities": ENTITIES,
        },
    )
    assert rejected["type"].value == "form"
    assert rejected["errors"]["base"] == "capacity_mode_in_use"


async def test_change_entity_default_does_not_reweight_active_booking(hass: HomeAssistant):
    entry = await setup_queue(
        hass, weights={ENTITIES[0]: 30, ENTITIES[1]: 40, ENTITIES[2]: 1}
    )
    await action(hass, "resume")
    await action(hass, "request", resource_id="h1", entity_id=ENTITIES[0])

    flow = await hass.config_entries.options.async_init(entry.entry_id)
    weights_step = await hass.config_entries.options.async_configure(
        flow["flow_id"],
        {
            "max_active": 100,
            "capacity_mode": "weighted",
            "strategy": "fifo",
            "monitored_entities": ENTITIES,
        },
    )
    assert weights_step["step_id"] == "weights"
    finished = await hass.config_entries.options.async_configure(
        flow["flow_id"], {ENTITIES[0]: 45, ENTITIES[1]: 40, ENTITIES[2]: 1}
    )
    assert finished["type"].value == "create_entry"
    await hass.async_block_till_done()
    manager = hass.data[DOMAIN][entry.entry_id].manager
    assert manager.paused
    assert manager.capacity_used == 30
    assert manager.entity_weights[ENTITIES[0]] == 45

    await action(hass, "resume")
    await action(hass, "request", resource_id="h2", entity_id=ENTITIES[1])
    assert manager.capacity_used == 70
    assert manager.queue.effective_weight("h1") == 30


async def test_options_reject_limit_that_cannot_fit_frozen_pending_weight(hass: HomeAssistant):
    entry = await setup_queue(
        hass, mode="weighted", capacity=50,
        weights={ENTITIES[0]: 20, ENTITIES[1]: 35, ENTITIES[2]: 1},
    )
    await action(hass, "resume")
    await action(hass, "request", resource_id="h1", entity_id=ENTITIES[0])
    await action(hass, "request", resource_id="h2", entity_id=ENTITIES[1])
    manager = hass.data[DOMAIN][entry.entry_id].manager
    assert manager.snapshot().waiting == ("h2",)
    # 30 units remain physically unreserved, but the 35-unit head blocks.
    available = hass.states.get("sensor.weighted_test_queue_available")
    assert available is not None
    assert available.state == "30"

    flow = await hass.config_entries.options.async_init(entry.entry_id)
    rejected = await hass.config_entries.options.async_configure(
        flow["flow_id"],
        {
            "max_active": 30,
            "capacity_mode": "weighted",
            "strategy": "fifo",
            "monitored_entities": ENTITIES,
        },
    )
    assert rejected["type"].value == "form"
    assert rejected["errors"]["base"] == "max_active_below_reserved"
    assert not manager.paused


async def test_classic_rejects_weighted_engine_request_metadata(hass: HomeAssistant):
    await setup_queue(hass, mode="classic", capacity=3)
    await action(hass, "resume")
    with pytest.raises(HomeAssistantError, match="does not accept engine_data"):
        await action(
            hass, "request", resource_id="h1", entity_id=ENTITIES[0],
            engine_data={"weight": 2},
        )
