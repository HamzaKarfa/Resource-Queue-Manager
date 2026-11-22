"""End-to-end tests through Home Assistant's config entries, services and states.

Unlike isolated FIFO tests, these tests exercise the actual Home Assistant
adapter, its sensor entities and its persistence using a local test instance.
No physical entities are connected or commanded.
"""

import asyncio

import pytest

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.setup import async_setup_component
from homeassistant.helpers.storage import Store
from pytest_homeassistant.common import MockConfigEntry

DOMAIN = "resource_queue_manager"


@pytest.fixture
async def queue_entry(hass: HomeAssistant) -> MockConfigEntry:
    """Load one integration entry in an isolated Home Assistant test instance."""
    assert await async_setup_component(hass, DOMAIN, {})
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Resource Queue Manager (FIFO)",
        unique_id=DOMAIN,
        data={"max_active": 3},
        options={"monitored_entities": [f"light.relay_{i}" for i in range(1, 6)]},
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    for i in range(1, 6):
        hass.states.async_set(f"light.relay_{i}", "off")
    await hass.async_block_till_done()
    return entry


async def action(hass: HomeAssistant, operation: str, **data: str) -> None:
    """Call the public integration action with blocking=True."""
    await hass.services.async_call(DOMAIN, operation, data, blocking=True)
    await hass.async_block_till_done()


async def options_form(hass: HomeAssistant, entry: MockConfigEntry, category: str):
    """Navigate the actual four-category HA Configure menu."""
    menu = await hass.config_entries.options.async_init(entry.entry_id)
    assert menu["type"].value == "menu"
    form = await hass.config_entries.options.async_configure(
        menu["flow_id"], {"next_step_id": category}
    )
    assert form["type"].value == "form"
    return form


async def guided_setup_to_policy(
    hass: HomeAssistant, flow: dict, *,
    name: str, capacity: int, strategy: str,
    monitored: list[str] | None = None, capacity_mode: str = "classic",
    allocation_mode: str = "strict",
):
    """Drive guided setup to its strategy-specific or recurrence step."""
    step = await hass.config_entries.flow.async_configure(
        flow["flow_id"], {"name": name, "monitored_entities": monitored or []}
    )
    assert step["step_id"] == "setup_capacity"
    step = await hass.config_entries.flow.async_configure(
        flow["flow_id"], {"capacity_mode": capacity_mode, "max_active": capacity}
    )
    assert step["step_id"] == "setup_scheduling"
    return await hass.config_entries.flow.async_configure(
        flow["flow_id"],
        {"strategy": strategy, "allocation_mode": allocation_mode},
    )


async def request(hass: HomeAssistant, index: int) -> None:
    await action(
        hass,
        "request",
        resource_id=f"h{index}",
        entity_id=f"light.relay_{index}",
    )


def sensor(hass: HomeAssistant, metric: str):
    """Read the state through Home Assistant, not coordinator internals."""
    state = hass.states.get(f"sensor.resource_queue_{metric}")
    assert state is not None, f"Missing sensor.resource_queue_{metric}"
    return state


async def test_start_paused_then_resume(
    hass: HomeAssistant, queue_entry: MockConfigEntry
) -> None:
    """No allocation is possible before an explicit resume."""
    assert sensor(hass, "status").state == "paused"
    assert sensor(hass, "available").state == "0"
    with pytest.raises(HomeAssistantError):
        await request(hass, 1)
    await action(hass, "resume")
    assert sensor(hass, "status").state == "ready"
    assert sensor(hass, "available").state == "3"


async def test_concurrent_requests_do_not_overallocate(
    hass: HomeAssistant, queue_entry: MockConfigEntry
) -> None:
    """A burst of five service calls must never reserve more than three slots."""
    await action(hass, "resume")
    await asyncio.gather(*(request(hass, i) for i in range(1, 6)))
    assert sensor(hass, "active").state == "3"
    assert sensor(hass, "waiting").state == "2"
    assert sensor(hass, "available").state == "0"
    assert len(sensor(hass, "active").attributes["active"]) == 3


