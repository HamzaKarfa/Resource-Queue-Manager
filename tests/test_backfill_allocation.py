"""Pure-Python strict/backfill regression tests, independent from Home Assistant."""

from pathlib import Path
import sys
import types
import unittest

ROOT = Path(__file__).resolve().parents[1] / "custom_components"
package = types.ModuleType("resource_queue_manager")
package.__path__ = [str(ROOT / "resource_queue_manager")]
sys.modules.setdefault("resource_queue_manager", package)

from resource_queue_manager.allocation import validate_allocation_mode  # noqa: E402
from resource_queue_manager.coordinator import (  # noqa: E402
    QueueStateError,
    ResourceQueueCoordinator,
)
from resource_queue_manager.engine import ResourceQueue  # noqa: E402


class PureEngineBackfillTests(unittest.TestCase):
    def test_strict_default_preserves_head_of_line_and_available_units(self):
        q = ResourceQueue(15, capacity_mode="weighted")
        q.request("active", engine_data={"weight": 10})
        q.request("head", engine_data={"weight": 10})
        q.request("small", engine_data={"weight": 3})
        q.request("tiny", engine_data={"weight": 2})
        self.assertEqual(q.allocation_mode, "strict")
        self.assertEqual(q.snapshot().active, ("active",))
        self.assertEqual(q.snapshot().waiting, ("head", "small", "tiny"))
        self.assertEqual(q.capacity_remaining, 5)
        result = q.release("active")
        self.assertEqual(result.granted, ("head", "small", "tiny"))
        self.assertEqual(q.capacity_used, 15)

    def test_weighted_backfill_uses_remaining_units_without_reordering_head(self):
        q = ResourceQueue(15, capacity_mode="weighted", allocation_mode="backfill")
        self.assertEqual(q.request("active", engine_data={"weight": 10}).granted, ("active",))
        self.assertEqual(q.request("head", engine_data={"weight": 10}).granted, ())
        self.assertEqual(q.request("small", engine_data={"weight": 3}).granted, ("small",))
        self.assertEqual(q.request("tiny", engine_data={"weight": 2}).granted, ("tiny",))
        self.assertEqual(q.snapshot().active, ("active", "small", "tiny"))
        self.assertEqual(q.snapshot().waiting, ("head",))
        self.assertEqual(q.capacity_remaining, 0)
        self.assertEqual(q.release("active").granted, ("head",))
        self.assertEqual(q.snapshot().active, ("small", "tiny", "head"))
        self.assertEqual(q.capacity_used, 15)

    def test_priority_fifo_backfills_lower_priority_when_high_rank_cannot_fit(self):
        q = ResourceQueue(
            15, strategy="priority_fifo",
            capacity_mode="weighted", allocation_mode="backfill",
        )
        q.request("active", {"priority": 1}, engine_data={"weight": 10})
        q.request("urgent", {"priority": 10}, engine_data={"weight": 10})
        q.request("low", {"priority": 2}, engine_data={"weight": 3})
        q.request("medium", {"priority": 5}, engine_data={"weight": 2})
        self.assertEqual(q.snapshot().active, ("active", "low", "medium"))
        self.assertEqual(q.snapshot().waiting, ("urgent",))
        self.assertEqual(q.capacity_used, 15)
        result = q.release("active")
        self.assertEqual(result.granted, ("urgent",))
        self.assertEqual(q.snapshot().active, ("low", "medium", "urgent"))

    def test_priority_order_of_waiters_that_fit_is_still_respected(self):
        q = ResourceQueue(
            15, strategy="priority_fifo",
            capacity_mode="weighted", allocation_mode="backfill",
        )
        # Force all the arrivals into the waiting queue at capacity 15.
        q.request("holder", {"priority": 1}, engine_data={"weight": 15})
        q.request("low", {"priority": 1}, engine_data={"weight": 2})
        q.request("medium", {"priority": 5}, engine_data={"weight": 3})
        q.request("large", {"priority": 10}, engine_data={"weight": 14})
        self.assertEqual(q.snapshot().waiting, ("large", "medium", "low"))
        result = q.release("holder")
        self.assertEqual(result.granted, ("large",))
        self.assertEqual(result.waiting, ("medium", "low"))
        self.assertEqual(q.capacity_remaining, 1)
        self.assertEqual(q.release("large").granted, ("medium", "low"))

    def test_lowest_first_priority_and_lifo_work_with_backfill(self):
        q = ResourceQueue(
            10, strategy="priority_fifo",
            strategy_config={"priority_order": "lowest_first"},
            capacity_mode="weighted", allocation_mode="backfill",
        )
        q.request("holder", {"priority": 1}, engine_data={"weight": 10})
        q.request("p9", {"priority": 9}, engine_data={"weight": 3})
        q.request("p2", {"priority": 2}, engine_data={"weight": 8})
        q.request("p4", {"priority": 4}, engine_data={"weight": 7})
        self.assertEqual(q.snapshot().waiting, ("p2", "p4", "p9"))
        self.assertEqual(q.release("holder").granted, ("p2",))
        self.assertEqual(q.snapshot().waiting, ("p4", "p9"))
        self.assertEqual(q.release("p2").granted, ("p4", "p9"))

        lifo = ResourceQueue(
            10, strategy="lifo", capacity_mode="weighted", allocation_mode="backfill"
        )
        lifo.request("holder", engine_data={"weight": 10})
        lifo.request("first", engine_data={"weight": 3})
        lifo.request("second", engine_data={"weight": 7})
        self.assertEqual(lifo.snapshot().waiting, ("second", "first"))
        self.assertEqual(lifo.release("holder").granted, ("second", "first"))

    def test_backfill_does_not_change_classic_capacity_or_order(self):
        for strategy in ("fifo", "lifo"):
            with self.subTest(strategy=strategy):
                q = ResourceQueue(2, strategy=strategy, allocation_mode="backfill")
                q.request("a")
                q.request("b")
                q.request("c")
                self.assertEqual(q.capacity_used, 2)
                self.assertEqual(q.capacity_remaining, 0)
                self.assertEqual(q.release("a").granted, ("c" if strategy == "lifo" else "c",))
                self.assertEqual(q.capacity_used, 2)

    def test_backfill_repeated_pending_counter_remains_frozen_on_grant(self):
        q = ResourceQueue(
            10, strategy="priority_fifo", capacity_mode="weighted",
            allocation_mode="backfill", recurrence_mode="count"
        )
        q.request("active", {"priority": 1}, engine_data={"weight": 10})
        q.request("pending", {"priority": 10}, engine_data={"weight": 8})
        q.request("pending", {"priority": 10})
        q.request("pending", {"priority": 10})
        self.assertEqual(q.occurrences("pending"), 3)
        self.assertEqual(q.effective_weight("pending"), 8)
        self.assertEqual(q.snapshot().waiting, ("pending",))
        with self.assertRaisesRegex(ValueError, "different effective weight"):
            q.request("pending", {"priority": 10}, engine_data={"weight": 7})
        self.assertEqual(q.occurrences("pending"), 3)
        result = q.release("active")
        self.assertEqual(result.granted, ("pending",))
        self.assertEqual(q.occurrences("pending"), 3)
        q.request("pending", {"priority": 10})
        self.assertEqual(q.occurrences("pending"), 3)
        q.release("pending")
        self.assertIsNone(q.occurrences("pending"))

    def test_weighted_snapshot_restores_backfill_order_without_auto_grant(self):
        q = ResourceQueue(15, capacity_mode="weighted", allocation_mode="backfill")
        q.request("active", engine_data={"weight": 10})
        q.request("head", engine_data={"weight": 10})
        q.request("small", engine_data={"weight": 3})
        data = q.export_engine_request_data()
        restored = ResourceQueue.from_snapshot(
            15, list(q.snapshot().active), list(q.snapshot().waiting),
            capacity_mode="weighted", engine_request_data=data,
            allocation_mode="backfill",
        )
        self.assertEqual(restored.snapshot().granted, ())
        self.assertEqual(restored.snapshot().active, ("active", "small"))
        self.assertEqual(restored.snapshot().waiting, ("head",))
        self.assertEqual(restored.release("active").granted, ("head",))
        self.assertEqual(restored.capacity_used, 13)

    def test_allocation_mode_validation_rejects_unknown_values(self):
        for bad in ("unknown", "", None, True, [], 3):
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError):
                    validate_allocation_mode(bad)
                with self.assertRaises(ValueError):
                    ResourceQueue(5, allocation_mode=bad)


class CoordinatorBackfillRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.states = {f"light.test_{i}": "off" for i in range(1, 5)}
        self.entities = list(self.states)

    def create(self, allocation_mode="backfill"):
        return ResourceQueueCoordinator(
            15, self.states.get, self.entities, capacity_mode="weighted",
            entity_weights={
                self.entities[0]: 10, self.entities[1]: 10,
                self.entities[2]: 3, self.entities[3]: 2,
            }, allocation_mode=allocation_mode,
        )

    def restore(self, state, allocation_mode="backfill"):
        return ResourceQueueCoordinator.from_state(
            15, self.states.get, state, monitored_entities=self.entities,
            capacity_mode="weighted", allocation_mode=allocation_mode,
        )

    def test_restore_persists_policy_and_active_backfills_paused_until_resume(self):
        manager = self.create()
        manager.request("first", self.entities[0])
        manager.request("big", self.entities[1])
        manager.request("small", self.entities[2])
        manager.request("tiny", self.entities[3])
        state = manager.export_state()
        self.assertEqual(state["allocation_mode"], "backfill")
        self.assertEqual(state["waiting"], ["big"])
        restored = self.restore(state)
        self.assertTrue(restored.paused)
        self.assertEqual(restored.allocation_mode, "backfill")
        self.assertEqual(restored.snapshot().granted, ())
        self.assertEqual(restored.snapshot().active, ("first", "small", "tiny"))
        with self.assertRaises(QueueStateError):
            restored.release("first")
        restored.resume()
        self.assertEqual(restored.release("first").granted, ("big",))

    def test_legacy_snapshot_defaults_strict_and_refuses_nonempty_switch(self):
        manager = self.create("strict")
        manager.request("first", self.entities[0])
        manager.request("big", self.entities[1])
        saved = manager.export_state()
        saved.pop("allocation_mode")
        restored = self.restore(saved, allocation_mode="strict")
        self.assertEqual(restored.allocation_mode, "strict")
        with self.assertRaisesRegex(QueueStateError, "Cannot change allocation mode"):
            self.restore(saved, allocation_mode="backfill")

    def test_empty_snapshot_can_change_policy(self):
        state = self.create("strict").export_state()
        state.pop("allocation_mode")
        changed = self.restore(state)
        self.assertTrue(changed.paused)
        self.assertEqual(changed.allocation_mode, "backfill")

    def test_invalid_saved_policy_fails_closed_even_if_empty(self):
        original = self.create("strict").export_state()
        for mode in ("all", [], None):
            with self.subTest(mode=mode):
                changed = dict(original, allocation_mode=mode)
                with self.assertRaises(ValueError):
                    self.restore(changed, allocation_mode="strict")


if __name__ == "__main__":
    unittest.main()
