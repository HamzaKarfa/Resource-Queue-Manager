# Development and integration testing

This document covers the published v1.0 architecture and the **unreleased v1.1 development branches** for Home Assistant 2026.11+. Use the stable release tag for production and a complete feature branch on a separate test installation for v1.1.

## Repository layout

```text
custom_components/resource_queue_manager/
├── __init__.py            # HA lifecycle, services and persistence
├── config_flow.py         # Multi-entry setup and options flows
├── const.py               # Integration constants
├── coordinator.py         # Entity binding, recovery and safety rules
├── engine.py              # Generic queue capacity and scheduling
├── entity_supervision.py  # Domain-specific ON/OFF and logical rules
├── sensor.py              # Four sensors per entry, with v1.1 capacity and count attributes
├── services.yaml          # Common Home Assistant action schema
├── strategy_forms.py      # Provider settings -> native HA selectors
├── capacity/              # Classic + weighted capacity providers
├── recurrence/            # Ignore + count pending-duplicate providers
├── strings.json           # Canonical English UI definitions
├── translations/          # English/French translations
└── strategies/
    ├── base.py            # Protocols and field descriptors
    ├── request.py         # QueueRequest data model
    ├── registry.py        # Explicit provider registration and validation
    ├── fifo/
    ├── lifo/
    └── priority_fifo/
docs/
├── MIGRATION_v0.4_to_v1.md
├── V1_ARCHITECTURE.md
└── releases/v1.0.0.md
tests/
├── test_engine.py
├── test_coordinator.py
├── test_recovery.py
├── test_priority_fifo.py
├── test_supervision.py
├── test_weighted_capacity.py
├── test_recurrence.py
├── test_snapshot_migration_v11.py
└── ha/                     # Integration tests incl. v1.1 contracts
```

Core scheduling policies must remain independent from Home Assistant imports. Every integration config entry has its own queue, independent lock and `.storage` key.

**No legacy FIFO shim:** the generic scheduling code is in `engine.py`; tests and plugins import it as `resource_queue_manager.engine`. Strategy `config.py` and `request.py` declarations remain part of each plugin's provider contract, including when the field tuples are empty.

**Entity supervision:** `entity_supervision.py` assigns domain-aware availability and release checks, independently from scheduling strategies. `light`, `switch`, `fan` and `input_boolean` use fail-closed ON/OFF verification; arbitrary Home Assistant domains (including native and helper number/text entities) require a known non-unavailable state. Generic entity values do not prove that a physical device is off. `coordinator.py` enforces these policies, never the strategy packages.

## Local test setup

Use **Python 3.14** for the pinned Home Assistant test fixture package, matching `.github/workflows/home-assistant-tests.yml`. Unit tests also run in CI under Python 3.13.

```bash
git clone https://github.com/HamzaKarfa/Resource-Queue-Manager.git
cd Resource-Queue-Manager
git fetch origin
git switch docs/v1.1-regression-release-readiness  # unreleased development preview

python3.14 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m unittest discover -s tests -v

python -m pip install "pytest-homeassistant==2026.11.1"
python -m pytest -q tests/ha
```

The Home Assistant fixture package installs its declared dependencies; the pure-Python tests require no Home Assistant installation. CI also runs HACS validation and hassfest. No physical relays are used by tests.

To verify the integration manually, place the entire branch directory `custom_components/resource_queue_manager` in a **separate test Home Assistant** `config/custom_components` directory, restart, and add one or more entries in Settings → Devices & services. Keep real heating or other high-power equipment disconnected from the experiment.

## How to add another scheduling plugin

An ordinary plugin owns four files:

```text
strategies/my_algorithm/
├── __init__.py
├── provider.py
├── config.py
├── request.py
└── strategy.py
```