async def test_release_promotes_oldest_waiting(
    hass: HomeAssistant, queue_entry: MockConfigEntry
) -> None:
    """FIFOs only admit a waiting resource after a confirmed OFF release."""
    await action(hass, "resume")
    for i in range(1, 6):
        await request(hass, i)

    assert sensor(hass, "waiting").attributes["waiting"] == ["h4", "h5"]
    await action(hass, "release", resource_id="h2")
    assert sensor(hass, "active").attributes["active"] == ["h1", "h3", "h4"]
    assert sensor(hass, "waiting").attributes["waiting"] == ["h5"]


async def test_reload_restores_order_without_regrant(
    hass: HomeAssistant, queue_entry: MockConfigEntry
) -> None:
    """Reload the real config entry and verify its persistent state and pause."""
    await action(hass, "resume")
    for i in range(1, 6):
        await request(hass, i)

    before_active = sensor(hass, "active").attributes["active"]
    before_waiting = sensor(hass, "waiting").attributes["waiting"]

    assert await hass.config_entries.async_reload(queue_entry.entry_id)
    await hass.async_block_till_done()

    assert sensor(hass, "status").state == "paused"
    assert sensor(hass, "available").state == "0"
    assert sensor(hass, "active").attributes["active"] == before_active
    assert sensor(hass, "waiting").attributes["waiting"] == before_waiting

    await action(hass, "resume")
    assert sensor(hass, "status").state == "ready"
    await action(hass, "release", resource_id="h1")
    assert sensor(hass, "active").attributes["active"] == ["h2", "h3", "h4"]
    assert sensor(hass, "waiting").attributes["waiting"] == ["h5"]


async def test_recovery_refuses_unavailable_known_relay(
    hass: HomeAssistant, queue_entry: MockConfigEntry
) -> None:
    """A missing Zigbee report must block manual recovery."""
    await action(hass, "resume")
    await request(hass, 1)
    hass.states.async_set("light.relay_1", "unavailable")
    await hass.async_block_till_done()

    assert await hass.config_entries.async_reload(queue_entry.entry_id)
    await hass.async_block_till_done()

    with pytest.raises(HomeAssistantError):
        await action(hass, "resume")
    assert sensor(hass, "status").state == "paused"
    assert sensor(hass, "active").state == "1"


async def test_recovery_refuses_orphaned_on_relay(
    hass: HomeAssistant, queue_entry: MockConfigEntry
) -> None:
    """A known ON entity without reservation is inconsistent."""
    await action(hass, "resume")
    await request(hass, 1)
    await action(hass, "release", resource_id="h1")
    hass.states.async_set("light.relay_1", "on")
    await hass.async_block_till_done()

    assert await hass.config_entries.async_reload(queue_entry.entry_id)
    await hass.async_block_till_done()

    with pytest.raises(HomeAssistantError):
        await action(hass, "resume")
    assert sensor(hass, "status").state == "paused"
    assert sensor(hass, "available").state == "0"



async def test_options_form_reconfigures_supervised_relays(
    hass: HomeAssistant, queue_entry: MockConfigEntry
) -> None:
    """The Configure UI persists selection and reloads the entry paused."""
    form = await options_form(hass, queue_entry, "resources")
    assert form["type"] is not None
    result = await hass.config_entries.options.async_configure(
        form["flow_id"], {"monitored_entities": ["light.relay_1"]}
    )
    assert result["type"].value == "create_entry"
    await hass.async_block_till_done()

    assert queue_entry.options["monitored_entities"] == ["light.relay_1"]
    assert sensor(hass, "status").state == "paused"
    assert sensor(hass, "status").attributes["monitored_entities"] == [
        "light.relay_1"
    ]

    hass.states.async_set("light.relay_3", "on")
    await hass.async_block_till_done()
    await action(hass, "resume")
    assert sensor(hass, "status").state == "ready"
    await request(hass, 1)
    assert sensor(hass, "active").state == "1"
    with pytest.raises(HomeAssistantError, match="not supervised"):
        await request(hass, 3)


async def test_options_form_rejects_removal_of_active_reservation(
    hass: HomeAssistant, queue_entry: MockConfigEntry
) -> None:
    """An existing slot must not vanish when a entity is deselected."""
    await action(hass, "resume")
    await request(hass, 3)

    form = await options_form(hass, queue_entry, "resources")
    result = await hass.config_entries.options.async_configure(
        form["flow_id"], {"monitored_entities": ["light.relay_1"]}
    )
    assert result["type"].value == "form"
    assert result["errors"]["base"] == "entities_in_use"
    assert "light.relay_3" in queue_entry.options["monitored_entities"]
    assert sensor(hass, "active").state == "1"


