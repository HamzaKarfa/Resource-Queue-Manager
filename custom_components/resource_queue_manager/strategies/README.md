# Scheduling strategy providers

Resource Queue Manager v1.1 separates **four independent responsibilities**:

1. **Scheduling strategy** — FIFO, LIFO or Priority FIFO decides the waiting order.
2. **Allocation mode** — Strict stops at the first request that cannot fit; Backfill may grant later requests that fit without reordering blocked entries.
3. **Capacity policy** — Classic counts slots; Weighted counts positive integer units with frozen per-request costs.
4. **Recurrence policy** — Ignore or Count repeated requests for the same *waiting* resource ID.

A strategy implementation is a pure-Python provider registered **explicitly** in [registry.py](registry.py); modules are not dynamically loaded from user input.

| Plugin | Ordering | Per-request metadata | Queue configuration |
| --- | --- | --- | --- |
| [FIFO](fifo/README.md) | Oldest pending first | None | None |
| [LIFO](lifo/README.md) | Newest pending first | None | None |
| [Priority FIFO](priority_fifo/README.md) | Priority ranking, FIFO ties | `priority` (1–10) | `priority_order` |

## Provider structure

Every strategy folder supplies:

- `provider.py`: stable key, labels, supported configuration/request descriptors and a factory returning a **fresh** strategy instance.
- `strategy.py`: `enqueue(waiting, request, requests)` implementation — **waiting order only**.
- `config.py`: queue-wide settings, rendered by native Home Assistant selectors when needed.
- `request.py`: per-request provider metadata validation.

The generic [engine](../engine.py) controls allocations, frozen costs, idempotent/counting requests and persistence. The [coordinator](../coordinator.py) validates supervised entities and safe release. **Neither strategy plugins nor Backfill may bypass supervision, change an active booking, switch real devices, or overcommit capacity.**

In the v1.1 Home Assistant interface, strategy and allocation settings are under **Configure → Scheduling and allocation**. Strategy-specific options only appear when needed or requested.

## Backfill interaction

Given 15 weighted units, an active 10-unit reservation, then waiting requests of weights 10, 3 and 2, **Strict** waits at the blocked 10-unit head; **Backfill** can grant weights 3 and 2. The strategy's existing waiting order is preserved for skipped requests.

Priority FIFO's preference is not a strict guarantee of next service when Backfill is on: a lower-priority **fitting** request can pass a higher-priority **non-fitting** request. No priority aging or starvation protection exists.

Read the [developer guide](../../../docs/DEVELOPMENT.md), [Backfill design](../../../docs/V1.2_BACKFILL.md) and [main README](../../../README.md) before introducing another provider.

**Availability:** these APIs are part of **Resource Queue Manager v1.1.0**, first validated in the [v1.1.0-rc.2 prerelease](https://github.com/HamzaKarfa/Resource-Queue-Manager/releases/tag/v1.1.0-rc.2). They were not available in v1.0.0.
