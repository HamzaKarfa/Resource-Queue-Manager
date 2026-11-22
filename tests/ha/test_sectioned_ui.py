"""End-to-end real UI tests for the new guided setup and options menu."""

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.setup import async_setup_component
from pytest_homeassistant.common import MockConfigEntry

DOMAIN = "resource_queue_manager"
E = ["light.section_1", "light.section_2", "light.section_3"]


async def setup_entry(
    hass: HomeAssistant, *,
    mode="weighted", strategy="priority_fifo", allocation="backfill",
    recurrence="count", capacity=15,
) -> MockConfigEntry:
    assert await async_setup_component(hass, DOMAIN, {})
    entry = MockConfigEntry(
        domain=DOMAIN, title="Sectioned Example",
        data={
            "max_active": capacity,
            "capacity_mode": mode,
            "strategy": strategy,
            "strategy_config": {"priority_order": "highest_first"} if strategy=="priority_fifo" else {},
            "allocation_mode": allocation,
            "recurrence_mode": recurrence,
            "entity_weights": {E[0]: 10, E[1]: 5} if mode=="weighted" else {},
            "monitored_entities": E[:2],
        },
    )
    entry.add_to_hass(hass)
    for e in E:
        hass.states.async_set(e, "off")
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def select_category(hass, entry, category):
    flow = await hass.config_entries.options.async_init(entry.entry_id)
    assert flow["type"].value == "menu"
    assert flow["step_id"] == "init"
    assert list(flow["menu_options"]) == ["resources", "capacity", "scheduling", "recurrence"]
    form = await hass.config_entries.options.async_configure(
        flow["flow_id"], {"next_step_id": category}
    )
    assert form["step_id"] == category
    assert form["type"].value == "form"
    return form


async def request(hass, service, **data):
    await hass.services.async_call(DOMAIN, service, data, blocking=True)
    await hass.async_block_till_done()


async def test_menu_and_recurrence_only_change_preserves_all_other_configuration(
    hass: HomeAssistant,
):
    entry = await setup_entry(hass)
    original = entry.data
    form = await select_category(hass, entry, "recurrence")
    assert {m.schema for m in form["data_schema"].schema} == {"recurrence_mode"}
    result = await hass.config_entries.options.async_configure(
        form["flow_id"], {"recurrence_mode": "ignore"}
    )
    assert result["type"].value == "create_entry"
    await hass.async_block_till_done()
    manager = hass.data[DOMAIN][entry.entry_id].manager
    assert manager.paused
    assert manager.recurrence_mode == "ignore"
    assert manager.allocation_mode == "backfill"
    assert manager.capacity_mode == "weighted"
    assert manager.max_active == 15
    assert manager.strategy == "priority_fifo"
    assert manager.queue.strategy_config == {"priority_order": "highest_first"}
    assert manager.entity_weights == {E[0]: 10, E[1]: 5}
    assert original["recurrence_mode"] == "count"


async def test_opening_menu_does_not_pause_active_queue_and_mode_switch_is_blocked(
    hass: HomeAssistant,
):
    entry = await setup_entry(hass)
    await request(hass, "resume")
    await request(hass, "request", resource_id="r1", entity_id=E[0],
                  strategy_data={"priority": 1})
    manager = hass.data[DOMAIN][entry.entry_id].manager
    assert not manager.paused

    form = await select_category(hass, entry, "scheduling")
    assert not manager.paused
    fields = {m.schema for m in form["data_schema"].schema}
    assert fields == {"strategy", "allocation_mode", "edit_strategy_options"}
    rejected = await hass.config_entries.options.async_configure(
        form["flow_id"],
        {"strategy": "priority_fifo", "allocation_mode": "strict"},
    )
    assert rejected["type"].value == "form"
    assert rejected["errors"]["base"] == "allocation_mode_in_use"
    assert not manager.paused
    assert manager.allocation_mode == "backfill"
    assert manager.snapshot().active == ("r1",)


async def test_change_allocation_keeps_existing_priority_settings(
    hass: HomeAssistant,
):
    entry = await setup_entry(hass)
    form = await select_category(hass, entry, "scheduling")
    result = await hass.config_entries.options.async_configure(
        form["flow_id"],
        {"strategy": "priority_fifo", "allocation_mode": "strict"}
    )
    assert result["type"].value == "create_entry"
    await hass.async_block_till_done()
    manager = hass.data[DOMAIN][entry.entry_id].manager
    assert manager.allocation_mode == "strict"
    assert manager.queue.strategy_config == {"priority_order": "highest_first"}
    assert manager.entity_weights == {E[0]: 10, E[1]: 5}