async def test_options_form_rejects_removal_of_waiting_request(
    hass: HomeAssistant, queue_entry: MockConfigEntry
) -> None:
    """A waiting queue entry is just as protected as an active booking."""
    await action(hass, "resume")
    for i in range(1, 5):
        await request(hass, i)
    assert sensor(hass, "waiting").state == "1"

    form = await options_form(hass, queue_entry, "resources")
    result = await hass.config_entries.options.async_configure(
        form["flow_id"], {"monitored_entities": [
            "light.relay_1", "light.relay_2", "light.relay_3"
        ]}
    )
    assert result["errors"]["base"] == "entities_in_use"


async def test_legacy_stored_history_ignored_after_explicit_selection(
    hass: HomeAssistant, queue_entry: MockConfigEntry
) -> None:
    """An old released test entity must not prevent migration to one resource."""
    runtime = hass.data[DOMAIN][queue_entry.entry_id]
    snapshot = runtime.manager.export_state()
    snapshot["known_relays"] = {"old_ch3": "light.relay_3"}
    await runtime.store.async_save(snapshot)

    form = await options_form(hass, queue_entry, "resources")
    result = await hass.config_entries.options.async_configure(
        form["flow_id"], {"monitored_entities": ["light.relay_1"]}
    )
    assert result["type"].value == "create_entry"
    await hass.async_block_till_done()
    hass.states.async_set("light.relay_3", "on")
    await hass.async_block_till_done()
    await action(hass, "resume")
    assert sensor(hass, "status").state == "ready"


async def test_edit_max_slots_from_options_and_persist(
    hass: HomeAssistant, queue_entry: MockConfigEntry
) -> None:
    """Changing 3 to 2 preserves the configuration across reloads."""
    form = await options_form(hass, queue_entry, "capacity")
    result = await hass.config_entries.options.async_configure(
        form["flow_id"],
        {
            "max_active": 2,
            "monitored_entities": [f"light.relay_{i}" for i in range(1, 6)],
        },
    )
    assert result["type"].value == "create_entry"
    await hass.async_block_till_done()
    assert queue_entry.options["max_active"] == 2
    assert sensor(hass, "status").state == "paused"
    assert sensor(hass, "status").attributes["max_active"] == 2

    await action(hass, "resume")
    assert sensor(hass, "available").state == "2"
    for i in range(1, 4):
        await request(hass, i)
    assert sensor(hass, "active").attributes["active"] == ["h1", "h2"]
    assert sensor(hass, "waiting").attributes["waiting"] == ["h3"]

    # Opening Configure again must preserve the edited max as its default.
    reopened = await options_form(hass, queue_entry, "capacity")
    assert reopened["type"].value == "form"


async def test_options_reject_limit_below_existing_active_reservations(
    hass: HomeAssistant, queue_entry: MockConfigEntry
) -> None:
    await action(hass, "resume")
    for i in range(1, 4):
        await request(hass, i)

    flow = await options_form(hass, queue_entry, "capacity")
    result = await hass.config_entries.options.async_configure(
        flow["flow_id"],
        {
            "max_active": 2,
            "monitored_entities": [f"light.relay_{i}" for i in range(1, 6)],
        },
    )
    assert result["type"].value == "form"
    assert result["errors"]["base"] == "max_active_below_reserved"
    assert queue_entry.options.get("max_active") is None
    assert sensor(hass, "active").state == "3"


