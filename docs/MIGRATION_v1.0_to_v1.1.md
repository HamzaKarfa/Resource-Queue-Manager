# Resource Queue Manager — Upgrade v1.0.0 → v1.1.0 (pre-release)

**Not published yet.** These steps are for the development candidate. HACS/Marketplace continues to install the published stable version, not stacked PR branches.

## Back up first

1. Back up the Home Assistant configuration and the relevant `.storage/resource_queue_manager.*` files; note each queue's config entry ID, supervised entities and current sensor entity IDs.
2. Record each queue's `active`/`waiting` attributes, strategy, capacity and status. Do not delete or manually clear a saved reservation to work around restoration errors.
3. Use a separate test HA installation (Home Assistant 2026.11+), with only noncritical devices/helpers, before changing production.
4. When testing a development branch, copy the *entire* custom component directory, not individual source files from different PRs.

## Backwards compatibility

- Existing queues with no `capacity_mode` or `recurrence_mode` configuration use `classic` and `ignore`.
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
| Scheduling | FIFO, LIFO, Priority FIFO | Unchanged; strict head-of-line, no preemption |

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

## Before resuming a migrated queue

1. Check stored active/waiting IDs and each physical entity's observed state. A reserved ON device may remain reserved; an ON device without a reservation blocks recovery.
2. Confirm `status == paused`, capacity mode and units in the sensor attributes, frozen effective weights and occurrence counts.
3. Run `resource_queue_manager.resume` using the queue's own config entry ID. New capacity may grant waiting work *only on this explicit resume*.
4. Confirm event metadata and sensor state through a test request and OFF-confirmed release.
5. Repeat with two independent queues and both `classic`/`weighted` modes.

## Configuration and migration rejection rules

- Switching strategy, capacity mode or recurrence mode while any active/waiting request exists is rejected.
- Reducing capacity below active usage or any pending request's frozen weight is rejected.
- Removing a supervised entity bound to a reservation is rejected.
- Corrupt or inconsistent saved weights, counts, bindings or unknown provider identifiers fail closed; **do not delete the stored file to force startup**.
- Weighted queues may legitimately have spare units while the first waiting request is too large to fit; smaller requests behind it do not skip the head.

## Rollback

**A downgrade from weighted/count state directly to v1.0 is not guaranteed to read the extended snapshot.** Keep the pre-upgrade Home Assistant backup and restore it *as a whole* if rolling back (code, config entries and persisted state together), while preserving any real-world changes made since the snapshot. Do not replace only the custom component while retaining newer active reservations.

## Validation status

Automated suites cover pure Python 3.13/3.14, Home Assistant fixture tests, HACS and hassfest in each PR. They are not a substitute for an independently verified upgrade/rollback with a live test Home Assistant instance. No automatic public release is authorized by this guide.