1. Implement a pure-Python `QueueStrategy.enqueue(waiting, request, requests)` in `strategy.py`. The engine always grants from the **left** of the queue and controls concurrency, not physical entities. An algorithm must insert each new resource ID exactly once.
2. In `config.py`, declare `CONFIG_FIELDS` as a tuple of `StrategyConfigField` objects. Leave it empty when there are no strategy-wide settings.
3. In `request.py`, declare `REQUEST_FIELDS` for metadata supplied on **each request**. The host rejects unknown fields, invalid types and out-of-range numbers.
4. In `provider.py`, define a class with `key`, `label`, `description`, `config_fields`, `request_fields` and `create(config)`. It must return a **fresh policy instance**, not a shared mutable singleton.
5. Register the provider explicitly in `strategies/registry.py` and export it from `strategies/__init__.py`. Registration is intentionally **not** auto-discovered from disk; arbitrary untrusted modules cannot be loaded by configuration values.
6. Add native HA form labels/descriptions to `strings.json` and the translations. Form choices are generated from the provider registry; strategy-wide settings are rendered by `strategy_forms.py`.
7. Add pure-Python tests for ordering, ties, cancellation and idempotency, plus HA setup/option/action/restart tests when adding request settings.

Example **Priority FIFO** request descriptor:

```python
REQUEST_FIELDS = (
    StrategyConfigField(
        key="priority",
        label="Request priority",
        kind="number",
        required=True,
        minimum=1,
        maximum=10,
    ),
)
```

**Boundaries:** strategies may rank or insert waiting requests. They may not bypass OFF confirmation, alter saved reservations directly, switch HA entities, preempt active reservations, register arbitrary services, or claim to provide electrical safety. Advanced policies needing time-based aging, scheduling callbacks, dynamic priorities, or different persistence need a reviewed extension of these contracts.

## Capacity and recurrence extension contracts (v1.1 development)

- The capacity policy determines admission and restore-capacity validation, independently of FIFO/LIFO/Priority FIFO. Registered providers live in `capacity/registry.py`. `classic` consumes one slot; `weighted` consumes integer units with no second slot limit.
- The recurrence policy determines how duplicate **pending** `resource_id` requests are handled. Registered providers live in `recurrence/registry.py`; the default `ignore` does not increment, while `count` increments without modifying position, priority, effective weight or reservation count.
- The engine owns immutable effective request weights, occurrence counts and ID-only active/waiting snapshots. Changes to capacity modes and recurrence policy must fail with nonempty queues.
- Do not publish grant events until durable storage succeeds. `sensor.py` preserves the four original IDs and exposes capacity metrics and occurrence metadata.
- New providers must have isolated pure-Python implementations and regression tests; there is no dynamic import of arbitrary user modules.

## Contract and backwards compatibility

- The public request action accepts the standard `resource_id`, `entity_id`, optional `config_entry_id` and optional `strategy_data`. In **v1.1 development**, `engine_data` is also accepted and provider-validated (for example `engine_data.weight` in weighted mode).
- In a multi-entry setup, all actions require `config_entry_id` and route to exactly one queue.
- Every queue starts paused on setup/reload, and pending grants resume only after explicit verification.
- A queue is not allowed to switch strategy/settings with active or waiting work.
- The persisted `active` and `waiting` arrays remain **ID-only**, while `request_data` persists validated scheduling metadata separately. v1.1 also saves effective weighted costs, per-entity defaults and occurrence counts.
- Legacy FIFO snapshots without newer keys remain valid. Changing the serialized format must include an explicit migration test.
- Priority FIFO is **non-preemptive**, and ties preserve FIFO arrival order.

## Release readiness

Version tags and GitHub releases are deliberately **not** published from pull requests. Only after manual acceptance and merge to `main` should the maintainer run the guarded manual release workflow.

```bash
python -m unittest discover -s tests -v
python -m pip install "pytest-homeassistant==2026.11.1"
python -m pytest -q tests/ha
```

For the existing v1.0 release, the applicable version is `1.0.0`. For **unreleased v1.1**, see [the manual acceptance checklist](RELEASE_CHECKLIST_v1.1.md) and [migration guide](MIGRATION_v1.0_to_v1.1.md). Keep the manifest at `1.0.0` until an explicitly authorized v1.1 release commit. Validate a fresh v1.0 upgrade, two independent queues, weighted allocation, count-mode events, paused recovery and rollback on a separate HA test instance before publication. The separate release workflow requires a manual confirmation token and only runs on `main`; it does not trigger on PRs or merges.

See [migration steps](MIGRATION_v0.4_to_v1.md), [release notes](releases/v1.0.0.md), and the [manual acceptance checklist](RELEASE_CHECKLIST_v1.md).