async def test_increase_max_with_waiters_promotes_only_on_resume(
    hass: HomeAssistant, queue_entry: MockConfigEntry
) -> None:
    await action(hass, "resume")
    for i in range(1, 6):
        await request(hass, i)
    assert sensor(hass, "waiting").attributes["waiting"] == ["h4", "h5"]
    assert sensor(hass, "active").attributes["active"] == ["h1", "h2", "h3"]

    flow = await options_form(hass, queue_entry, "capacity")
    result = await hass.config_entries.options.async_configure(
        flow["flow_id"],
        {
            "max_active": 4,
            "monitored_entities": [f"light.relay_{i}" for i in range(1, 6)],
        },
    )
    assert result["type"].value == "create_entry"
    await hass.async_block_till_done()
    assert sensor(hass, "status").state == "paused"
    assert sensor(hass, "active").attributes["active"] == ["h1", "h2", "h3"]
    assert sensor(hass, "waiting").attributes["waiting"] == ["h4", "h5"]
    assert sensor(hass, "status").attributes["max_active"] == 4

    await action(hass, "resume")
    assert sensor(hass, "active").attributes["active"] == ["h1", "h2", "h3", "h4"]
    assert sensor(hass, "waiting").attributes["waiting"] == ["h5"]
    assert sensor(hass, "available").state == "0"


async def test_capacity_forms_use_number_box_not_slider(
    hass: HomeAssistant, queue_entry: MockConfigEntry
) -> None:
    """Setup and Configure both expose the native numeric box selector."""
    from homeassistant.helpers.selector import NumberSelector

    def assert_number_box(schema) -> None:
        values = {
            marker.schema: field
            for marker, field in schema.schema.items()
        }
        selector = values["max_active"]
        assert isinstance(selector, NumberSelector)
        assert selector.config["mode"] == "box"
        assert selector.config["min"] == 1
        assert selector.config["max"] == 100000
        assert selector.config["step"] == 1

    options = await options_form(hass, queue_entry, "capacity")
    assert options["type"].value == "form"
    assert_number_box(options["data_schema"])


async def test_initial_setup_uses_number_box(hass: HomeAssistant) -> None:
    """The first setup flow shows a numeric input before an entry exists."""
    from homeassistant.helpers.selector import NumberSelector

    assert await async_setup_component(hass, DOMAIN, {})
    setup = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}
    )
    assert setup["type"].value == "form"
    selector = next(
        field for marker, field in setup["data_schema"].schema.items()
        if marker.schema == "max_active"
    )
    assert isinstance(selector, NumberSelector)
    assert selector.config["mode"] == "box"
    assert selector.config["min"] == 1
    assert selector.config["max"] == 100000


async def test_multi_instance_routes_and_isolates_fifo_lifo_queues(
    hass: HomeAssistant, queue_entry: MockConfigEntry
) -> None:
    """Independent entry IDs must never share reservations or scheduling policy."""
    for index in range(1, 4):
        hass.states.async_set(f"light.garden_{index}", "off")
    await hass.async_block_till_done()
    other = MockConfigEntry(
        domain=DOMAIN,
        title="Garden",
        data={"name": "Garden", "max_active": 1, "strategy": "lifo"},
        options={
            "strategy": "lifo",
            "monitored_entities": [
                "light.garden_1",
                "light.garden_2",
                "light.garden_3",
            ],
        },
    )
    other.add_to_hass(hass)
    assert await hass.config_entries.async_setup(other.entry_id)
    await hass.async_block_till_done()
    assert hass.data[DOMAIN][other.entry_id].manager.strategy == "lifo"

    with pytest.raises(HomeAssistantError, match="config_entry_id"):
        await action(hass, "resume")
    await action(hass, "resume", config_entry_id=queue_entry.entry_id)
    await action(hass, "resume", config_entry_id=other.entry_id)

    await action(
        hass, "request", config_entry_id=queue_entry.entry_id,
        resource_id="heating", entity_id="light.relay_1"
    )
    for index in range(1, 4):
        await action(
            hass, "request", config_entry_id=other.entry_id,
            resource_id=f"garden{index}", entity_id=f"light.garden_{index}"
        )

    heating = hass.data[DOMAIN][queue_entry.entry_id].manager
    garden = hass.data[DOMAIN][other.entry_id].manager
    assert heating.snapshot().active == ("heating",)
    assert garden.snapshot().active == ("garden1",)
    assert garden.snapshot().waiting == ("garden3", "garden2")

    await action(
        hass, "release", config_entry_id=other.entry_id, resource_id="garden1"
    )
    assert garden.snapshot().active == ("garden3",)
    assert garden.snapshot().waiting == ("garden2",)
    assert heating.snapshot().active == ("heating",)

    assert await hass.config_entries.async_reload(other.entry_id)
    await hass.async_block_till_done()
    restored = hass.data[DOMAIN][other.entry_id].manager
    assert restored.paused
    assert restored.strategy == "lifo"
    assert restored.snapshot().active == ("garden3",)
    assert restored.snapshot().waiting == ("garden2",)


