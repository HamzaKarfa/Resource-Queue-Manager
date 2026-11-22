"""Section-based Home Assistant options flow, editing one concern at a time.

Each category commits a complete, merged set of options, preserving unrelated
provider settings. No queue is paused merely by navigating the menu/forms.
"""

from typing import Any

import voluptuous as vol

from homeassistant.helpers.storage import Store

from .allocation import ALLOCATION_MODES, DEFAULT_ALLOCATION_MODE
from .capacity import CAPACITY_PROVIDERS, DEFAULT_CAPACITY_MODE
from .const import (
    CONF_ALLOCATION_MODE,
    CONF_CAPACITY_MODE,
    CONF_ENTITY_WEIGHTS,
    CONF_MAX_ACTIVE,
    CONF_MONITORED_ENTITIES,
    CONF_RECURRENCE_MODE,
    CONF_STRATEGY,
    CONF_STRATEGY_CONFIG,
    DEFAULT_MAX_ACTIVE,
    DOMAIN,
)
from .recurrence import RECURRENCE_PROVIDERS, DEFAULT_RECURRENCE_MODE
from .strategies import DEFAULT_STRATEGY, PROVIDERS, get_provider, validate_strategy_config
from .strategy_forms import strategy_form_schema
from .config_flow import (
    ENTITIES_SELECTOR,
    MAX_ACTIVE_SELECTOR,
    STORAGE_VERSION,
    _capacity_configuration_valid,
    _normalize_weights,
    _overlapping_entities,
    _saved_capacity_error,
    _weights_schema,
    allocation_mode_selector,
    capacity_mode_selector,
    recurrence_mode_selector,
    strategy_selector,
    ResourceQueueOptionsFlow,
)


_DEFAULTS = {
    CONF_MAX_ACTIVE: DEFAULT_MAX_ACTIVE,
    CONF_CAPACITY_MODE: DEFAULT_CAPACITY_MODE,
    CONF_ENTITY_WEIGHTS: {},
    CONF_MONITORED_ENTITIES: [],
    CONF_STRATEGY: DEFAULT_STRATEGY,
    CONF_STRATEGY_CONFIG: {},
    CONF_RECURRENCE_MODE: DEFAULT_RECURRENCE_MODE,
    CONF_ALLOCATION_MODE: DEFAULT_ALLOCATION_MODE,
}


