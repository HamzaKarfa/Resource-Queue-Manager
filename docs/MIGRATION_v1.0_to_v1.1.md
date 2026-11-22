# Resource Queue Manager — Upgrade from v1.0.0 to v1.1.0

This guide covers upgrading from **v1.0.0** to **v1.1.0 stable**. The previous [v1.1.0-rc.2 release candidate](https://github.com/HamzaKarfa/Resource-Queue-Manager/releases/tag/v1.1.0-rc.2) remains available as a historical test build. Verify the installed version before changing any configuration.

## Back up first

1. Back up the Home Assistant configuration and the relevant `.storage/resource_queue_manager.*` files; note each queue's config entry ID, supervised entities and current sensor entity IDs.
2. Record each queue's `active`/`waiting` attributes, strategy, capacity and status. Do not delete or manually clear a saved reservation to work around restoration errors.
3. Use a separate test HA installation (Home Assistant 2026.11+), with only noncritical devices/helpers, before changing production.
4. When testing a development branch, copy the *entire* custom component directory, not individual source files from different PRs.

## Backwards compatibility

- Existing queues without the new configuration fields use **`classic` (capacity), `ignore` (recurrence) and `strict` (allocation)**; no explicit conversion of their settings is required.
- Classic still reserves one slot per active request; old `resource_queue_manager.request`, `release`, `cancel`, and `resume` YAML remains valid.
- Existing four per-queue sensor identifiers are preserved. Active and waiting attributes remain lists of resource IDs.
- New configuration names, weights and counters are stored per queue; old snapshots without them are migrated in memory and saved at the next normal state change.
- Queue strategy remains independent of capacity/repetition settings. Existing priority order/metadata are unchanged.
- All queues still reload `paused`; `resume` is required before further allocation, and an observed unsafe ON/OFF state blocks the recovery.
- With two or more configured queues, actions still require `config_entry_id`.

## New configuration modes

| Concern | v1.0 behavior (default) | v1.1 optional behavior |
|---|---|---|
| Capacity | Classic, 1–50 active slots | Weighted, one 1–100000 unit budget, **no second slot limit** |
| Per entity | All reservations consume one slot | Each supervised `entity_id` gets a default integer weight (initial 1) |
| Request override | Not required | `engine_data.weight` overrides its entity default **for one new request** |
| Duplicate requests | Ignore/idempotent | Count occurrences of identical *waiting* `resource_id` |
| Scheduling | FIFO, LIFO, Priority FIFO | Unchanged strategy order and non-preemption |
| Allocation | Strict head-of-line | Optional **Backfill** scans later fitting waiters while preserving blocked request order |

### Weighted example

A queue with total capacity **100 units** and a default entity weight of **30** can receive a request costing **25** units without changing its configured default:

```yaml
action: resource_queue_manager.request
data:
  config_entry_id: YOUR_QUEUE_ENTRY_ID
  resource_id: living_room_heater
  entity_id: light.living_room_heater
  engine_data:
    weight: 25
```

The effective weight is frozen while the request waits, runs and is restored. Repeating the same `resource_id` with no override does not recalculate its weight from updated defaults. Invalid, unknown or nonpositive weights fail explicitly.

### Occurrence example

Under `recurrence_mode: count`, the first pending request has `occurrences: 1`. Two identical repeat calls for its `resource_id` produce `occurrences: 3` without creating new queue entries. Active requests do not accrue further counts. The count is available in `occurrence_counts` sensor attributes and the `resource_queue_manager_slot_granted` event. Release or cancellation resets the count.

## New options interface

After upgrade, **Configure** opens a four-category menu: **Supervised resources**, **Capacity**, **Scheduling and allocation**, and **Repeated requests**. Opening it does not pause the queue. An accepted change reloads the entry and requires a checked `resume`. Policy changes (strategy, capacity mode, allocation mode or recurrence mode) cannot be made with active or waiting work.

Backfill uses unused capacity behind a blocked head. For example, with a budget of 15 units, A active with weight 10 and B first waiting with weight 10, later C (3) and D (2) may be granted under Backfill while B stays waiting. Under Strict, C and D stay waiting too. **Backfill may starve high-weight or higher-priority requests.**

When changing the capacity limit, defaults that exceed the new budget require review; existing frozen requests and active reservations must remain grantable. See [the settings menu](CONFIGURATION_UI_v1.1-rc2.md) and [Backfill behavior](V1.2_BACKFILL.md).

## Before resuming a migrated queue

1. Check stored active/waiting IDs and each physical entity's observed state. A reserved ON device may remain reserved; an ON device without a reservation blocks recovery.
2. Confirm `status == paused`, capacity mode and units in the sensor attributes, frozen effective weights and occurrence counts.
3. Run `resource_queue_manager.resume` using the queue's own config entry ID. New capacity may grant waiting work *only on this explicit resume*.
4. Confirm event metadata and sensor state through a test request and OFF-confirmed release.
5. Repeat with two independent queues and both `classic`/`weighted` modes.

## Configuration and migration rejection rules

- Switching strategy, capacity mode, **allocation mode** or recurrence mode while any active/waiting request exists is rejected.
- Reducing capacity below active usage or any pending request's frozen weight is rejected.
- Removing a supervised entity bound to a reservation is rejected.
- Corrupt or inconsistent saved weights, counts, bindings or unknown provider identifiers fail closed; **do not delete the stored file to force startup**.
- Weighted **Strict** queues may have spare units while the first waiting request is too large to fit; later requests cannot skip it. In **Backfill**, later requests that fit may be granted without changing the blocked request's position.

## Rollback

**A downgrade from weighted/count state directly to v1.0 is not guaranteed to read the extended snapshot.** Keep the pre-upgrade Home Assistant backup and restore it *as a whole* if rolling back (code, config entries and persisted state together), while preserving any real-world changes made since the snapshot. Do not replace only the custom component while retaining newer active reservations.

## Validation status

Automated suites cover Python 3.13/3.14, Home Assistant 2026.11 fixtures, HACS and hassfest. The RC2 candidate passed these checks, and the guarded stable workflow repeats them on the exact PR #32 merge SHA. **A real-HA backup, migration and rollback rehearsal still requires manual verification**; the CI suite does not guarantee those operations on a production instance.
