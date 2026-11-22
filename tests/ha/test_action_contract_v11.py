"""v1.1 public HA action/sensor/event compatibility and isolation contracts."""

from unittest.mock import AsyncMock, patch

import pytest

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.setup import async_setup_component
from pytest_homeassistant.common import MockConfigEntry

DOMAIN = "resource_queue_manager"
GRANTED_EVENT = "resource_queue_manager_slot_granted"


async def setup_entry(
    hass: HomeAssistant,
    title: str,
    entities: tuple[str, ...],
    *,
    capacity_mode: str = "classic",
    recurrence_mode: str = "ignore",
    capacity: int = 2,
    weights: dict[str, int] | None = None,
) -> MockConfigEntry:
    assert await async_setup_component(hass, DOMAIN, {})
    entry = MockConfigEntry(
        domain=DOMAIN,
        title=title,
        data={
            "max_active": capacity,
            "capacity_mode": capacity_mode,
            "recurrence_mode": recurrence_mode,
            "entity_weights": weights or {},
            "strategy": "fifo",
            "strategy_config": {},
            "monitored_entities": list(entities),
        },
    )
    entry.add_to_hass(hass)
    for entity in entities:
        hass.states.async_set(entity, "off")
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def call_action(hass: HomeAssistant, action: str, **data):
    await hass.services.async_call(DOMAIN, action, data, blocking=True)
    await hass.async_block_till_done()


def state(hass: HomeAssistant, name: str):
    result = hass.states.get(name)
    assert result is not None, name
    return result


async def test_classic_legacy_yaml_stays_valid_and_metrics_stay_slots(hass: HomeAssistant):
    entry = await setup_entry(
        hass, "Legacy Contract", ("light.classic_a", "light.classic_b"),
        capacity=1,
    )
    observed = []
    hass.bus.async_listen(GRANTED_EVENT, lambda event: observed.append(event.data))
    await call_action(hass, "resume")  # One entry: no config_entry_id necessary.
    await call_action(hass, "request", resource_id="a", entity_id="light.classic_a")
    await call_action(hass, "request", resource_id="b", entity_id="light.classic_b")

    attrs = state(hass, "sensor.legacy_contract_available").attributes
    assert state(hass, "sensor.legacy_contract_available").state == "0"
    assert attrs["capacity_mode"] == "classic"
    assert attrs["capacity_unit"] == "slots"
    assert attrs["capacity_total"] == 1
    assert attrs["capacity_used"] == 1
    assert attrs["capacity_remaining"] == 0
    assert attrs["effective_weights"] == {"a": 1, "b": 1}
    assert attrs["active"] == ["a"]
    assert attrs["waiting"] == ["b"]
    assert observed[0]["resource_id"] == "a"
    assert observed[0]["occurrences"] == 1
    assert observed[0]["capacity_mode"] == "classic"
    assert observed[0]["effective_weight"] == 1
    assert observed[0]["config_entry_id"] == entry.entry_id


async def test_weighted_ha_units_and_grant_count_survive_head_of_line(hass: HomeAssistant):
    entities = ("light.unit_a", "light.unit_b", "light.unit_c")
    entry = await setup_entry(
        hass, "Unit Contract", entities,
        capacity_mode="weighted", recurrence_mode="count",
        capacity=10,
        weights={entities[0]: 7, entities[1]: 5, entities[2]: 2},
    )
    events = []
    hass.bus.async_listen(GRANTED_EVENT, lambda event: events.append(event.data))
    await call_action(hass, "resume", config_entry_id=entry.entry_id)
    await call_action(
        hass, "request", config_entry_id=entry.entry_id,
        resource_id="a", entity_id=entities[0],
    )
    await call_action(
        hass, "request", config_entry_id=entry.entry_id,
        resource_id="b", entity_id=entities[1],
    )
    await call_action(
        hass, "request", config_entry_id=entry.entry_id,
        resource_id="c", entity_id=entities[2],
    )
    await call_action(
        hass, "request", config_entry_id=entry.entry_id,
        resource_id="b", entity_id=entities[1],
    )
    attrs = state(hass, "sensor.unit_contract_available").attributes
    assert state(hass, "sensor.unit_contract_available").state == "3"
    assert attrs["capacity_unit"] == "units"
    assert attrs["capacity_total"] == 10
    assert attrs["capacity_used"] == 7
    assert attrs["capacity_remaining"] == 3
    assert attrs["active"] == ["a"]
    assert attrs["waiting"] == ["b", "c"]
    assert attrs["effective_weights"] == {"a": 7, "b": 5, "c": 2}
    assert attrs["occurrence_counts"] == {"a": 1, "b": 2, "c": 1}
    # Even though c would fit the remaining 3 units, b blocks it.
    assert [event["resource_id"] for event in events] == ["a"]

    await call_action(
        hass, "release", config_entry_id=entry.entry_id, resource_id="a"
    )
    assert [event["resource_id"] for event in events] == ["a", "b", "c"]
    assert events[1]["occurrences"] == 2
    assert events[1]["effective_weight"] == 5
    assert events[1]["capacity_mode"] == "weighted"
    assert events[1]["config_entry_id"] == entry.entry_id
    assert state(hass, "sensor.unit_contract_available").state == "3"