class SectionedOptionsFlow(ResourceQueueOptionsFlow):
    """Native HA menu containing only the chosen category's settings."""

    def _settings(self) -> dict[str, Any]:
        entry = self.config_entry
        settings = {
            key: entry.options.get(key, entry.data.get(key, default))
            for key, default in _DEFAULTS.items()
        }
        # Old weighted entries may omit some per-entity defaults: the engine
        # already uses 1 for those entities. Preserve that same behavior when
        # editing *unrelated* settings instead of rejecting the whole form.
        if settings[CONF_CAPACITY_MODE] == "weighted":
            stored = settings[CONF_ENTITY_WEIGHTS] or {}
            settings[CONF_ENTITY_WEIGHTS] = {
                entity: stored.get(entity, 1)
                for entity in settings[CONF_MONITORED_ENTITIES]
            }
        return settings

    async def _commit(self, updates: dict[str, Any]) -> str | None:
        """Validate a complete candidate against the live or saved queue."""
        entry = self.config_entry
        candidate = {**self._settings(), **updates}
        entities = list(candidate[CONF_MONITORED_ENTITIES])
        mode = candidate[CONF_CAPACITY_MODE]
        allocation = candidate[CONF_ALLOCATION_MODE]
        recurrence = candidate[CONF_RECURRENCE_MODE]
        strategy = candidate[CONF_STRATEGY]
        capacity = candidate[CONF_MAX_ACTIVE]

        if not _capacity_configuration_valid(mode, capacity):
            return "invalid_capacity"
        if allocation not in ALLOCATION_MODES:
            return "invalid_allocation_mode"
        if recurrence not in RECURRENCE_PROVIDERS:
            return "invalid_recurrence_mode"
        if strategy not in PROVIDERS:
            return "invalid_strategy"
        if len(entities) != len(set(entities)):
            return "invalid_weights"
        if _overlapping_entities(self.hass, entities, entry.entry_id):
            return "entities_in_use_elsewhere"
        try:
            config = validate_strategy_config(
                strategy, candidate[CONF_STRATEGY_CONFIG]
            )
            if mode == "weighted":
                weights = _normalize_weights(
                    entities, candidate[CONF_ENTITY_WEIGHTS], capacity
                ) if entities else {}
            else:
                weights = {}
        except ValueError as err:
            if "weight" in str(err).lower():
                return "invalid_weights"
            return "invalid_strategy_options"

        candidate[CONF_STRATEGY_CONFIG] = config
        candidate[CONF_ENTITY_WEIGHTS] = weights
        runtime = self.hass.data.get(DOMAIN, {}).get(entry.entry_id)

        async def check_saved(saved: dict[str, Any]) -> str | None:
            active, waiting = saved.get("active", []), saved.get("waiting", [])
            bindings = saved.get("bindings", {})
            if (
                not isinstance(active, list)
                or not isinstance(waiting, list)
                or not isinstance(bindings, dict)
            ):
                raise ValueError("Malformed queue snapshot")
            busy = bool(active or waiting)
            if not set(bindings.values()).issubset(entities):
                return "entities_in_use"
            if mode != saved.get("capacity_mode", DEFAULT_CAPACITY_MODE) and busy:
                return "capacity_mode_in_use"
            if recurrence != saved.get("recurrence_mode", DEFAULT_RECURRENCE_MODE) and busy:
                return "recurrence_mode_in_use"
            if allocation != saved.get("allocation_mode", DEFAULT_ALLOCATION_MODE) and busy:
                return "allocation_mode_in_use"
            if (
                strategy != saved.get("strategy", DEFAULT_STRATEGY)
                or config != saved.get("strategy_config", {})
            ) and busy:
                return "strategy_in_use"
            return _saved_capacity_error(saved, mode, capacity)

        if runtime is not None:
            async with runtime.lock:
                try:
                    error = await check_saved(runtime.manager.export_state())
                except (ValueError, TypeError, KeyError):
                    return "storage_unavailable"
                if error:
                    return error
                # Pause only on an accepted change, immediately before the
                # options flow ends and Home Assistant schedules its reload.
                runtime.manager.pause()
        else:
            try:
                saved = await Store(
                    self.hass, STORAGE_VERSION, f"{DOMAIN}.{entry.entry_id}"
                ).async_load()
                error = await check_saved(saved or {})
            except (ValueError, TypeError, KeyError, OSError):
                return "storage_unavailable"
            if error:
                return error

        self._next_options = {
            **entry.options,
            **candidate,
        }
        return None

    def _finish(self):
        return self.async_create_entry(data=self._next_options)

    async def async_step_init(self, user_input: dict | None = None):
        """Present the native menu; preserve old direct config inputs for API clients."""
        if user_input is not None:
            return await super().async_step_init(user_input)
        return self.async_show_menu(
            step_id="init",
            menu_options=["resources", "capacity", "scheduling", "recurrence"],
        )

    async def async_step_resources(self, user_input: dict | None = None):
        """Edit supervised entities, then their weights when relevant."""
        current = self._settings()
        errors = {}
        entities = current[CONF_MONITORED_ENTITIES]
        if user_input is not None:
            entities = list(user_input.get(CONF_MONITORED_ENTITIES, []))
            if _overlapping_entities(self.hass, entities, self.config_entry.entry_id):
                errors["base"] = "entities_in_use_elsewhere"
            elif current[CONF_CAPACITY_MODE] == "weighted" and entities:
                self._pending_entities = entities
                return await self.async_step_resource_weights()
            else:
                error = await self._commit({
                    CONF_MONITORED_ENTITIES: entities,
                    CONF_ENTITY_WEIGHTS: {},
                })
                if error:
                    errors["base"] = error
                else:
                    return self._finish()
        return self.async_show_form(
            step_id="resources",
            data_schema=vol.Schema({
                vol.Optional(
                    CONF_MONITORED_ENTITIES, default=entities
                ): ENTITIES_SELECTOR,
            }),
            errors=errors,
        )

    async def async_step_resource_weights(self, user_input: dict | None = None):
        """Edit entity defaults without reconfiguring unrelated policies."""
        current = self._settings()
        entities = self._pending_entities
        capacity = current[CONF_MAX_ACTIVE]
        defaults = {
            entity: current[CONF_ENTITY_WEIGHTS].get(entity, 1)
            for entity in entities
        }
        errors = {}
        if user_input is not None:
            try:
                normalized = _normalize_weights(entities, user_input, capacity)
            except ValueError:
                errors["base"] = "invalid_weights"
            else:
                error = await self._commit({
                    CONF_MONITORED_ENTITIES: entities,
                    CONF_ENTITY_WEIGHTS: normalized,
                })
                if error:
                    errors["base"] = error
                else:
                    return self._finish()
        return self.async_show_form(
            step_id="resource_weights",
            data_schema=_weights_schema(
                entities, user_input or defaults, capacity
            ),
            errors=errors,
        )

    async def async_step_capacity(self, user_input: dict | None = None):
        """Edit capacity policy and limit only."""
        current = self._settings()
        mode = current[CONF_CAPACITY_MODE]
        capacity = current[CONF_MAX_ACTIVE]
        errors = {}
        if user_input is not None:
            mode = user_input[CONF_CAPACITY_MODE]
            capacity = int(user_input[CONF_MAX_ACTIVE])
            if not _capacity_configuration_valid(mode, capacity):
                errors["base"] = "invalid_capacity"
            else:
                old_weights = current[CONF_ENTITY_WEIGHTS]
                selected = current[CONF_MONITORED_ENTITIES]
                # Ask for weight defaults only when entering weighted mode or
                # when an existing entity default exceeds the new limit.
                needs_weights = mode == "weighted" and bool(selected) and (
                    current[CONF_CAPACITY_MODE] != "weighted"
                    or any(old_weights.get(e, 1) > capacity for e in selected)
                )
                if needs_weights:
                    self._pending_capacity = {CONF_CAPACITY_MODE: mode, CONF_MAX_ACTIVE: capacity}
                    return await self.async_step_capacity_weights()
                error = await self._commit({
                    CONF_CAPACITY_MODE: mode,
                    CONF_MAX_ACTIVE: capacity,
                })
                if error:
                    errors["base"] = error
                else:
                    return self._finish()
        return self.async_show_form(
            step_id="capacity",
            data_schema=vol.Schema({
                vol.Required(CONF_CAPACITY_MODE, default=mode):
                    capacity_mode_selector(self.hass.config.language),
                vol.Required(CONF_MAX_ACTIVE, default=capacity):
                    MAX_ACTIVE_SELECTOR,
            }),
            errors=errors,
        )

    async def async_step_capacity_weights(self, user_input: dict | None = None):
        """Only necessary when capacity mode/limit makes defaults unsuitable."""
        current = self._settings()
        capacity = self._pending_capacity[CONF_MAX_ACTIVE]
        entities = current[CONF_MONITORED_ENTITIES]
        defaults = {
            entity: min(current[CONF_ENTITY_WEIGHTS].get(entity, 1), capacity)
            for entity in entities
        }
        errors = {}
        if user_input is not None:
            try:
                weights = _normalize_weights(entities, user_input, capacity)
            except ValueError:
                errors["base"] = "invalid_weights"
            else:
                error = await self._commit({
                    **self._pending_capacity,
                    CONF_ENTITY_WEIGHTS: weights,
                })
                if error:
                    errors["base"] = error
                else:
                    return self._finish()
        return self.async_show_form(
            step_id="capacity_weights",
            data_schema=_weights_schema(
                entities, user_input or defaults, capacity
            ),
            errors=errors,
        )

    async def async_step_scheduling(self, user_input: dict | None = None):
        """Edit strategy/backfill, without mandatory priority re-entry."""
        current = self._settings()
        strategy = current[CONF_STRATEGY]
        allocation = current[CONF_ALLOCATION_MODE]
        errors = {}
        if user_input is not None:
            strategy = user_input[CONF_STRATEGY]
            allocation = user_input[CONF_ALLOCATION_MODE]
            edit_details = bool(user_input.get("edit_strategy_options", False))
            if strategy not in PROVIDERS:
                errors["base"] = "invalid_strategy"
            elif allocation not in ALLOCATION_MODES:
                errors["base"] = "invalid_allocation_mode"
            elif get_provider(strategy).config_fields and (
                strategy != current[CONF_STRATEGY] or edit_details
            ):
                self._pending_scheduling = {
                    CONF_STRATEGY: strategy,
                    CONF_ALLOCATION_MODE: allocation,
                }
                return await self.async_step_scheduling_details()
            else:
                error = await self._commit({
                    CONF_STRATEGY: strategy,
                    CONF_STRATEGY_CONFIG: (
                        current[CONF_STRATEGY_CONFIG]
                        if strategy == current[CONF_STRATEGY] else {}
                    ),
                    CONF_ALLOCATION_MODE: allocation,
                })
                if error:
                    errors["base"] = error
                else:
                    return self._finish()
        return self.async_show_form(
            step_id="scheduling",
            data_schema=vol.Schema({
                vol.Required(CONF_STRATEGY, default=strategy):
                    strategy_selector(self.hass.config.language),
                vol.Required(CONF_ALLOCATION_MODE, default=allocation):
                    allocation_mode_selector(self.hass.config.language),
                vol.Optional("edit_strategy_options", default=False): bool,
            }),
            errors=errors,
        )

    async def async_step_scheduling_details(self, user_input: dict | None = None):
        """Provider-owned settings are shown only when explicitly requested."""
        pending = self._pending_scheduling
        strategy = pending[CONF_STRATEGY]
        current = self._settings()
        defaults = (
            current[CONF_STRATEGY_CONFIG]
            if strategy == current[CONF_STRATEGY] else {}
        )
        errors = {}
        if user_input is not None:
            try:
                config = validate_strategy_config(strategy, user_input)
            except ValueError:
                errors["base"] = "invalid_strategy_options"
            else:
                error = await self._commit({
                    **pending,
                    CONF_STRATEGY_CONFIG: config,
                })
                if error:
                    errors["base"] = error
                else:
                    return self._finish()
        return self.async_show_form(
            step_id="scheduling_details",
            data_schema=strategy_form_schema(
                strategy, user_input or defaults, self.hass.config.language
            ),
            errors=errors,
        )

    async def async_step_recurrence(self, user_input: dict | None = None):
        """Edit duplicate handling without visiting the other forms."""
        current = self._settings()
        mode = current[CONF_RECURRENCE_MODE]
        errors = {}
        if user_input is not None:
            mode = user_input[CONF_RECURRENCE_MODE]
            error = await self._commit({CONF_RECURRENCE_MODE: mode})
            if error:
                errors["base"] = error
            else:
                return self._finish()
        return self.async_show_form(
            step_id="recurrence",
            data_schema=vol.Schema({
                vol.Required(CONF_RECURRENCE_MODE, default=mode):
                    recurrence_mode_selector(self.hass.config.language),
            }),
            errors=errors,
        )
