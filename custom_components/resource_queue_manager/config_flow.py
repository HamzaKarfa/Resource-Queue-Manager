"""Config flow for independent Resource Queue Manager instances."""

from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.config_entries import ConfigEntry, OptionsFlowWithReload
from homeassistant.core import callback
from homeassistant.helpers.selector import (
    EntitySelector,
    EntitySelectorConfig,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)

from homeassistant.helpers.storage import Store

from .const import (
    CONF_MAX_ACTIVE,
    CONF_CAPACITY_MODE,
    CONF_ENTITY_WEIGHTS,
    CONF_MONITORED_ENTITIES,
    CONF_NAME,
    CONF_STRATEGY,
    CONF_STRATEGY_CONFIG,
    DEFAULT_MAX_ACTIVE,
    DOMAIN,
)
from .capacity import CAPACITY_PROVIDERS, DEFAULT_CAPACITY_MODE, get_capacity_policy
from .strategies import (
    DEFAULT_STRATEGY,
    PROVIDERS,
    get_provider,
    strategy_options,
    validate_strategy_config,
)
from .strategy_forms import strategy_form_schema

STORAGE_VERSION = 1

# Support larger unit budgets while retaining the historic classic limit.
MAX_ACTIVE_SELECTOR = NumberSelector(
    NumberSelectorConfig(min=1, max=100000, step=1, mode=NumberSelectorMode.BOX)
)


def capacity_mode_selector(language: str = "en") -> SelectSelector:
    """Capacity is independent of the selected ordering strategy."""
    french = language.lower().startswith("fr")
    translated = {
        "classic": "Classique (places)",
        "weighted": "Pondéré (unités)",
    }
    return SelectSelector(
        SelectSelectorConfig(
            options=[
                SelectOptionDict(
                    value=key,
                    label=translated.get(key, provider.label) if french else provider.label,
                )
                for key, provider in CAPACITY_PROVIDERS.items()
            ],
            mode=SelectSelectorMode.DROPDOWN,
        )
    )


def _capacity_configuration_valid(mode: str, capacity: int) -> bool:
    """Classic retains 1-50 slots; weighted supports 1-100000 units."""
    return (
        mode in CAPACITY_PROVIDERS
        and type(capacity) is int
        and 1 <= capacity <= (50 if mode == "classic" else 100000)
    )


def _weights_schema(
    entities: list[str], defaults: dict[str, int], capacity: int
) -> vol.Schema:
    """Show a native number box for each supervised entity ID."""
    return vol.Schema({
        vol.Required(entity, default=defaults.get(entity, 1)): NumberSelector(
            NumberSelectorConfig(
                min=1, max=capacity, step=1, mode=NumberSelectorMode.BOX
            )
        )
        for entity in entities
    })


def _normalize_weights(
    entities: list[str], values: dict[str, Any], capacity: int
) -> dict[str, int]:
    if set(values) != set(entities):
        raise ValueError("Every supervised entity requires a default weight")
    if any(
        type(value) is not int or value < 1 or value > capacity
        for value in values.values()
    ):
        raise ValueError("Weights must be positive integers within total capacity")
    return dict(values)


def _saved_capacity_error(
    saved: dict, new_mode: str, new_limit: int
) -> str | None:
    """Check unloaded reservations using their saved, immutable effective weights."""
    active = saved.get("active", [])
    waiting = saved.get("waiting", [])
    mode = saved.get("capacity_mode", DEFAULT_CAPACITY_MODE)
    if mode not in CAPACITY_PROVIDERS:
        raise ValueError("Unknown stored capacity mode")
    if mode != new_mode and (active or waiting):
        return "capacity_mode_in_use"
    if mode == "classic":
        if saved.get("engine_request_data"):
            raise ValueError("Unexpected classic engine weights")
        units = {resource: 1 for resource in (*active, *waiting)}
    else:
        metadata = saved.get("engine_request_data", {})
        if not isinstance(metadata, dict) or set(metadata) != set((*active, *waiting)):
            raise ValueError("Missing frozen weights")
        units = {}
        for resource in (*active, *waiting):
            data = metadata[resource]
            if not isinstance(data, dict) or set(data) != {"weight"}:
                raise ValueError("Invalid frozen weight metadata")
            value = data["weight"]
            if type(value) is not int or value < 1:
                raise ValueError("Invalid frozen weight")
            units[resource] = value
    try:
        get_capacity_policy(mode).validate_limit(
            active_units=tuple(units[r] for r in active),
            waiting_units=tuple(units[r] for r in waiting),
            capacity=new_limit,
        )
    except ValueError:
        return "max_active_below_reserved"
    return None

