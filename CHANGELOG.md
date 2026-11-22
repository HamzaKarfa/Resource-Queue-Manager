# Changelog

All notable changes to Resource Queue Manager are documented here.
Versions follow Semantic Versioning; the Home Assistant manifest version and
GitHub Release tag are intended to match (`1.0.0` ↔ `v1.0.0`).

## [Pre-release candidate] — v1.1.0-rc.2 (Backfill + improved UI)

- Add an independent per-queue allocation-mode setting: **Strict** (default, preserves head-of-line) or **Backfill** (grant fitting requests beyond a blocked head in existing strategy order).
- Preserve waiting-order, frozen effective weights, recurrence counters, persistence-before-grant behavior, and capacity guarantees.
- Add EN/FR Home Assistant setup/options selectors and allocation-mode attributes in existing sensors/grant events.
- Old queues and snapshots continue in `strict`. Changing modes requires no outstanding reservations or waiting requests.
- Backfill may bypass a blocked higher-priority or older request and **does not prevent starvation**; no automatic priority aging or device control.

- Replace the monolithic Home Assistant options dialog with a native four-category menu for resources/weights, capacity, scheduling/admission and recurrence.
- Guide first-time setup through independent steps; preserve unrelated options and frozen request metadata on individual edits.
- Keep the queue running while navigating menus; pause/reload only after a configuration change is accepted.
- Add EN/FR translations for all new setup/options steps and Home Assistant end-to-end regression tests.

These additions are staged for **v1.1.0-rc.2**, not included in immutable `v1.1.0-rc.1`; stable `v1.0.0` is unchanged.

## [Unreleased] — planned v1.1.0

**Development candidate only.** The features below are in stacked draft PRs and have not been published to Marketplace/HACS.

### Added
- Pure-Python capacity provider registry with `classic` (v1-compatible slots) and `weighted` (single shared integer unit budget, no additional slot limit).
- Configurable integer weight per supervised entity (default 1); optional `engine_data.weight` override on one new request, frozen while pending, active and after reload.
- Independent `ignore`/`count` recurrence providers; identical pending resource IDs can be counted without duplicate queue entries, reordering or new reservations.
- Capacity/recurrence selectors in native HA config/options forms with English/French translations.
- Exposed `capacity_mode`, `capacity_unit`, total/used/remaining, effective request weights and occurrence counts as attributes on the existing four sensors.
- Extended persisted grant events with capacity mode, effective weight and occurrence count.
- Focused tests for 12 strategy × capacity × recurrence combinations, concurrent queue isolation, persistence-before-event, and fail-closed snapshot migration.

### Maintained
- Existing v1.0 queues default to `classic + ignore` with original service YAML, sensor IDs, strategy ordering and supervised OFF rules.
- Every queue starts paused after reload and requires an explicit `resume`; invalid snapshots never reset silently.
- No direct actuation, global budget, watts calculation, message-content deduplication, priority aging or preemption.

### Migration / release
See [v1.0 → v1.1 migration guide](docs/MIGRATION_v1.0_to_v1.1.md),
[draft release notes](docs/releases/v1.1.0-draft.md) and
[unverified manual release gates](docs/RELEASE_CHECKLIST_v1.1.md).
The manifest stays at `1.0.0` until a separately approved release commit.

## [1.0.0]

**Multi-instance and strategy-provider architecture.** Version 1 introduces
multiple independent queues, additional strategies, and domain-aware entity
supervision while preserving existing v0.4 FIFO entry and storage compatibility.

### Added

- Multiple independent, named Home Assistant configuration entries with
  separate capacities, supervised entities, saved state and diagnostic sensors.
- Pluggable `StrategyProvider` modules, with pure-Python strategies, configuration
  and request descriptors, and provider-driven Home Assistant forms.
- FIFO, non-preemptive LIFO, and Priority FIFO (configurable priority direction;
  stable FIFO ties for equal priority).
- `config_entry_id` targeting for every queue action and corresponding grant
  event identity.
- Provider-validated `strategy_data` in the `request` action, persisted in
  a new `request_data` field.
- French UI translation coverage and provider-owned translated labels.
- Domain-neutral entity selector for native `number`/`text` and helpers including
  `input_number`, `input_text` and `input_boolean`. ON/OFF devices remain guarded
  by observed OFF before release; other entities require a known state.
- Expanded English/French documentation, migration/rollback instructions and
  development guides.
- Tests covering strategy ordering, multiple entries, priority persistence,
  provider forms, v0.4 snapshot upgrades, logical entity supervision and release metadata.
- Manually gated `v1.0.0` GitHub release workflow.

### Changed

- Generic scheduling engine moved to `engine.py`; the obsolete `fifo.py` shim
  and standalone-import fallback have been removed. Tests import the real package.
- Existing singleton installations remain FIFO, but **once two or more entries
  are configured, all actions require `config_entry_id`**.
- HACS/manifest display name is now **Resource Queue Manager** without the
  FIFO-only suffix.
- Every entry remains paused after startup and options reload until an explicit
  validated `resume` for that entry.

### Important

- No physical entity switching; logical reservations are not electrical
  protections or a guaranteed power limiter.
- No active-reservation preemption, priority aging, global capacity, or automatic
  strategy migration.
- Rollback to v0.4 requires the matching Home Assistant backup.

See [v1.0.0 release notes](docs/releases/v1.0.0.md) and
[v0.4 → v1 migration guide](docs/MIGRATION_v0.4_to_v1.md).

## [0.4.0] — Initial public release

- Single persistent FIFO queue of logical reservations.
- Configurable capacity and explicitly supervised `light`/`switch` entities.
- Safe OFF-confirmed release, fail-closed manual restart recovery,
  four diagnostic sensors and slot-granted event.
- Domain change from legacy Heating Queue Manager.

See [v0.4.0 release notes](docs/releases/v0.4.0.md).
