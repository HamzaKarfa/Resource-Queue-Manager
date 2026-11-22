# LIFO scheduling provider

**Key:** `lifo` · **Policy:** last in, first out (newest waiting request first).

A new pending request is inserted at the **front** of the waiting queue. On a verified release the newest waiting request is considered first. Already-active reservations are **never preempted**.

| Allocation mode | LIFO behavior |
| --- | --- |
| **Strict** (default) | A too-heavy newest waiter blocks older requests |
| **Backfill** | Older waiting requests that fit may be granted behind a blocked newer waiter, without moving that newer entry |

**Provider files:** [provider.py](provider.py), [strategy.py](strategy.py), [config.py](config.py), [request.py](request.py).

**Queue-wide strategy fields:** none. **Per-request strategy fields:** none. Capacity (Classic/Weighted), allocation (Strict/Backfill), weighted request overrides and recurrence are independent settings.

### Request example

```yaml
action: resource_queue_manager.request
data:
  config_entry_id: "YOUR_CONFIG_ENTRY_ID"
  resource_id: demo
  entity_id: light.demo_lamp
```

**Starvation risk:** a sustained stream of newer arrivals can indefinitely delay older requests. Backfill can improve the usage of remaining units but does not guarantee fairness. No aging or automatic priority promotion is implemented.

RQM requires a supervised ON/OFF device to report `off` before an active reservation can be released. A logical resource requires a known, available state.

[Main README](../../../../README.md) · [Strategy architecture](../README.md) · [Backfill behavior](../../../../docs/V1.2_BACKFILL.md)