async def test_invalid_weight_rejected_without_mutation_or_event(hass: HomeAssistant):
    entities = ("light.invalid_a", "light.invalid_b")
    entry = await setup_entry(
        hass, "Invalid Contract", entities, capacity_mode="weighted",
        recurrence_mode="count", capacity=10,
        weights={entities[0]: 10, entities[1]: 4},
    )
    events = []
    hass.bus.async_listen(GRANTED_EVENT, lambda event: events.append(event.data))
    await call_action(hass, "resume")
    await call_action(hass, "request", resource_id="busy", entity_id=entities[0])
    await call_action(
        hass, "request", resource_id="pending", entity_id=entities[1],
        engine_data={"weight": 3},
    )
    for invalid in ({"weight": 0}, {"weight": True}, {"weight": 11},
                    {"weight": 1.5}, {"weight": 4, "unknown": 9}):
        with pytest.raises(HomeAssistantError):
            await call_action(
                hass, "request", resource_id="pending", entity_id=entities[1],
                engine_data=invalid,
            )
    with pytest.raises(HomeAssistantError, match="different effective weight"):
        await call_action(
            hass, "request", resource_id="pending", entity_id=entities[1],
            engine_data={"weight": 4},
        )
    manager = hass.data[DOMAIN][entry.entry_id].manager
    assert manager.snapshot().waiting == ("pending",)
    assert manager.queue.occurrences("pending") == 1
    assert manager.queue.effective_weight("pending") == 3
    assert [event["resource_id"] for event in events] == ["busy"]


async def test_isolated_mixed_queues_require_entry_id(hass: HomeAssistant):
    classic = await setup_entry(
        hass, "Classic Queue", ("light.classic_only",), capacity=1
    )
    weighted = await setup_entry(
        hass, "Weighted Queue", ("light.weighted_only",),
        capacity_mode="weighted", recurrence_mode="count",
        capacity=10, weights={"light.weighted_only": 6},
    )
    events = []
    hass.bus.async_listen(GRANTED_EVENT, lambda event: events.append(event.data))
    with pytest.raises(HomeAssistantError, match="config_entry_id"):
        await call_action(hass, "resume")
    for entry in (classic, weighted):
        await call_action(hass, "resume", config_entry_id=entry.entry_id)
    with pytest.raises(HomeAssistantError, match="config_entry_id"):
        await call_action(
            hass, "request", resource_id="wrong", entity_id="light.classic_only"
        )
    await call_action(
        hass, "request", config_entry_id=classic.entry_id,
        resource_id="classic", entity_id="light.classic_only",
    )
    await call_action(
        hass, "request", config_entry_id=weighted.entry_id,
        resource_id="weighted", entity_id="light.weighted_only",
        engine_data={"weight": 4},
    )
    assert len(events) == 2
    assert {event["config_entry_id"] for event in events} == {
        classic.entry_id, weighted.entry_id
    }
    assert events[0]["capacity_mode"] == "classic"
    assert events[1]["capacity_mode"] == "weighted"
    assert events[1]["effective_weight"] == 4
    assert state(hass, "sensor.classic_queue_active").state == "1"
    assert state(hass, "sensor.weighted_queue_active").state == "1"
    assert state(hass, "sensor.classic_queue_available").state == "0"
    assert state(hass, "sensor.weighted_queue_available").state == "6"


async def test_grant_event_only_after_store_save_and_never_after_failure(
    hass: HomeAssistant,
):
    entry = await setup_entry(hass, "Durability Queue", ("light.durable",), capacity=1)
    runtime = hass.data[DOMAIN][entry.entry_id]
    order = []
    events = []
    hass.bus.async_listen(
        GRANTED_EVENT,
        lambda event: (order.append("event"), events.append(event.data)),
    )
    original_save = runtime.store.async_save

    async def recording_save(data):
        order.append("save")
        await original_save(data)

    await call_action(hass, "resume")
    with patch.object(runtime.store, "async_save", side_effect=recording_save):
        await call_action(
            hass, "request", resource_id="durable", entity_id="light.durable"
        )
    assert order == ["save", "event"]
    assert events[-1]["resource_id"] == "durable"

    await call_action(hass, "release", resource_id="durable")
    order.clear()
    events.clear()
    with patch.object(
        runtime.store, "async_save", new_callable=AsyncMock,
        side_effect=OSError("storage unavailable"),
    ):
        with pytest.raises(HomeAssistantError, match="Unable to save"):
            await call_action(
                hass, "request", resource_id="unsafe", entity_id="light.durable"
            )
    assert not events
    assert runtime.manager.paused
