[![Home Assistant](https://img.shields.io/badge/Home%20Assistant-Custom%20Integration-41BDF5?logo=homeassistant&logoColor=white)](https://www.home-assistant.io/)
[![HACS Marketplace](https://img.shields.io/badge/HACS-Marketplace-41BDF5)](https://hacs.xyz/)
[![Marketplace validation](https://github.com/HamzaKarfa/Resource-Queue-Manager/actions/workflows/validate.yml/badge.svg)](https://github.com/HamzaKarfa/Resource-Queue-Manager/actions/workflows/validate.yml)
[![Home Assistant tests](https://github.com/HamzaKarfa/Resource-Queue-Manager/actions/workflows/home-assistant-tests.yml/badge.svg)](https://github.com/HamzaKarfa/Resource-Queue-Manager/actions/workflows/home-assistant-tests.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

![Resource Queue Manager logo](assets/icon.png)

# Resource Queue Manager

[![Add to My Home Assistant](https://my.home-assistant.io/badges/marketplace_repository.svg)](https://my.home-assistant.io/redirect/marketplace_repository/?owner=HamzaKarfa&repository=Resource-Queue-Manager&category=integration)

**Français :** [Documentation en français](README.fr.md) · [Changelog](CHANGELOG.md) · [Migration v1.0 → v1.1](docs/MIGRATION_v1.0_to_v1.1.md)

**Resource Queue Manager (RQM)** is a Home Assistant custom integration for managing **multiple independent queues of logical resource reservations**. Each queue has its own supervised entities, strategy, capacity, pending requests, recovery state and diagnostic sensors. Your automations request a grant and control the associated devices; RQM never powers equipment on or off itself.

> **Version status:** This README prepares the upcoming **v1.1.0 stable** release. The complete implementation is available in the published [v1.1.0-rc.2 pre-release](https://github.com/HamzaKarfa/Resource-Queue-Manager/releases/tag/v1.1.0-rc.2). At documentation-preparation time, [v1.0.0](https://github.com/HamzaKarfa/Resource-Queue-Manager/releases/tag/v1.0.0) is still the latest **stable** version. Check your installed version; v1.1 features are not available in v1.0.0.
>
> **Safety:** Reservations are logical. RQM is **not** a certified load-shedding device, power/current meter or electrical/thermal protection system. Independent hardware and electrical protections remain necessary.

## Features in v1.1

| Independent setting | Choices | Default / behavior |
| --- | --- | --- |
| Scheduling | **FIFO**, **LIFO**, **Priority FIFO** | FIFO; waiting-order selection, no active preemption |
| Capacity | **Classic** or **Weighted** | Classic; 1–50 simultaneous slots |
| Weighted capacity | A shared budget of **1–100000 integer units** | No extra slot limit; entity default weight 1 |
| Allocation | **Strict** or **Backfill** | Strict; stop at the first waiting request that does not fit |
| Repeated requests | **Ignore** or **Count** | Ignore; pending duplicates are idempotent |
| Supervision | ON/OFF devices and logical Home Assistant entities | Each entity belongs to a single queue |
| Durability | Persisted reservations, frozen weights and recurrence counts | Restore `paused`; manual `resume` after state checks |

**One queue ≠ global budget:** different queue instances have separate capacities. Weighted units are arbitrary units, **not automatically watts**.

### Scheduling: FIFO, LIFO and Priority FIFO

- **FIFO:** the oldest waiting request is considered first.
- **LIFO:** the newest waiting request is considered first.
- **Priority FIFO:** requests are ordered by numeric `strategy_data.priority` (1–10); ties preserve FIFO order. Queue setting `priority_order` is `highest_first` (10 ahead of 1, default) or `lowest_first` (1 ahead of 10).

All strategies are **non-preemptive**: a new high-priority request cannot revoke an existing active grant. FIFO/LIFO/Priority FIFO determine waiting order; **allocation mode** determines which requests that fit may be granted from that order.

### Allocation: Strict versus Backfill

Suppose the capacity is **15 units**, A is active using 10, and B (10 units), C (3 units), D (2 units) wait in that order.

| Resource | Weight | Strict | Backfill |
| --- | ---: | --- | --- |
| A | 10 | Active | Active |
| B | 10 | Waiting | Waiting |
| C | 3 | Waiting | **Granted** |
| D | 2 | Waiting | **Granted** |
| Units used | — | **10/15** | **15/15** |

- **Strict:** B blocks every request behind it until it fits.
- **Backfill:** C and D can use unused units even though B does not fit. B retains its place, metadata and recurrence count; no active booking is preempted.
- Under Priority FIFO, a lower-priority request **can bypass** a higher-priority one *that cannot fit*. Backfill improves utilization but may cause a large request to **starve** under sustained smaller arrivals. There is no automatic aging or fairness guarantee.

[Detailed Backfill behavior](docs/V1.2_BACKFILL.md)

### Weighted entities and per-request overrides

In **Weighted** mode, configure a positive integer default weight for each supervised entity. This value is used when a **new** request is created; changing a default does not retroactively change active/pending request weights.

A request may override the default *for that request only* with `engine_data.weight`. Its effective cost is frozen while waiting, active and after Home Assistant restarts.

```yaml
action: resource_queue_manager.request
data:
  config_entry_id: "YOUR_CONFIG_ENTRY_ID"
  resource_id: heater_living_room
  entity_id: light.heater_living_room
  engine_data:
    weight: 25
```

The override must be a positive integer that fits the configured budget. Classic mode always uses **one slot per resource** and does not support weighted overrides. Repeating an existing resource ID cannot change its frozen weight.

### Repeated requests: Ignore or Count

A repeated `request` for the **same pending `resource_id`**:

- `ignore` (default): remains a single queue entry with occurrence count 1.
- `count`: increments `occurrences` for that entry (1, 2, 3, …) without modifying its position, priority, effective weight or capacity use.

Repeated requests for an **already active** ID do not increment the count. Releasing or cancelling the resource deletes its count; a future new request starts at 1. Duplicates must keep the same entity and provider-specific strategy data.

Occurrence counts are observable in `occurrence_counts` sensor attributes and in `resource_queue_manager_slot_granted` events. **Count is metadata**, not an instruction to run a job several times.

## Installation

**Minimum supported Home Assistant version:** **2026.11.0**.

For a **published stable release**, open **Settings → Marketplace**, search for *Resource Queue Manager*, install or update, then restart Home Assistant. If necessary, add the repository URL:

```text
https://github.com/HamzaKarfa/Resource-Queue-Manager
```

Marketplace/HACS stable installs the latest published stable tag. **Until v1.1.0 is actually published as stable, the stable channel remains v1.0.0.** Do not expect the v1.1 settings to appear in that installation.

To test the release candidate, select the published [v1.1.0-rc.2 release](https://github.com/HamzaKarfa/Resource-Queue-Manager/releases/tag/v1.1.0-rc.2) on a separate Home Assistant test installation. Do not mix files from different tags in `custom_components/resource_queue_manager/`. Back up Home Assistant and its `.storage` data before an upgrade; read [the migration and rollback guide](docs/MIGRATION_v1.0_to_v1.1.md).

## Setup: create and configure a queue

Open **Settings → Devices & services → Add integration → Resource Queue Manager**. The guided setup presents:

1. **Queue name and supervised entities** — choose existing HA entities (each entity can be supervised by only one queue).
2. **Capacity** — Classic (1–50 slots) or Weighted (1–100000 units), and its limit.
3. **Scheduling and allocation** — FIFO, LIFO or Priority FIFO; Strict or Backfill.
4. **Strategy details** — only when required, e.g. Priority FIFO direction.
5. **Repeated requests** — Ignore or Count.
6. **Default entity weights** — only for Weighted queues with supervised entities.

Add another integration entry to create another independent queue. For editing an entry, select **Configure** to see four separate categories:

| Category | What can be changed |
| --- | --- |
| **Supervised resources** | Entities; their default weights if Weighted |
| **Capacity** | Classic/Weighted and total slot/unit budget |
| **Scheduling and allocation** | FIFO/LIFO/Priority FIFO; Strict/Backfill; optionally priority direction |
| **Repeated requests** | Ignore/Count for pending duplicates |

Opening a category does **not** pause the queue. Saving an accepted change triggers a reload; the queue starts **paused** and must be resumed. **Policy changes with active/waiting work are blocked**, as is removing a supervised entity with an outstanding request. Capacity reductions must still accommodate all frozen active/pending costs.

[Configuration screens and behavior](docs/CONFIGURATION_UI_v1.1-rc2.md)

## Services and examples

Home Assistant exposes four actions: `resource_queue_manager.request`, `release`, `cancel` and `resume`. The actions are configured via **Developer tools → Actions** or automation YAML.

| Action | Required fields | Optional fields | Result |
| --- | --- | --- | --- |
| `request` | `resource_id`, `entity_id` | `config_entry_id`, `strategy_data`, `engine_data` | Grants a booking or places it in waiting |
| `release` | `resource_id` | `config_entry_id` | Releases a booking only after the supervision check |
| `cancel` | `resource_id` | `config_entry_id` | Withdraws waiting work or safely releases active work |
| `resume` | — | `config_entry_id` | Validates supervised entity states and resumes a paused queue |

**When two or more queues are configured, `config_entry_id` becomes mandatory for every action**, even if another queue is temporarily unloaded. It is the HA configuration **entry ID**, not the queue title or resource ID. The action editor provides a selector.

### Resume after startup or configuration change

```yaml
action: resource_queue_manager.resume
data:
  config_entry_id: "YOUR_CONFIG_ENTRY_ID"
```

Each queue restores in `paused` state. Examine its four sensors, actual entity states and `recovery_issues` before calling `resume`. Existing active bookings are **not replayed as new grant events**.

### Priority FIFO + Weighted + Backfill + Count

The following request works on a queue already configured with these options:

```yaml
action: resource_queue_manager.request
data:
  config_entry_id: "YOUR_CONFIG_ENTRY_ID"
  resource_id: living_room_test
  entity_id: light.living_room_test
  strategy_data:
    priority: 8
  engine_data:
    weight: 5
```

A duplicate pending request can repeat the same `resource_id`, `entity_id` and `strategy_data.priority`; omit `engine_data` to retain the existing frozen weight (including an earlier override).

### Release or cancel

Switch an ON/OFF device **OFF first**, and wait until HA actually reports `off` before releasing:

```yaml
action: resource_queue_manager.release
data:
  config_entry_id: "YOUR_CONFIG_ENTRY_ID"
  resource_id: living_room_test
```

`cancel` uses the same fields; cancelling a waiting request is immediate, but cancelling an active ON/OFF booking also requires the observed OFF state.

### Automation pattern

A safe logical pattern is: **request → verify active grant → turn ON (if applicable) → turn OFF → verify OFF → release**. Do not switch a real load ON merely because a request was submitted: the request may remain waiting. Read the matching queue's `active` list or listen for `resource_queue_manager_slot_granted`. If an automation times out or restarts, reconcile existing reservations before retrying.

For a practical example, see the [Home Assistant action examples](docs/V1.1_HA_CAPACITY_SETUP.md). The integration does not automatically execute queued work or multiple occurrences.

## Supervision rules

| Entity domain | Observed state requirement | Active booking release |
| --- | --- | --- |
| `light`, `switch`, `fan`, `input_boolean` | Known `on`/`off`; reject ON without a matching active booking | Must report `off` |
| `sensor`, `binary_sensor`, `number`, `text`, `input_number`, `input_text` and other domains | Must be present and neither `unknown` nor `unavailable` | Known state sufficient for **logical** release |

A `binary_sensor` is **not** treated as an ON/OFF actuator by this integration; it is a logical supervised entity. Its state must not be taken as proof of electrical isolation. Physical equipment must use appropriate actual ON/OFF feedback and independent protection.

## Diagnostics and events

Each queue exposes **four existing sensors** (actual entity IDs depend on the entry title and HA entity registry):

| Sensor suffix | State |
| --- | --- |
| `_active` | Number of active reservations |
| `_waiting` | Number of waiting requests |
| `_available` | Free **slots** in Classic or **units** in Weighted; **0 while paused** |
| `_status` | `ready` or `paused` |

All four provide attributes including `active`, `waiting`, `strategy`, `config_entry_id`, `max_active`, `capacity_mode`, `capacity_unit`, `capacity_total`, `capacity_used`, `capacity_remaining`, `effective_weights`, `allocation_mode`, `recurrence_mode`, `occurrence_counts`, `monitored_entities`, `paused` and `recovery_issues`.

The `resource_queue_manager_slot_granted` event is emitted **after durable state persistence** for each newly granted resource and includes:

```yaml
event_type: resource_queue_manager_slot_granted
data:
  resource_id: living_room_test
  entity_id: light.living_room_test
  config_entry_id: YOUR_CONFIG_ENTRY_ID
  capacity_mode: weighted
  allocation_mode: backfill
  effective_weight: 5
  occurrences: 3
```

This is an **illustrative event payload**, not a command. Values depend on the request and queue. Events are not replayed for active reservations after restart.

### Troubleshooting

| Symptom | Check |
| --- | --- |
| No new v1.1 fields | Verify installed version; stable v1.0.0 does not have them |
| Category menu shows empty labels | Refresh the HA frontend (hard reload) and restart HA to refresh translated strings |
| Queue shows `paused` | Expected on reload; inspect `recovery_issues` and call `resume` after checking entities |
| `config_entry_id` error | Select the correct entry for **every** action in a multi-queue setup |
| Queue does not allocate despite available units | In **Strict**, a larger first waiter can block smaller ones; choose Backfill only after the queue is empty |
| Priority rejected | Supply `strategy_data: {priority: 1..10}` on Priority FIFO; omit on FIFO/LIFO |
| Duplicate rejected | Keep the same resource/entity, priority and frozen weight |
| Cannot release an active device | The supervised ON/OFF entity must report `off` |
| Configuration change rejected | Empty the active/waiting reservations, or keep the existing policy |

## Migration and release validation

- **From v1.0.0:** existing queues default to Classic + Ignore + Strict when the new options are absent. Existing sensor IDs and action names remain. New weighted metadata and counts are stored without changing ID-only active/waiting lists.
- **From v0.4:** historical single FIFO configurations are supported; see [v0.4 → v1](docs/MIGRATION_v0.4_to_v1.md).
- **Rollback:** restoring the previous code alone after using the new snapshot format is **not guaranteed**. Use a matching Home Assistant backup (code, entry configuration and `.storage` state).

[Detailed v1.0 → v1.1 migration guide](docs/MIGRATION_v1.0_to_v1.1.md) · [Developer guide](docs/DEVELOPMENT.md) · [Release acceptance checklist](docs/RELEASE_CHECKLIST_v1.1.md) · [Draft v1.1.0 stable notes](docs/releases/v1.1.0-draft.md)

The v1.1 release remains subject to final review, real Home Assistant migration/rollback tests and explicit publication approval. Do not infer stable availability from these prepared README files.

## License

Distributed under the [MIT License](LICENSE).