async def test_edit_resource_weights_without_changing_capacity_or_strategy(
    hass: HomeAssistant,
):
    entry = await setup_entry(hass)
    form = await select_category(hass, entry, "resources")
    assert {m.schema for m in form["data_schema"].schema} == {"monitored_entities"}
    step = await hass.config_entries.options.async_configure(
        form["flow_id"], {"monitored_entities": E[:2]}
    )
    assert step["step_id"] == "resource_weights"
    saved = await hass.config_entries.options.async_configure(
        form["flow_id"], {E[0]: 9, E[1]: 4}
    )
    assert saved["type"].value == "create_entry"
    await hass.async_block_till_done()
    manager = hass.data[DOMAIN][entry.entry_id].manager
    assert manager.entity_weights == {E[0]: 9, E[1]: 4}
    assert manager.max_active == 15
    assert manager.strategy == "priority_fifo"
    assert manager.recurrence_mode == "count"
    assert manager.allocation_mode == "backfill"


async def test_capacity_edit_does_not_ask_for_weights_unless_needed(hass: HomeAssistant):
    entry = await setup_entry(hass)
    form = await select_category(hass, entry, "capacity")
    result = await hass.config_entries.options.async_configure(
        form["flow_id"], {"capacity_mode": "weighted", "max_active": 20}
    )
    assert result["type"].value == "create_entry"
    await hass.async_block_till_done()
    manager = hass.data[DOMAIN][entry.entry_id].manager
    assert manager.max_active == 20
    assert manager.entity_weights == {E[0]: 10, E[1]: 5}
    form = await select_category(hass, entry, "capacity")
    step = await hass.config_entries.options.async_configure(
        form["flow_id"], {"capacity_mode": "weighted", "max_active": 8}
    )
    assert step["step_id"] == "capacity_weights"
    committed = await hass.config_entries.options.async_configure(
        form["flow_id"], {E[0]: 8, E[1]: 5}
    )
    assert committed["type"].value == "create_entry"
    await hass.async_block_till_done()
    assert hass.data[DOMAIN][entry.entry_id].manager.max_active == 8
    assert hass.data[DOMAIN][entry.entry_id].manager.entity_weights == {E[0]: 8, E[1]: 5}


async def test_guided_first_setup_covers_all_policy_sections(hass: HomeAssistant):
    assert await async_setup_component(hass, DOMAIN, {})
    flow = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    assert flow["type"].value == "form"
    assert {m.schema for m in flow["data_schema"].schema} == {"name", "monitored_entities"}
    step = await hass.config_entries.flow.async_configure(
        flow["flow_id"], {"name": "New guided queue", "monitored_entities": E[:2]}
    )
    assert step["step_id"] == "setup_capacity"
    step = await hass.config_entries.flow.async_configure(
        flow["flow_id"], {"capacity_mode": "weighted", "max_active": 15}
    )
    assert step["step_id"] == "setup_scheduling"
    step = await hass.config_entries.flow.async_configure(
        flow["flow_id"], {"strategy": "priority_fifo", "allocation_mode": "backfill"}
    )
    assert step["step_id"] == "setup_strategy"
    step = await hass.config_entries.flow.async_configure(
        flow["flow_id"], {"priority_order": "lowest_first"}
    )
    assert step["step_id"] == "setup_recurrence"
    step = await hass.config_entries.flow.async_configure(
        flow["flow_id"], {"recurrence_mode": "count"}
    )
    assert step["step_id"] == "weights"
    entry = await hass.config_entries.flow.async_configure(
        flow["flow_id"], {E[0]: 10, E[1]: 5}
    )
    assert entry["type"].value == "create_entry"
    assert entry["data"]["max_active"] == 15
    assert entry["data"]["strategy_config"] == {"priority_order": "lowest_first"}
    assert entry["data"]["entity_weights"] == {E[0]: 10, E[1]: 5}
    assert entry["data"]["allocation_mode"] == "backfill"
    assert entry["data"]["recurrence_mode"] == "count"