async def test_options_reject_strategy_change_with_pending_work(
    hass: HomeAssistant, queue_entry: MockConfigEntry
) -> None:
    await action(hass, "resume")
    await request(hass, 1)
    form = await options_form(hass, queue_entry, "scheduling")
    result = await hass.config_entries.options.async_configure(
        form["flow_id"],
        {
            "max_active": 3,
            "strategy": "lifo",
            "monitored_entities": [f"light.relay_{i}" for i in range(1, 6)],
        },
    )
    assert result["type"].value == "form"
    assert result["errors"]["base"] == "strategy_in_use"
    assert hass.data[DOMAIN][queue_entry.entry_id].manager.strategy == "fifo"


async def test_second_config_flow_asks_for_name_and_strategy(
    hass: HomeAssistant, queue_entry: MockConfigEntry
) -> None:
    """Creating a second entry remains available with a legacy singleton loaded."""
    flow = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}
    )
    assert flow["type"].value == "form"
    fields = {marker.schema for marker in flow["data_schema"].schema}
    assert {"name", "max_active", "strategy", "monitored_entities"} <= fields


@pytest.fixture
def configured_test_strategy(monkeypatch):
    """Register a test-only plugin with real declarative configuration fields."""
    from custom_components.resource_queue_manager.strategies import (
        PROVIDERS,
        FifoStrategy,
        StrategyConfigField,
    )

    class SampleProvider:
        key = "sample_policy"
        label = "Sample configurable policy"
        description = "Exercise native strategy-specific form steps."
        config_fields = (
            StrategyConfigField(
                key="threshold", label="Threshold", kind="number",
                required=True, minimum=1, maximum=10
            ),
            StrategyConfigField(
                key="flavor", label="Flavor", kind="select",
                choices=("one", "two"), default="one"
            ),
        )

        def create(self, config=None):
            assert config is not None
            assert 1 <= config["threshold"] <= 10
            return FifoStrategy()

    monkeypatch.setitem(PROVIDERS, "sample_policy", SampleProvider())


async def test_config_flow_renders_provider_options_and_persists_them(
    hass: HomeAssistant, configured_test_strategy
) -> None:
    """A strategy can supply setup fields without modifying config_flow.py."""
    assert await async_setup_component(hass, DOMAIN, {})
    first = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}
    )
    assert first["type"].value == "form"
    next_step = await hass.config_entries.flow.async_configure(
        first["flow_id"],
        {
            "name": "Configurable Queue",
            "max_active": 1,
            "strategy": "sample_policy",
            "monitored_entities": [],
        },
    )
    assert next_step["type"].value == "form"
    assert next_step["step_id"] == "strategy"
    fields = {marker.schema for marker in next_step["data_schema"].schema}
    assert fields == {"threshold", "flavor"}

    created = await hass.config_entries.flow.async_configure(
        first["flow_id"], {"threshold": 5, "flavor": "two"}
    )
    assert created["type"].value == "create_entry"
    assert created["data"]["strategy_config"] == {
        "threshold": 5, "flavor": "two"
    }


async def test_options_flow_updates_provider_settings_and_recovers(
    hass: HomeAssistant, queue_entry: MockConfigEntry, configured_test_strategy
) -> None:
    """Configuration changes run through an extra provider-specific step."""
    flow = await options_form(hass, queue_entry, "scheduling")
    selected = await hass.config_entries.options.async_configure(
        flow["flow_id"],
        {
            "max_active": 3,
            "strategy": "sample_policy",
            "monitored_entities": [f"light.relay_{i}" for i in range(1, 6)],
        },
    )
    assert selected["type"].value == "form"
    assert selected["step_id"] == "strategy"
    finished = await hass.config_entries.options.async_configure(
        flow["flow_id"], {"threshold": 3, "flavor": "one"}
    )
    assert finished["type"].value == "create_entry"
    await hass.async_block_till_done()
    assert queue_entry.options["strategy"] == "sample_policy"
    assert queue_entry.options["strategy_config"] == {
        "threshold": 3, "flavor": "one"
    }
    runtime = hass.data[DOMAIN][queue_entry.entry_id].manager
    assert runtime.paused
    assert runtime.queue.strategy_config["threshold"] == 3


