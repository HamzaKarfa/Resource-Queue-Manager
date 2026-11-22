[![Home Assistant](https://img.shields.io/badge/Home%20Assistant-Custom%20Integration-41BDF5?logo=homeassistant&logoColor=white)](https://www.home-assistant.io/)
[![HACS Marketplace](https://img.shields.io/badge/HACS-Marketplace-41BDF5)](https://hacs.xyz/)
[![Marketplace validation](https://github.com/HamzaKarfa/Resource-Queue-Manager/actions/workflows/validate.yml/badge.svg)](https://github.com/HamzaKarfa/Resource-Queue-Manager/actions/workflows/validate.yml)
[![Home Assistant tests](https://github.com/HamzaKarfa/Resource-Queue-Manager/actions/workflows/home-assistant-tests.yml/badge.svg)](https://github.com/HamzaKarfa/Resource-Queue-Manager/actions/workflows/home-assistant-tests.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

![Resource Queue Manager logo](assets/icon.png)

# Resource Queue Manager

[![Add to My Home Assistant](https://my.home-assistant.io/badges/marketplace_repository.svg)](https://my.home-assistant.io/redirect/marketplace_repository/?owner=HamzaKarfa&repository=Resource-Queue-Manager&category=integration)

**Français :** [guide d'installation, configuration et migration](README.fr.md).

**Resource Queue Manager** manages multiple independent resource queues in Home Assistant with **FIFO, LIFO and priority-based scheduling**, configurable capacity and persistent reservations. Each queue has its own supervised entities and state. It coordinates logical grants; your automations remain responsible for switching devices.

> **Versioning:** Marketplace/HACS installs a published release, not an unreleased branch. Check the installed version before following the v1 instructions. When evaluating code ahead of a release, use a separate test instance and start with a noncritical entity.

> **Important:** Resource Queue Manager never switches devices ON or OFF. Your automations do that after obtaining a grant. It is **not a certified electrical load-shedding, thermal safety or overcurrent protection device**. Manual commands, external automation and unsupervised equipment can bypass it.

## v1.1.0-rc.2 — Backfill and redesigned Home Assistant configuration

A new per-queue **allocation mode** lets you keep the default **Strict** head-of-line behavior or select **Backfill** to grant later requests that fit remaining capacity. Priority FIFO/FIFO/LIFO still determine the waiting order; Backfill may bypass a higher-priority request **only when it does not fit**, and may starve large requests under sustained small arrivals. Classic capacity remains compatible and usually behaves identically under either mode.

For example, with 15 total units, an active weight-10 reservation and a waiting weight-10 request, Backfill can still grant following weights 3 and 2. In Strict mode those requests all remain waiting until the head fits.

Switching allocation modes requires an empty queue. The four existing sensors gain `allocation_mode`, and grant events include it. Legacy configurations and snapshots default to `strict`. This feature is included in the **v1.1.0-rc.2 release candidate** and was not part of `v1.1.0-rc.1`. It is not part of stable v1.0.0.

See [Backfill behavior, risks and configuration](docs/V1.2_BACKFILL.md) and [the new four-category configuration menu](docs/CONFIGURATION_UI_v1.1-rc2.md). Each category can be edited independently; initial setup is guided.

## v1.1 release candidate — not stable

> **Pre-release v1.1.0-rc.2:** This branch is the integrated candidate containing the v1.1 feature stack and the new Backfill/UI improvements. It is intended for testing only; `main` and stable v1.0.0 remain unchanged. Read the [RC2 notes](docs/releases/v1.1.0-rc.2.md), [migration guide](docs/MIGRATION_v1.0_to_v1.1.md) and [manual acceptance gates](docs/RELEASE_CHECKLIST_v1.1.md) before installing.


The v1.1 feature branches add a **third independent concern** to each queue. Scheduling still chooses the next request (FIFO/LIFO/Priority FIFO), capacity decides how much can run, and recurrence decides what to do when the same waiting `resource_id` is requested again. These features are **not available in published v1.0.0**.

| Setting | Default (compatible with v1.0) | Optional v1.1 behavior |
| --- | --- | --- |
| Scheduling | FIFO (or an existing v1 strategy) | FIFO, LIFO or Priority FIFO — unchanged |
| Capacity mode | `classic`: 1–50 active slots | `weighted`: a shared 1–100000 unit budget, **no second slot limit** |
| Entity weight | 1 per active slot | Native numeric default for every supervised entity, initially 1 |
| Repeated request | `ignore`: idempotent | `count`: count repeated **waiting** requests with the same `resource_id` |

In weighted mode, this example overrides the entity's configured default **for one new request**, without modifying the saved default:

```yaml
action: resource_queue_manager.request
data:
  config_entry_id: YOUR_QUEUE_ENTRY_ID
  resource_id: heater_living_room
  entity_id: light.heater_living_room
  engine_data:
    weight: 25
```

The weight is frozen for the lifetime of the request (including waiting and restart). Only active reservations consume units. The default **Strict** allocation mode blocks smaller requests behind a heavy head-of-line request; optional **Backfill** may grant requests that fit, without moving the blocked request in the queue.

With recurrence set to `count`, the first request has occurrence count 1; subsequent calls for the **same waiting** `resource_id` increment its count, without changing queue position, priority, capacity or number of entries. Calls for an active ID do not increase it. Grant events add `occurrences`, `effective_weight` and `capacity_mode`; existing sensors keep their IDs and expose `capacity_unit`, `capacity_total`, `capacity_used`, `capacity_remaining`, `effective_weights` and `occurrence_counts` attributes.

**Version compatibility:** existing queues stay `classic + ignore`. Old YAML requires no edits. A queue still restarts paused and must be resumed after checking supervised entities. Switching policies with existing active/waiting requests is rejected. The application does not switch devices or calculate watts.

**Before testing v1.1**, read the [v1.0 → v1.1 migration guide](docs/MIGRATION_v1.0_to_v1.1.md), [recurrence guide](docs/V1.1_RECURRENCE.md) and [maintainer release checklist](docs/RELEASE_CHECKLIST_v1.1.md). These are pre-release features, not a stable installation; test separately and keep a rollback backup.

## What's new in v1

- **Multiple named queues** in one integration: e.g. Heating (capacity 3), Ventilation (2), Irrigation (1).
- **Independent strategies**, selected per queue during setup:
  - **FIFO** — oldest waiting request first (default and v0.4-compatible).
  - **LIFO** — newest waiting request first.
  - **Priority FIFO** — priority ranking with FIFO order for equal priorities.
- **Provider-based architecture**: each strategy ships its own `provider.py`, `config.py`, `request.py` and `strategy.py`. The core engine is not coupled to an algorithm.
- **Strategy-specific settings and request data** validated by the chosen provider.
- **Independent persistence and recovery**: every queue starts `paused` after reload and requires its own explicit `resume`.
- **Unambiguous service routing** with `config_entry_id` when multiple entries exist.
- Four read-only diagnostic sensors **per queue**, with strategy and entry ID in their attributes.

See [v1 architecture](docs/V1_ARCHITECTURE.md), [migration guide](docs/MIGRATION_v0.4_to_v1.md), [developer setup](docs/DEVELOPMENT.md), [changelog](CHANGELOG.md) and [v1 release notes](docs/releases/v1.0.0.md).

For maintainers: [v1 release acceptance checklist](docs/RELEASE_CHECKLIST_v1.md) (manual test and publication gates).

## Scheduling example

Suppose a queue has **one** slot. Four requests arrive in this order: A, B, C, D. A is granted immediately and continues running; B/C/D are waiting.

| Strategy | Waiting order after A is granted | Next grant after A is released |
| --- | --- | --- |
| FIFO | B → C → D | B |
| LIFO | D → C → B | D |
| Priority FIFO | Sorted by priority, then arrival order | Highest-ranked waiter |

For Priority FIFO, let B have priority 4, C have priority 8 and D have priority 4. With the default `highest_first` option, the waiting order is **C → B → D**. With `lowest_first`, it is **B → D → C**. Equal-priority requests remain FIFO.

**All strategies are non-preemptive:** an already-active reservation is never revoked just because a more important request arrives. Priority FIFO can starve low-priority requests under sustained high-priority traffic; there is no aging or automatic priority escalation in v1.

## Installation

**Requirements:** Home Assistant **2026.11.0 or newer**. Any existing Home Assistant entity may be supervised, including native `number.*` / `text.*` entities and `input_number.*`, `input_text.*`, `input_boolean.*` helpers.

### Stable installation from Marketplace

Go to **Settings → Marketplace**, search for *Resource Queue Manager*, install and restart Home Assistant. If the repository is not visible, use the Marketplace's **Add from link** feature with `https://github.com/HamzaKarfa/Resource-Queue-Manager`.

Marketplace installs the latest published stable version. To inspect unreleased changes, follow the development instructions below and check the corresponding branch/version.

### Testing an unreleased development branch

Use a **separate Home Assistant test instance**, or make a full backup first and disable real-device automations. Files from a feature branch are not automatically part of the Marketplace release.

1. Browse [the development branch](https://github.com/HamzaKarfa/Resource-Queue-Manager/tree/docs/v1.1-regression-release-readiness/custom_components/resource_queue_manager) when it exists, or the branch under review.
2. Copy the **whole** `custom_components/resource_queue_manager` directory from the selected branch into the test instance's `config/custom_components/resource_queue_manager`; do not mix component files from different versions.
3. Restart Home Assistant, then go to **Settings → Devices & services → Add integration → Resource Queue Manager**.
4. Add an entry and configure a **test lamp** or other low-risk entity. Repeat to test a second queue.
5. Confirm the queue's `status` sensor reads `paused`; inspect supervised entity states and explicitly call `resume` for that entry.
6. Exercise a request, an active grant, a waiting request, an OFF-verified release, a cancellation and a restart before using more complex automations.

Avoid overwriting a working HACS-managed installation with a feature branch on a production system. Restore the stable version from a backup if you decide not to continue testing.

### First configuration: one queue

When adding **Resource Queue Manager**, enter a unique queue name (e.g. *Heating*), the number of simultaneous reservations (1–50), a strategy and any Home Assistant entities supervised by that queue. You can add more entries afterward using **Add integration** again.

An entity may be supervised by **only one queue**, and each queue has its own capacity. There is **no shared electrical power limit** across queues.

Choosing **Priority FIFO** displays an additional provider-specific setup step:

| Setting | Values | Meaning |
| --- | --- | --- |
| `priority_order` | `highest_first` (default), `lowest_first` | Whether priority 10 or 1 wins first |

Each Priority FIFO request must contain `strategy_data.priority`, a numeric value from **1 to 10**. FIFO and LIFO do not accept `priority` or any other provider-specific request fields.

### Recovery: explicitly resume each queue

All queues are restored in `paused` state after Home Assistant startup, integration reload or options changes. Inspect supervised entities before resuming. Binary ON/OFF entities must report `on` or `off`; an ON entity without an active reservation blocks recovery. Logical entities must report an available, known state. See **Supervision modes** below.

In **Developer tools → Actions**, select `resource_queue_manager.resume` and specify the queue:

```yaml
action: resource_queue_manager.resume
data:
  config_entry_id: "YOUR_CONFIG_ENTRY_ID"
```

The `config_entry_id` is the Home Assistant **configuration entry ID**, not the queue name, entity ID or resource ID. The action editor offers a queue selector. The queue's status sensor must read `ready` before making requests.

With **exactly one configured queue**, old v0.4 calls with no `config_entry_id` still work. As soon as two or more queues are configured, **every** `request`, `release`, `cancel` and `resume` action must select its entry, even if the other entry is currently unloaded.

## Actions, events and safe reservation lifecycle

Home Assistant's **Developer tools → Actions** exposes the native `request`, `release`, `cancel` and `resume` actions (with localized labels). The screenshot below shows the actions as they appear in a French-language Home Assistant instance.

![Resource Queue Manager actions in Home Assistant — request, release, cancel and resume](assets/resource-queue-manager-actions.webp)

**Quick UI smoke test on a noncritical device:** select `resource_queue_manager.resume` for the **test queue** after verifying supervised devices; call `request` using that queue's `config_entry_id`, a unique `resource_id` and a supervised test `entity_id`; confirm the corresponding `active` sensor increments; keep the test device OFF and call `release`; confirm the count returns to its previous value. Also test `cancel` on a waiting request. Never test first with a live heater or bypass physical protections.

| Action | Required data | Optional data | Purpose |
| --- | --- | --- | --- |
| `resource_queue_manager.request` | `resource_id`, `entity_id` | `config_entry_id`, `strategy_data` | Acquire capacity or join a waiting queue |
| `resource_queue_manager.release` | `resource_id` | `config_entry_id` | Confirm OFF for ON/OFF entities; require a known state for logical entities |
| `resource_queue_manager.cancel` | `resource_id` | `config_entry_id` | Withdraw a waiting request or safely release an active reservation |
| `resource_queue_manager.resume` | — | `config_entry_id` | Validate supervised states and resume after reload |

Note that `config_entry_id` is effectively **required for all four actions when multiple queues exist**.

**Physical ON/OFF lifecycle:** Request → reservation becomes active or waits → automation confirms grant → automation switches device ON → automation switches device OFF → Home Assistant reports `off` → automation releases reservation → next waiting request is granted. Logical resources use the same booking lifecycle but do not use an OFF signal.

The integration fires `resource_queue_manager_slot_granted` with `resource_id`, `entity_id` and `config_entry_id` after persisting newly granted slots. Events are not replayed for existing grants. Use the relevant queue sensor's `active` attribute to verify a grant even if an event was missed.

### Supervision modes: physical vs. logical resources

The entity selector is **domain-neutral**. Every queue still requires an actual entity to exist and be explicitly selected as supervised. The service `entity_id` is **required** for each `request`.

| Entity domains | Supervision rule | Active reservation release |
| --- | --- | --- |
| `light`, `switch`, `fan`, `input_boolean` | Reject unavailable, unknown and any non-ON/OFF state; reject ON without a booking | Requires observed `off` |
| `number`, `text`, `input_number`, `input_text`, `input_select`, `sensor`, other domains | Require an existing, known state (not `unknown`/`unavailable`) | Known state is enough; no OFF check |

**Safety boundary:** a generic entity's state does **not** confirm that a physical actuator has stopped. Use a supervised ON/OFF entity, or independent hardware safety, for physical electrical loads. Merely supervising a number or text helper must never be used as proof of power isolation.

### FIFO or LIFO request

```yaml
action: resource_queue_manager.request
data:
  config_entry_id: "YOUR_CONFIG_ENTRY_ID"
  resource_id: demo_lamp
  entity_id: light.demo_lamp
```

### Priority FIFO request

```yaml
action: resource_queue_manager.request
data:
  config_entry_id: "YOUR_PRIORITY_QUEUE_ENTRY_ID"
  resource_id: bedroom
  entity_id: switch.bedroom_test_relay
  strategy_data:
    priority: 8
```

Priority must be supplied on **every new** Priority FIFO request. The same `resource_id` cannot change its entity binding or request priority while active/waiting; cancel or safely release it first. Unknown provider fields and out-of-range values are rejected.

### Release or cancel

For an ON/OFF entity (light, switch, fan or input_boolean), **wait until Home Assistant reports `off`** before releasing. For a generic number/text/sensor entity, a valid available state is sufficient to release the logical booking; this is **not** evidence that a physical device is safe to switch:

```yaml
action: resource_queue_manager.release
data:
  config_entry_id: "YOUR_CONFIG_ENTRY_ID"
  resource_id: bedroom
```

Use `resource_queue_manager.cancel` with the same entry ID and resource ID to withdraw a waiting request. Cancellation of an active ON/OFF reservation also requires its entity to report OFF; generic entities require an available state.

### Low-risk test automation

Create an `input_button.queue_demo` helper; supervise a real **test light** `light.demo_lamp` in your new queue. Find its actual **active sensor entity ID** under Devices & services → Entities (for example `sensor.heating_test_active`) and replace the placeholders below. Do not use this example on an unattended heater.

```yaml
alias: "Resource Queue v1 - test lamp"
mode: single
triggers:
  - trigger: state
    entity_id: input_button.queue_demo
actions:
  - action: resource_queue_manager.request
    data:
      config_entry_id: "YOUR_CONFIG_ENTRY_ID"
      resource_id: demo_lamp
      entity_id: light.demo_lamp
      # For Priority FIFO only, add:
      # strategy_data:
      #   priority: 5
  - wait_template: >
      {{ 'demo_lamp' in (state_attr('sensor.YOUR_QUEUE_active', 'active') or []) }}
    timeout: "00:02:00"
    continue_on_timeout: true
  - if:
      - condition: template
        value_template: "{{ not wait.completed }}"
    then:
      - action: resource_queue_manager.cancel
        data:
          config_entry_id: "YOUR_CONFIG_ENTRY_ID"
          resource_id: demo_lamp
      - stop: "Timed out waiting for reservation"
  - action: light.turn_on
    target:
      entity_id: light.demo_lamp
  - delay: "00:00:15"
  - action: light.turn_off
    target:
      entity_id: light.demo_lamp
  - wait_template: "{{ is_state('light.demo_lamp', 'off') }}"
    timeout: "00:00:30"
    continue_on_timeout: false
  - action: resource_queue_manager.release
    data:
      config_entry_id: "YOUR_CONFIG_ENTRY_ID"
      resource_id: demo_lamp
```

A stopped automation, lost connection or HA restart can leave a reservation active. This example is **not fault tolerant**; reconcile the actual device states and saved reservations before issuing `resume` or re-running a resource.

## Diagnostics and troubleshooting

Each entry owns four sensors. Newly added queues use their entry title in their sensor names. The **legacy v0.4 entry preserves** its existing Resource Queue sensor names and unique IDs. Check the actual entity IDs in Home Assistant; do not assume a name is fixed.

| Sensor (typical suffix) | State | Attributes |
| --- | --- | --- |
| `*_active` | Active reservation count | `active` (resource IDs) |
| `*_waiting` | Waiting request count | `waiting` (next-grant order) |
| `*_available` | Grantable slots; 0 if paused | `max_active` |
| `*_status` | `paused` or `ready` | `recovery_issues`, `monitored_entities` |

All sensors also expose `strategy`, `config_entry_id`, active/waiting IDs and safety state. Priority values are persisted internally as request metadata; the basic sensor lists remain **ID-only**.

| Symptom | Check |
| --- | --- |
| Action says `specify config_entry_id` | Two or more queues are configured; select the owning entry in **all** actions. |
| Queue is paused after restart or options change | Expected. Inspect supervised entities, then call `resume` on that queue. |
| `resume` refuses to run | Inspect the queue's `recovery_issues` attribute; fix missing/unavailable entities, or ON/OFF entities powered ON without a booking. |
| `request` rejects `priority` | Priority goes inside `strategy_data` and is only supported by **Priority FIFO**. |
| Priority request fails for missing metadata | Provide `strategy_data: {priority: 1}` through `{priority: 10}` (inclusive). |
| Two queues cannot monitor the same entity | This is intentional. Assign each supervised entity to one queue only. |
| Queue is not granting | Confirm its `status` is `ready`, its capacity and the supervised entity states. |
| A lower-priority request never runs | Priority FIFO is non-preemptive and does not have aging; frequent high-priority arrivals may cause starvation. |
| Changing strategy or configuration is refused | Empty the active and waiting lists safely before switching policies or provider-specific settings. |
| Release/cancel fails | ON/OFF entities must **report** `off`; generic logical entities must be available (not `unknown`/`unavailable`). |
| A grant event was missed | Read that specific queue's `active` sensor attribute. |

**Safety reminder:** reservation capacity does not measure electrical current or force devices OFF. Keep independent protection devices, thermal limits, and normal circuit protection.

## Upgrading from v0.4

The existing `resource_queue_manager` domain, config-entry ID, storage key, legacy FIFO ordering and old action names are retained. **There is no automatic strategy migration**: old entries default to FIFO. The v1 snapshot adds optional `strategy`, `strategy_config` and `request_data` fields. Old snapshots without these fields continue to load as FIFO.

Before adding a second entry, update existing automations to pass the legacy queue's **actual `config_entry_id`** on all four actions. Back up Home Assistant and disable real-equipment automations while testing. After the upgrade, verify the saved active/waiting lists and supervised entity states, then explicitly `resume` the original queue.

Read the [detailed v0.4 → v1 migration procedure](docs/MIGRATION_v0.4_to_v1.md). Migration from the **older `heating_queue_manager` integration** is separate: it used a different domain and is not automatic.

## Development, compatibility and release

```bash
python -m unittest discover -s tests -v
python -m pip install "pytest-homeassistant==2026.11.1"
python -m pytest -q tests/ha
```

CI also validates HACS/Marketplace metadata and Home Assistant hassfest. Tests simulate Home Assistant states, **not physical devices**. See [DEVELOPMENT.md](docs/DEVELOPMENT.md) for environment setup and plugin development.

The current development branch deliberately keeps the stable manifest version **1.0.0**. A v1.1 release requires separately approved version-bump and publication steps. **None of these development PRs merges, tags or publishes a release automatically.**

The repository is distributed under the [MIT License](LICENSE).