def strategy_selector(language: str = "en") -> SelectSelector:
    """Refresh provider choices in the user's Home Assistant language."""
    return SelectSelector(
        SelectSelectorConfig(
            options=[
                SelectOptionDict(**item)
                for item in strategy_options(language)
            ],
            mode=SelectSelectorMode.DROPDOWN,
        )
    )
# Domain-neutral: accept native entities and helpers (number, text, etc.).
# Actual safety semantics are enforced per-domain by entity_supervision.py.
ENTITIES_SELECTOR = EntitySelector(EntitySelectorConfig(multiple=True))


def _overlapping_entities(hass, selected: list[str], exclude: str | None = None) -> set[str]:
    """Refuse any supervised entity being bound to two independent queues."""
    selected_set = set(selected)
    overlapping: set[str] = set()
    for entry in hass.config_entries.async_entries(DOMAIN):
        if entry.entry_id == exclude:
            continue
        other = entry.options.get(
            CONF_MONITORED_ENTITIES,
            entry.data.get(CONF_MONITORED_ENTITIES, []),
        )
        overlapping.update(selected_set.intersection(other))
    return overlapping


class ResourceQueueManagerConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Create distinct queue entries; older singleton entries remain intact."""

    VERSION = 1

    async def async_step_user(self, user_input: dict | None = None):
        errors: dict[str, str] = {}
        if user_input is not None:
            name = user_input[CONF_NAME].strip()
            if not name:
                errors["base"] = "invalid_name"
            elif any(e.title == name for e in self.hass.config_entries.async_entries(DOMAIN)):
                errors["base"] = "name_in_use"
            elif user_input[CONF_STRATEGY] not in PROVIDERS:
                errors["base"] = "invalid_strategy"
            elif not _capacity_configuration_valid(
                user_input[CONF_CAPACITY_MODE], int(user_input[CONF_MAX_ACTIVE])
            ):
                errors["base"] = "invalid_capacity"
            elif _overlapping_entities(
                self.hass, user_input.get(CONF_MONITORED_ENTITIES, [])
            ):
                errors["base"] = "entities_in_use_elsewhere"
            else:
                # No shared unique_id: each flow creates an independent entry.
                self._pending_data = {
                    CONF_NAME: name,
                    CONF_MAX_ACTIVE: int(user_input[CONF_MAX_ACTIVE]),
                    CONF_STRATEGY: user_input[CONF_STRATEGY],
                    CONF_CAPACITY_MODE: user_input[CONF_CAPACITY_MODE],
                    CONF_MONITORED_ENTITIES: list(
                        user_input.get(CONF_MONITORED_ENTITIES, [])
                    ),
                }
                if get_provider(user_input[CONF_STRATEGY]).config_fields:
                    return await self.async_step_strategy()
                self._pending_data[CONF_STRATEGY_CONFIG] = {}
                return await self._finish_setup()

        schema = vol.Schema(
            {
                vol.Required(CONF_NAME, default=(user_input or {}).get(CONF_NAME, "My queue")): str,
                vol.Required(
                    CONF_MAX_ACTIVE,
                    default=(user_input or {}).get(CONF_MAX_ACTIVE, DEFAULT_MAX_ACTIVE),
                ): MAX_ACTIVE_SELECTOR,
                vol.Required(
                    CONF_STRATEGY,
                    default=(user_input or {}).get(CONF_STRATEGY, DEFAULT_STRATEGY),
                ): strategy_selector(self.hass.config.language),
                vol.Required(
                    CONF_CAPACITY_MODE,
                    default=(user_input or {}).get(CONF_CAPACITY_MODE, DEFAULT_CAPACITY_MODE),
                ): capacity_mode_selector(self.hass.config.language),
                vol.Optional(
                    CONF_MONITORED_ENTITIES,
                    default=(user_input or {}).get(CONF_MONITORED_ENTITIES, []),
                ): ENTITIES_SELECTOR,
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    async def async_step_strategy(self, user_input: dict | None = None):
        """Configure fields provided by the selected algorithm module."""
        strategy = self._pending_data[CONF_STRATEGY]
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                normalized = validate_strategy_config(strategy, user_input)
            except ValueError:
                errors["base"] = "invalid_strategy_options"
            else:
                # A queue may have been created while this flow was open.
                if any(
                    e.title == self._pending_data[CONF_NAME]
                    for e in self.hass.config_entries.async_entries(DOMAIN)
                ):
                    errors["base"] = "name_in_use"
                elif _overlapping_entities(
                    self.hass, self._pending_data[CONF_MONITORED_ENTITIES]
                ):
                    errors["base"] = "entities_in_use_elsewhere"
                else:
                    data = dict(self._pending_data)
                    self._pending_data[CONF_STRATEGY_CONFIG] = normalized
                    return await self._finish_setup()
        return self.async_show_form(
            step_id="strategy",
            data_schema=strategy_form_schema(
                strategy, user_input, self.hass.config.language
            ),
            errors=errors,
        )

    async def _finish_setup(self):
        """Complete classic setup, or ask for default weights in weighted mode."""
        if (
            self._pending_data[CONF_CAPACITY_MODE] == "weighted"
            and self._pending_data[CONF_MONITORED_ENTITIES]
        ):
            return await self.async_step_weights()
        self._pending_data[CONF_ENTITY_WEIGHTS] = {}
        return self.async_create_entry(
            title=self._pending_data[CONF_NAME], data=self._pending_data
        )

    async def async_step_weights(self, user_input: dict | None = None):
        """Collect the supervised entities' default unit costs."""
        data = self._pending_data
        entities = data[CONF_MONITORED_ENTITIES]
        capacity = data[CONF_MAX_ACTIVE]
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                weights = _normalize_weights(entities, user_input, capacity)
            except ValueError:
                errors["base"] = "invalid_weights"
            else:
                if any(
                    entry.title == data[CONF_NAME]
                    for entry in self.hass.config_entries.async_entries(DOMAIN)
                ):
                    errors["base"] = "name_in_use"
                elif _overlapping_entities(self.hass, entities):
                    errors["base"] = "entities_in_use_elsewhere"
                else:
                    data[CONF_ENTITY_WEIGHTS] = weights
                    return self.async_create_entry(title=data[CONF_NAME], data=data)
        return self.async_show_form(
            step_id="weights",
            data_schema=_weights_schema(entities, user_input or {}, capacity),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> "ResourceQueueOptionsFlow":
        return ResourceQueueOptionsFlow()


class ResourceQueueOptionsFlow(OptionsFlowWithReload):
    """Configure capacity, strategy and supervised entities per entry."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None):
        entry = self.config_entry
        errors: dict[str, str] = {}
        selected = list(
            entry.options.get(
                CONF_MONITORED_ENTITIES,
                entry.data.get(CONF_MONITORED_ENTITIES, []),
            )
        )
        current_limit = entry.options.get(
            CONF_MAX_ACTIVE, entry.data.get(CONF_MAX_ACTIVE, DEFAULT_MAX_ACTIVE)
        )
        current_strategy = entry.options.get(
            CONF_STRATEGY, entry.data.get(CONF_STRATEGY, DEFAULT_STRATEGY)
        )
        current_config = entry.options.get(
            CONF_STRATEGY_CONFIG, entry.data.get(CONF_STRATEGY_CONFIG, {})
        )
        current_mode = entry.options.get(
            CONF_CAPACITY_MODE, entry.data.get(CONF_CAPACITY_MODE, DEFAULT_CAPACITY_MODE)
        )
        new_limit = current_limit
        new_strategy = current_strategy
        new_mode = current_mode

        if user_input is not None:
            selected = list(user_input.get(CONF_MONITORED_ENTITIES, []))
            new_limit = int(user_input[CONF_MAX_ACTIVE])
            new_strategy = user_input[CONF_STRATEGY]
            new_mode = user_input[CONF_CAPACITY_MODE]
            if new_strategy not in PROVIDERS:
                errors["base"] = "invalid_strategy"
            elif new_mode not in CAPACITY_PROVIDERS:
                errors["base"] = "invalid_capacity_mode"
            elif not _capacity_configuration_valid(new_mode, new_limit):
                errors["base"] = "invalid_capacity"
            elif _overlapping_entities(self.hass, selected, entry.entry_id):
                errors["base"] = "entities_in_use_elsewhere"

            # Provider forms must finish before pausing a live queue.
            strategy_ready = getattr(self, "_strategy_config_ready", False)
            weights_ready = getattr(self, "_weights_ready", False)
            has_fields = not errors and bool(get_provider(new_strategy).config_fields)
            pending_strategy = bool(has_fields and not strategy_ready)
            pending_weights = bool(new_mode == "weighted" and selected and not weights_ready)
            candidate_config = (
                self._validated_strategy_config
                if strategy_ready
                else current_config if current_strategy == new_strategy else {}
            )

            runtime = self.hass.data.get(DOMAIN, {}).get(entry.entry_id)
            if not errors and runtime is not None:
                async with runtime.lock:
                    saved = runtime.manager.export_state()
                    if not set(saved["bindings"].values()).issubset(selected):
                        errors["base"] = "entities_in_use"
                    elif new_mode != runtime.manager.capacity_mode and (
                        saved["active"] or saved["waiting"]
                    ):
                        errors["base"] = "capacity_mode_in_use"
                    elif new_mode == runtime.manager.capacity_mode:
                        try:
                            runtime.manager.queue.validate_capacity_limit(new_limit)
                        except ValueError:
                            errors["base"] = "max_active_below_reserved"
                    if not errors and (
                        new_strategy != runtime.manager.strategy
                        or (
                            not pending_strategy
                            and candidate_config != runtime.manager.queue.strategy_config
                        )
                    ) and (saved["active"] or saved["waiting"]):
                        errors["base"] = "strategy_in_use"
                    if not errors and not pending_strategy and not pending_weights:
                        runtime.manager.pause()
            elif not errors:
                try:
                    store = Store(
                        self.hass, STORAGE_VERSION, f"{DOMAIN}.{entry.entry_id}"
                    )
                    saved = await store.async_load()
                    saved = {} if saved is None else saved
                    if not isinstance(saved, dict):
                        raise ValueError("Invalid stored queue")
                    bindings = saved.get("bindings", {})
                    active = saved.get("active", [])
                    waiting = saved.get("waiting", [])
                    if (
                        not isinstance(bindings, dict)
                        or not isinstance(active, list)
                        or not isinstance(waiting, list)
                    ):
                        raise ValueError("Invalid stored queue")
                    if not set(bindings.values()).issubset(selected):
                        errors["base"] = "entities_in_use"
                    else:
                        capacity_error = _saved_capacity_error(
                            saved, new_mode, new_limit
                        )
                        if capacity_error is not None:
                            errors["base"] = capacity_error
                    if not errors and (
                        new_strategy != saved.get("strategy", current_strategy)
                        or (
                            not pending_strategy
                            and candidate_config != saved.get(
                                "strategy_config", current_config
                            )
                        )
                    ) and (active or waiting):
                        errors["base"] = "strategy_in_use"
                except Exception:
                    errors["base"] = "storage_unavailable"

            if not errors:
                pending = {
                    CONF_MONITORED_ENTITIES: selected,
                    CONF_MAX_ACTIVE: new_limit,
                    CONF_STRATEGY: new_strategy,
                    CONF_CAPACITY_MODE: new_mode,
                }
                self._pending_options = pending
                if has_fields and not strategy_ready:
                    return await self.async_step_strategy()
                pending[CONF_STRATEGY_CONFIG] = (
                    self._validated_strategy_config if has_fields else {}
                )
                if pending_weights:
                    return await self.async_step_weights()
                pending[CONF_ENTITY_WEIGHTS] = (
                    self._validated_weights if new_mode == "weighted" and selected else {}
                )
                self._strategy_config_ready = False
                self._weights_ready = False
                return self.async_create_entry(data=pending)

        schema = vol.Schema(
            {
                vol.Required(CONF_MAX_ACTIVE, default=new_limit): MAX_ACTIVE_SELECTOR,
                vol.Required(
                    CONF_STRATEGY, default=new_strategy
                ): strategy_selector(self.hass.config.language),
                vol.Required(
                    CONF_CAPACITY_MODE, default=new_mode
                ): capacity_mode_selector(self.hass.config.language),
                vol.Optional(
                    CONF_MONITORED_ENTITIES, default=selected
                ): ENTITIES_SELECTOR,
            }
        )
        return self.async_show_form(
            step_id="init", data_schema=schema, errors=errors
        )

    async def async_step_strategy(self, user_input: dict | None = None):
        """Configure the selected scheduling provider before final validation."""
        pending = self._pending_options
        strategy = pending[CONF_STRATEGY]
        errors: dict[str, str] = {}
        current_strategy = self.config_entry.options.get(
            CONF_STRATEGY,
            self.config_entry.data.get(CONF_STRATEGY, DEFAULT_STRATEGY),
        )
        previous = (
            self.config_entry.options.get(
                CONF_STRATEGY_CONFIG,
                self.config_entry.data.get(CONF_STRATEGY_CONFIG, {}),
            )
            if current_strategy == strategy
            else {}
        )
        if user_input is not None:
            try:
                normalized = validate_strategy_config(strategy, user_input)
            except ValueError:
                errors["base"] = "invalid_strategy_options"
            else:
                self._validated_strategy_config = normalized
                self._strategy_config_ready = True
                result = await self.async_step_init(dict(pending))
                if result["type"] == "form" and result.get("step_id") == "init":
                    self._strategy_config_ready = False
                return result

        return self.async_show_form(
            step_id="strategy",
            data_schema=strategy_form_schema(
                strategy, user_input or previous, self.hass.config.language
            ),
            errors=errors,
        )

    async def async_step_weights(self, user_input: dict | None = None):
        """Set native numeric defaults for all selected supervised entities."""
        pending = self._pending_options
        entities = pending[CONF_MONITORED_ENTITIES]
        capacity = pending[CONF_MAX_ACTIVE]
        previous = self.config_entry.options.get(
            CONF_ENTITY_WEIGHTS, self.config_entry.data.get(CONF_ENTITY_WEIGHTS, {})
        )
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                normalized = _normalize_weights(entities, user_input, capacity)
            except ValueError:
                errors["base"] = "invalid_weights"
            else:
                self._validated_weights = normalized
                self._weights_ready = True
                # Revalidate the queue under its lock before committing settings.
                result = await self.async_step_init(dict(pending))
                if result["type"] == "form" and result.get("step_id") == "init":
                    self._weights_ready = False
                return result

        return self.async_show_form(
            step_id="weights",
            data_schema=_weights_schema(entities, user_input or previous, capacity),
            errors=errors,
        )