async def test_strategy_specific_options_cannot_change_with_active_booking(
    hass: HomeAssistant, queue_entry: MockConfigEntry, configured_test_strategy
) -> None:
    """A queue must not lose active work when a plugin setting changes."""
    initial = await options_form(hass, queue_entry, "scheduling")
    strategy_step = await hass.config_entries.options.async_configure(
        initial["flow_id"],
        {
            "max_active": 3,
            "strategy": "sample_policy",
            "monitored_entities": [f"light.relay_{i}" for i in range(1, 6)],
        },
    )
    assert strategy_step["step_id"] == "strategy"
    saved = await hass.config_entries.options.async_configure(
        initial["flow_id"], {"threshold": 3, "flavor": "one"}
    )
    assert saved["type"].value == "create_entry"
    await hass.async_block_till_done()

    await action(hass, "resume")
    await request(hass, 1)

    form = await options_form(hass, queue_entry, "scheduling")
    options = await hass.config_entries.options.async_configure(
        form["flow_id"],
        {
            "max_active": 3,
            "strategy": "sample_policy",
            "monitored_entities": [f"light.relay_{i}" for i in range(1, 6)],
        },
    )
    assert options["step_id"] == "strategy"
    rejected = await hass.config_entries.options.async_configure(
        form["flow_id"], {"threshold": 4, "flavor": "one"}
    )
    assert rejected["type"].value == "form"
    assert rejected["errors"]["base"] == "strategy_in_use"
    manager = hass.data[DOMAIN][queue_entry.entry_id].manager
    assert manager.queue.strategy_config == {"threshold": 3, "flavor": "one"}
    assert manager.snapshot().active == ("h1",)


async def test_plugin_request_metadata_service_persists_through_restart(
    hass: HomeAssistant, monkeypatch
) -> None:
    """Provider fields travel through the public service API and survive reload."""
    from custom_components.resource_queue_manager.strategies import (
        PROVIDERS, FifoStrategy, StrategyConfigField
    )

    class MetadataProvider:
        key = "meta_test"
        label = "Metadata demo"
        description = "Test-only provider"
        config_fields = ()
        request_fields = (
            StrategyConfigField(
                key="priority", label="Priority", kind="number",
                required=True, minimum=1, maximum=10
            ),
        )

        def create(self, config=None):
            return FifoStrategy()

    monkeypatch.setitem(PROVIDERS, "meta_test", MetadataProvider())
    assert await async_setup_component(hass, DOMAIN, {})
    for index in (1, 2):
        hass.states.async_set(f"light.metadata_{index}", "off")
    entry = MockConfigEntry(
        domain=DOMAIN, title="Metadata queue",
        data={"max_active": 1, "strategy": "meta_test"},
        options={"monitored_entities": ["light.metadata_1", "light.metadata_2"]},
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    await action(hass, "resume", config_entry_id=entry.entry_id)
    await action(
        hass, "request", config_entry_id=entry.entry_id,
        resource_id="first", entity_id="light.metadata_1",
        strategy_data={"priority": 3}
    )
    await action(
        hass, "request", config_entry_id=entry.entry_id,
        resource_id="second", entity_id="light.metadata_2",
        strategy_data={"priority": 8}
    )
    manager = hass.data[DOMAIN][entry.entry_id].manager
    assert manager.export_state()["request_data"] == {
        "first": {"priority": 3}, "second": {"priority": 8}
    }
    with pytest.raises(HomeAssistantError):
        await action(
            hass, "request", config_entry_id=entry.entry_id,
            resource_id="second", entity_id="light.metadata_2",
            strategy_data={"priority": 11}
        )
    with pytest.raises(HomeAssistantError):
        await action(
            hass, "request", config_entry_id=entry.entry_id,
            resource_id="second", entity_id="light.metadata_2",
            strategy_data={"priority": 4}
        )
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    restored = hass.data[DOMAIN][entry.entry_id].manager
    assert restored.paused
    assert restored.snapshot().active == ("first",)
    assert restored.snapshot().waiting == ("second",)
    assert restored.export_state()["request_data"] == {
        "first": {"priority": 3}, "second": {"priority": 8}
    }
    await action(hass, "resume", config_entry_id=entry.entry_id)
    await action(
        hass, "release", config_entry_id=entry.entry_id,
        resource_id="first"
    )
    assert restored.snapshot().active == ("second",)
    assert restored.export_state()["request_data"] == {
        "second": {"priority": 8}
    }


async def test_priority_fifo_config_flow_uses_provider_fields(
    hass: HomeAssistant, queue_entry: MockConfigEntry
) -> None:
    """New provider appears in selection and declares its own configuration form."""
    flow = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}
    )
    assert flow["type"].value == "form"
    step = await hass.config_entries.flow.async_configure(
        flow["flow_id"],
        {
            "name": "Priority Test",
            "max_active": 1,
            "strategy": "priority_fifo",
            "monitored_entities": [],
        },
    )
    assert step["type"].value == "form"
    assert step["step_id"] == "strategy"
    fields = {marker.schema for marker in step["data_schema"].schema}
    assert fields == {"priority_order"}

    created = await hass.config_entries.flow.async_configure(
        flow["flow_id"], {"priority_order": "lowest_first"}
    )
    assert created["type"].value == "create_entry"
    assert created["data"]["strategy"] == "priority_fifo"
    assert created["data"]["strategy_config"] == {
        "priority_order": "lowest_first"
    }


