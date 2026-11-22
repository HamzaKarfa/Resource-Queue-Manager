# Priority FIFO scheduling provider

**Key:** `priority_fifo` · **Policy:** priority ranking, with FIFO order for equal priorities. **Existing active reservations are never preempted.**

## Settings and request contract

| Field | Where | Allowed values |
| --- | --- | --- |
| `priority_order` | Queue's Scheduling and allocation settings | `highest_first` (default: 10 before 1) or `lowest_first` (1 before 10) |
| `strategy_data.priority` | Every **new** request | Numeric priority from **1 to 10** |
| `engine_data.weight` | Optional new request, **Weighted capacity only** | Positive integer at or below queue capacity |

The strategy metadata is validated and frozen for the life of an active or pending request. A duplicate resource ID must keep the same entity and priority. To change priority, first cancel a waiting request or safely release an active one, then create a new request.

### Example

```yaml
action: resource_queue_manager.request
data:
  config_entry_id: "YOUR_CONFIG_ENTRY_ID"
  resource_id: bedroom
  entity_id: switch.bedroom_test_relay
  strategy_data:
    priority: 8
  # Weighted queues may additionally use:
  # engine_data:
  #   weight: 5
```

The Home Assistant configuration wizard asks for `priority_order` when Priority FIFO is selected. Existing queues expose it under **Configure → Scheduling and allocation → Edit priority settings**, without forcing re-entry when switching only Strict/Backfill.

## Priority and Backfill

The strategy arranges pending requests in priority order; ties remain FIFO.

- **Strict** (default): if the highest-ranked pending request cannot fit, lower-ranked requests must wait.
- **Backfill**: if the highest-ranked pending request cannot fit, lower-ranked requests **that fit** may be granted; the blocked request keeps its priority, position, weight and occurrence count.

A high-priority request therefore has **no absolute guarantee of being served first under Backfill**. Priority starvation is possible in either mode with frequent high-priority arrivals; Backfill may also starve large, non-fitting requests. RQM does not implement priority aging or future-capacity reservations.

## Provider structure and persistence

- [provider.py](provider.py): provider registration and factory.
- [strategy.py](strategy.py): rank pending requests without preempting active bookings.
- [config.py](config.py): `priority_order` selector.
- [request.py](request.py): required `priority` descriptor.

Priority metadata is persisted independently of the active/waiting ID lists. After restart the queue is `paused` until supervised states are checked and `resume` is called. Repeated pending IDs are counted only if the queue uses the independent `count` policy.

[Strategy architecture](../README.md) · [Configuration guide](../../../../README.md) · [Migration v1.0 → v1.1](../../../../docs/MIGRATION_v1.0_to_v1.1.md)
