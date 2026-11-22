# FIFO scheduling provider

**Key:** `fifo` · **Policy:** first in, first out (oldest waiting request first).

FIFO controls **waiting order only**. It does not grant capacity or operate Home Assistant devices. Once an active reservation is released safely, the queue engine considers the oldest pending request. An already-active grant is never preempted.

| Allocation mode | FIFO behavior |
| --- | --- |
| **Strict** (default) | If the first pending request cannot fit, all later requests remain waiting |
| **Backfill** | If the first pending request cannot fit, later requests that fit can receive grants; the blocked request keeps its position |

**Provider files:** [provider.py](provider.py), [strategy.py](strategy.py), [config.py](config.py), [request.py](request.py).

**Queue-wide strategy fields:** none. **Per-request strategy fields:** none. Capacity mode (Classic/Weighted), effective weight, allocation mode and recurrence mode are configured **independently** of FIFO.

### Basic request

```yaml
action: resource_queue_manager.request
data:
  config_entry_id: "YOUR_CONFIG_ENTRY_ID"
  resource_id: demo
  entity_id: light.demo_lamp
```

For a **Weighted** queue, you may also supply `engine_data: {weight: 3}` to override this new request's entity default. Duplicate waiting requests can be counted if the queue uses `recurrence_mode: count`. Neither option changes FIFO's order.

FIFO is the default strategy and preserves the legacy single-queue behavior during migration. All queues restart in `paused` and need an explicit `resume` after supervising entity states.

[Main README](../../../../README.md) · [v1.0 → v1.1 migration](../../../../docs/MIGRATION_v1.0_to_v1.1.md) · [Strategy architecture](../README.md)