async def test_priority_fifo_ha_actions_keep_ties_and_survive_reload(
    hass: HomeAssistant, queue_entry: MockConfigEntry
) -> None:
    """Real service calls preserve priorities, FIFO ties and fail-closed restart."""
    options = await options_form(hass, queue_entry, "scheduling")
    strategy_form = await hass.config_entries.options.async_configure(
        options["flow_id"],
        {
            "max_active": 1,
            "strategy": "priority_fifo",
            "monitored_entities": [f"light.relay_{i}" for i in range(1, 6)],
        },
    )
    assert strategy_form["type"].value == "form"
    assert strategy_form["step_id"] == "strategy"
    chosen = await hass.config_entries.options.async_configure(
        options["flow_id"], {"priority_order": "highest_first"}
    )
    assert chosen["type"].value == "create_entry"
    await hass.async_block_till_done()
    manager = hass.data[DOMAIN][queue_entry.entry_id].manager
    assert manager.strategy == "priority_fifo"
    assert manager.queue.strategy_config == {
        "priority_order": "highest_first"
    }
    assert manager.paused

    await action(hass, "resume")
    for index, priority in ((1, 1), (2, 4), (3, 8), (4, 4), (5, 10)):
        await action(
            hass, "request",
            resource_id=f"h{index}",
            entity_id=f"light.relay_{index}",
            strategy_data={"priority": priority},
        )
    assert manager.snapshot().active == ("h1",)
    assert manager.snapshot().waiting == ("h5", "h3", "h2", "h4")

    with pytest.raises(HomeAssistantError):
        await action(
            hass, "request",
            resource_id="h2", entity_id="light.relay_2",
            strategy_data={"priority": 7},
        )

    assert await hass.config_entries.async_reload(queue_entry.entry_id)
    await hass.async_block_till_done()
    restored = hass.data[DOMAIN][queue_entry.entry_id].manager
    assert restored.paused
    assert restored.snapshot().waiting == ("h5", "h3", "h2", "h4")
    assert restored.export_state()["request_data"]["h5"] == {"priority": 10}
    await action(hass, "resume")
    await action(hass, "release", resource_id="h1")
    assert restored.snapshot().active == ("h5",)
    await action(hass, "release", resource_id="h5")
    assert restored.snapshot().active == ("h3",)


