# Changelog

Notable changes to Resource Queue Manager follow semantic versioning. GitHub tags use a leading `v`; the version in `custom_components/resource_queue_manager/manifest.json` must match the tag's numeric part.

## [1.1.0] — stable

**Stable release changes.** These capabilities were validated in the published [v1.1.0-rc.2 pre-release](https://github.com/HamzaKarfa/Resource-Queue-Manager/releases/tag/v1.1.0-rc.2). See [v1.1.0 release notes](docs/releases/v1.1.0.md) and the migration guide.

### Added

- **Weighted capacity**: one shared budget of 1–100000 integer units per queue, with default weight 1 per supervised entity and configurable defaults.
- **Immutable per-request cost**: `engine_data.weight` overrides an entity's configured default only for a new Weighted request. Active/pending weights survive restart and release returns exactly the frozen cost.
- **Configurable allocation**: `strict` preserves head-of-line blocking; `backfill` grants fitting requests behind a non-fitting head without changing the ordering or preempting active work.
- **Recurrence counting**: `ignore` (default) or `count` repeated requests for one waiting `resource_id`, without new queue entries or extra capacity usage. Active duplicates do not increment.
- **Guided Home Assistant setup** with conditional capacity/priority/weight screens, and a four-category **Configure** menu for resources, capacity, scheduling/allocation and repetitions.
- **Richer diagnostics** on the four existing sensors: `capacity_mode`, `capacity_unit`, `capacity_total`, `capacity_used`, `capacity_remaining`, `effective_weights`, `allocation_mode`, `recurrence_mode`, `occurrence_counts`.
- **Extended grant events**: `capacity_mode`, `allocation_mode`, `effective_weight` and `occurrences` alongside the original resource/entity/config entry identifiers.
- **Migration and tests** for legacy snapshots, paused recovery, validation of invalid weights/counts, multiple queues, Strict/Backfill, persistence-before-event and English/French translations.

### Preserved compatibility and guarantees

- Existing configurations without the new fields default to **Classic + Strict + Ignore**; no new constraints on old Classic slot use.
- Existing `request`/`release`/`cancel`/`resume` action names, `strategy_data`, `config_entry_id` routing, four sensor entity IDs, and FIFO/LIFO/Priority FIFO strategy ordering.
- Each queue still restores **paused**. An explicit `resume` is necessary after checking supervised states. Invalid/unsafe snapshots must not silently discard active reservations.
- No active preemption, direct physical device control, global inter-queue capacity, watts calculation, message-content deduplication, automatic multi-job execution, priority aging or anti-starvation guarantee.

### Migration and release

- [Migration v1.0.0 → v1.1.0](docs/MIGRATION_v1.0_to_v1.1.md)
- [Backfill allocation](docs/V1.2_BACKFILL.md)
- [Configuration menu](docs/CONFIGURATION_UI_v1.1-rc2.md)
- [v1.1.0 stable release notes](docs/releases/v1.1.0.md)
- [Stable acceptance checklist](docs/RELEASE_CHECKLIST_v1.1.md)

**Publishing:** the stable tag `v1.1.0` is created only by the guarded workflow after the explicitly authorized PR #32 merge, final automated checks and a duplicate-tag check.

## [Pre-release] — v1.1.0-rc.2

Published pre-release integrating Weighted capacity, recurrence counting, Strict/Backfill, protected recovery and the redesigned Home Assistant configuration interface. See [RC2 notes](docs/releases/v1.1.0-rc.2.md); this prerelease remains in the historical release list.

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