async def test_populated_v04_stored_queue_upgrades_in_place(
    hass: HomeAssistant, queue_entry: MockConfigEntry
) -> None:
    """Reload an actual HA entry from the old v0.4 storage schema."""
    await action(hass, "resume")
    for index in range(1, 6):
        await request(hass, index)

    before = hass.data[DOMAIN][queue_entry.entry_id].manager.export_state()
    legacy = {
        "active": before["active"],
        "waiting": before["waiting"],
        "max_active": before["max_active"],
        "bindings": before["bindings"],
    }
    # Simulate a populated v0.4 .storage file before v1's new fields existed.
    store = Store(hass, 1, f"{DOMAIN}.{queue_entry.entry_id}")
    await store.async_save(legacy)

    assert await hass.config_entries.async_reload(queue_entry.entry_id)
    await hass.async_block_till_done()
    restored = hass.data[DOMAIN][queue_entry.entry_id].manager
    assert restored.paused
    assert restored.strategy == "fifo"
    assert list(restored.snapshot().active) == legacy["active"]
    assert list(restored.snapshot().waiting) == legacy["waiting"]
    assert restored.export_state()["bindings"] == legacy["bindings"]
    assert restored.export_state()["request_data"] == {}

    await action(hass, "resume")
    await action(hass, "release", resource_id="h1")
    assert restored.snapshot().active == ("h2", "h3", "h4")
    assert restored.snapshot().waiting == ("h5",)


async def test_native_number_text_and_helpers_work_as_logical_resources(
    hass: HomeAssistant, queue_entry: MockConfigEntry
) -> None:
    """Native and helper entities share a capacity without unsafe ON/OFF assumptions."""
    for entity, state in (
        ("input_number.queue_target", "2"),
        ("input_text.queue_note", "hello"),
        ("number.native_target", "15"),
        ("text.native_note", ""),
        ("input_boolean.queue_gate", "off"),
    ):
        hass.states.async_set(entity, state)
    await hass.async_block_till_done()

    extra = MockConfigEntry(
        domain=DOMAIN, title="Logical tests",
        data={"name": "Logical tests", "max_active": 2, "strategy": "lifo"},
        options={"monitored_entities": [
            "input_number.queue_target", "input_text.queue_note",
            "number.native_target", "text.native_note", "input_boolean.queue_gate",
        ]},
    )
    extra.add_to_hass(hass)
    assert await hass.config_entries.async_setup(extra.entry_id)
    await hass.async_block_till_done()

    await action(hass, "resume", config_entry_id=extra.entry_id)
    for resource_id, entity_id in (
        ("a", "input_number.queue_target"),
        ("b", "input_text.queue_note"),
        ("c", "number.native_target"),
        ("d", "text.native_note"),
    ):
        await action(hass, "request", config_entry_id=extra.entry_id,
                     resource_id=resource_id, entity_id=entity_id)
    runtime = hass.data[DOMAIN][extra.entry_id]
    assert runtime.manager.snapshot().active == ("a", "b")
    assert runtime.manager.snapshot().waiting == ("d", "c")

    await action(hass, "release", config_entry_id=extra.entry_id, resource_id="a")
    assert runtime.manager.snapshot().active == ("b", "d")
    assert runtime.manager.snapshot().waiting == ("c",)

    hass.states.async_set("input_text.queue_note", "unavailable")
    await hass.async_block_till_done()
    with pytest.raises(HomeAssistantError, match="must be available"):
        await action(hass, "release", config_entry_id=extra.entry_id, resource_id="b")
    assert "b" in runtime.manager.snapshot().active

    hass.states.async_set("input_text.queue_note", "again")
    await hass.async_block_till_done()
    await action(hass, "release", config_entry_id=extra.entry_id, resource_id="b")

    # The existing heating queue remains isolated while generic resources run.
    assert hass.data[DOMAIN][queue_entry.entry_id].manager.snapshot().active == ()
    assert await hass.config_entries.async_reload(extra.entry_id)
    await hass.async_block_till_done()
    assert hass.data[DOMAIN][extra.entry_id].manager.paused


async def test_setup_form_entity_selector_accepts_all_domains(
    hass: HomeAssistant,
) -> None:
    """No hardcoded light/switch domain filter in the native HA entity picker."""
    from homeassistant.helpers.selector import EntitySelector

    assert await async_setup_component(hass, DOMAIN, {})
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}
    )
    field = next(
        value for key, value in result["data_schema"].schema.items()
        if key.schema == "monitored_entities"
    )
    assert isinstance(field, EntitySelector)
    assert "domain" not in field.config
    assert field.config["multiple"] is True
