"""Weighted capacity and frozen entity weight tests; no Home Assistant required."""

from pathlib import Path
import sys
import types
import unittest

COMPONENTS_DIR = Path(__file__).resolve().parents[1] / "custom_components"
package = types.ModuleType("resource_queue_manager")
package.__path__ = [str(COMPONENTS_DIR / "resource_queue_manager")]
sys.modules.setdefault("resource_queue_manager", package)

from resource_queue_manager.capacity import (  # noqa: E402
    get_capacity_policy, get_capacity_provider,
)
from resource_queue_manager.coordinator import (  # noqa: E402
    QueueStateError, ResourceQueueCoordinator,
)
from resource_queue_manager.engine import ResourceQueue  # noqa: E402


class WeightedCapacityTests(unittest.TestCase):
    def queue(self, capacity=10, strategy="fifo"):
        return ResourceQueue(capacity, strategy=strategy, capacity_mode="weighted")

    def test_providers_and_default_classic_unchanged(self):
        self.assertEqual(get_capacity_provider("weighted").key, "weighted")
        self.assertIsNot(get_capacity_policy("weighted"), get_capacity_policy("weighted"))
        self.assertEqual(ResourceQueue(3).capacity_mode, "classic")
        classic = ResourceQueue(2)
        with self.assertRaisesRegex(ValueError, "does not accept engine_data"):
            classic.request("a", engine_data={"weight": 1})
        classic.request("a")
        self.assertEqual(classic.effective_weight("a"), 1)
        self.assertEqual(classic.export_engine_request_data(), {})
        self.assertEqual(classic.capacity_remaining, 1)

    def test_budget_and_release_promote_fifo(self):
        q = self.queue(100)
        for resource, units in (("a", 40), ("b", 30), ("c", 20), ("d", 25)):
            q.request(resource, engine_data={"weight": units})
        self.assertEqual(q.snapshot().active, ("a", "b", "c"))
        self.assertEqual(q.snapshot().waiting, ("d",))
        self.assertEqual(q.capacity_used, 90)
        self.assertEqual(q.capacity_remaining, 10)
        self.assertEqual(q.release("b").granted, ("d",))
        self.assertEqual(q.snapshot().active, ("a", "c", "d"))
        self.assertEqual(q.capacity_used, 85)
        self.assertEqual(q.export_engine_request_data()["d"], {"weight": 25})

    def test_head_of_line_blocking_never_skips_small_request(self):
        q = self.queue(100)
        q.request("active", engine_data={"weight": 70})
        q.request("large", engine_data={"weight": 40})
        q.request("small", engine_data={"weight": 20})
        self.assertEqual(q.snapshot().waiting, ("large", "small"))
        self.assertEqual(q.capacity_remaining, 30)
        self.assertEqual(q.release("active").granted, ("large", "small"))
        self.assertEqual(q.capacity_remaining, 40)

    def test_weighted_mode_has_no_separate_slot_limit(self):
        q = self.queue(100)
        for i in range(70):
            q.request(f"r{i}")
        self.assertEqual(len(q.snapshot().active), 70)
        self.assertEqual(q.capacity_used, 70)
        self.assertEqual(q.capacity_remaining, 30)

    def test_all_six_combinations_keep_strategies_independent(self):
        for mode in ("classic", "weighted"):
            for strategy in ("fifo", "lifo", "priority_fifo"):
                with self.subTest(mode=mode, strategy=strategy):
                    q = ResourceQueue(
                        1 if mode == "classic" else 6,
                        strategy=strategy,
                        capacity_mode=mode,
                    )
                    for i, (rid, weight) in enumerate(
                        (("a", 6), ("b", 2), ("c", 3), ("d", 1)), start=1
                    ):
                        priority = {"priority": i} if strategy == "priority_fifo" else None
                        engine = {"weight": weight} if mode == "weighted" else None
                        q.request(rid, priority, engine_data=engine)
                    expected = {
                        "fifo": ("b", "c", "d"),
                        "lifo": ("d", "c", "b"),
                        "priority_fifo": ("d", "c", "b"),
                    }[strategy]
                    self.assertEqual(q.snapshot().waiting, expected)
                    result = q.release("a")
                    self.assertEqual(
                        result.granted, expected if mode == "weighted" else expected[:1]
                    )
                    self.assertEqual(q.capacity_used, 6 if mode == "weighted" else 1)

    def test_default_and_one_request_override_do_not_mutate_defaults(self):
        q = self.queue(10)
        q.request("busy", engine_data={"weight": 10})
        q.request("pending", default_weight=4)
        self.assertEqual(q.effective_weight("pending"), 4)
        self.assertEqual(q.request("pending", default_weight=2).granted, ())
        self.assertEqual(q.effective_weight("pending"), 4)
        self.assertEqual(q.request("pending", engine_data={"weight": 4}).granted, ())
        with self.assertRaisesRegex(ValueError, "different effective weight"):
            q.request("pending", engine_data={"weight": 5})
        self.assertEqual(q.snapshot().waiting, ("pending",))
        self.assertEqual(q.release("busy").granted, ("pending",))
        self.assertEqual(q.effective_weight("pending"), 4)

    def test_invalid_weight_inputs_and_oversize_rejected_atomically(self):
        q = self.queue(10)
        for invalid in (
            {"weight": 0}, {"weight": -1}, {"weight": True},
            {"weight": 2.5}, {"weight": "4"}, {"weight": 11},
            {"weight": float("inf")}, {"weight": float("nan")},
            {"weight": 3, "unknown": 1},
            "not a mapping",
        ):
            with self.subTest(invalid=invalid):
                with self.assertRaises(ValueError):
                    q.request("x", engine_data=invalid)
                self.assertEqual(q.snapshot().waiting, ())
                self.assertEqual(q.snapshot().active, ())
        for weight in (0, True, 11, 1.5):
            with self.subTest(default=weight), self.assertRaises(ValueError):
                q.request("x", default_weight=weight)

    def test_restore_frozen_weights_and_allow_unused_units_with_waiters(self):
        q = self.queue(10)
        q.request("a", engine_data={"weight": 7})
        q.request("b", engine_data={"weight": 5})
        q.request("c", engine_data={"weight": 2})
        snapshot = q.snapshot()
        weights = q.export_engine_request_data()
        recovered = ResourceQueue.from_snapshot(
            10, list(snapshot.active), list(snapshot.waiting),
            capacity_mode="weighted", engine_request_data=weights,
        )
        self.assertEqual(recovered.snapshot(), snapshot)
        self.assertEqual(recovered.export_engine_request_data(), weights)
        self.assertEqual(recovered.release("a").granted, ("b", "c"))
        self.assertEqual(recovered.capacity_used, 7)

    def test_bad_weighted_snapshot_fails_closed(self):
        cases = [
            ({"a": {"weight": 4}}, ["a"], ["b"]),
            ({"a": {"weight": 4}, "b": {"weight": True}}, ["a"], ["b"]),
            ({"a": {"weight": 4}, "b": {"weight": 0}}, ["a"], ["b"]),
            ({"a": {"weight": 11}, "b": {"weight": 1}}, ["a"], ["b"]),
            ({"a": {"weight": 4}, "b": {"weight": 1}}, ["a"], ["b"]),
            ({"a": {"weight": 7}, "b": {"weight": 4}}, ["a", "b"], []),
            ({"a": {"weight": 4}, "b": {"weight": 3}, "x": {"weight": 1}}, ["a"], ["b"]),
        ]
        for metadata, active, waiting in cases:
            with self.subTest(metadata=metadata), self.assertRaises(ValueError):
                ResourceQueue.from_snapshot(
                    10, active, waiting, capacity_mode="weighted",
                    engine_request_data=metadata,
                )
        with self.assertRaises(ValueError):
            ResourceQueue.from_snapshot(
                10, ["a"], [], capacity_mode="classic",
                engine_request_data={"a": {"weight": 1}},
            )


class WeightedCoordinatorTests(unittest.TestCase):
    def setUp(self):
        self.entities = {f"light.r{i}": "off" for i in range(1, 6)}

    def manager(self, capacity=10, weights=None, strategy="fifo"):
        return ResourceQueueCoordinator(
            capacity, self.entities.get, self.entities,
            strategy=strategy, capacity_mode="weighted", entity_weights=weights,
        )

    def test_per_entity_default_and_override_are_frozen(self):
        manager = self.manager(weights={"light.r1": 7, "light.r2": 2})
        manager.request("a", "light.r1")
        manager.request("b", "light.r2", engine_data={"weight": 3})
        manager.request("c", "light.r3")
        self.assertEqual(manager.entity_weights["light.r1"], 7)
        self.assertEqual(manager.entity_weights["light.r2"], 2)
        self.assertEqual(manager.queue.effective_weight("a"), 7)
        self.assertEqual(manager.queue.effective_weight("b"), 3)
        self.assertEqual(manager.queue.effective_weight("c"), 1)
        self.assertEqual(manager.capacity_used, 10)
        self.assertEqual(manager.capacity_remaining, 0)
        self.assertEqual(manager.export_state()["entity_weights"]["light.r2"], 2)

    def test_restart_preserves_weight_and_accepts_changed_default(self):
        m = self.manager(weights={"light.r1": 10, "light.r2": 3})
        m.request("a", "light.r1")
        m.request("b", "light.r2")
        saved = m.export_state()
        restored = ResourceQueueCoordinator.from_state(
            10, self.entities.get, saved, monitored_entities=self.entities,
            capacity_mode="weighted", entity_weights={"light.r1": 5, "light.r2": 6},
        )
        self.assertTrue(restored.paused)
        self.assertEqual(restored.entity_weights["light.r1"], 5)
        self.assertEqual(restored.queue.effective_weight("a"), 10)
        self.assertEqual(restored.queue.effective_weight("b"), 3)
        restored.resume()
        self.assertEqual(restored.request("b", "light.r2").granted, ())
        self.assertEqual(restored.release("a").granted, ("b",))
        self.assertEqual(restored.queue.effective_weight("b"), 3)
        self.assertEqual(restored.capacity_used, 3)

    def test_restart_uses_saved_defaults_when_not_overridden(self):
        m = self.manager(weights={"light.r1": 5})
        m.request("a", "light.r1")
        recovered = ResourceQueueCoordinator.from_state(
            10, self.entities.get, m.export_state(),
            monitored_entities=self.entities, capacity_mode="weighted",
        )
        self.assertEqual(recovered.entity_weights["light.r1"], 5)

    def test_change_capacity_mode_with_nonempty_work_is_blocked(self):
        m = self.manager()
        m.request("a", "light.r1")
        with self.assertRaisesRegex(QueueStateError, "Cannot change capacity mode"):
            ResourceQueueCoordinator.from_state(
                10, self.entities.get, m.export_state(),
                monitored_entities=self.entities, capacity_mode="classic",
            )
        m.release("a")
        classic = ResourceQueueCoordinator.from_state(
            3, self.entities.get, m.export_state(),
            monitored_entities=self.entities, capacity_mode="classic",
        )
        self.assertEqual(classic.capacity_mode, "classic")

    def test_capacity_decrease_validates_active_and_waiting_weights(self):
        m = self.manager(weights={"light.r1": 7, "light.r2": 5})
        m.request("a", "light.r1")
        m.request("b", "light.r2")
        saved = m.export_state()
        with self.assertRaises(QueueStateError):
            ResourceQueueCoordinator.from_state(
                6, self.entities.get, saved,
                monitored_entities=self.entities, capacity_mode="weighted",
            )
        recovered = ResourceQueueCoordinator.from_state(
            9, self.entities.get, saved,
            monitored_entities=self.entities, capacity_mode="weighted",
        )
        self.assertEqual(recovered.capacity_remaining, 2)
        self.assertEqual(recovered.snapshot().waiting, ("b",))

    def test_invalid_entity_defaults_and_overrides_are_rejected(self):
        for weights in (
            {"light.r1": 0}, {"light.r1": True},
            {"light.r1": 11}, {"light.unknown": 2},
        ):
            with self.subTest(weights=weights), self.assertRaises(QueueStateError):
                self.manager(weights=weights)
        m = self.manager()
        with self.assertRaises(QueueStateError):
            m.request("a", "light.r1", engine_data={"weight": 0})
        self.assertEqual(m.snapshot().active, ())

    def test_active_relay_off_verification_remains_required(self):
        m = self.manager()
        m.request("a", "light.r1", engine_data={"weight": 4})
        self.entities["light.r1"] = "on"
        with self.assertRaises(QueueStateError):
            m.release("a")
        self.assertEqual(m.capacity_used, 4)
        self.entities["light.r1"] = "off"
        m.release("a")
        self.assertEqual(m.capacity_used, 0)

    def test_legacy_snapshot_remains_classic(self):
        classic = ResourceQueueCoordinator(
            2, self.entities.get, self.entities,
        )
        classic.request("a", "light.r1")
        saved = classic.export_state()
        saved.pop("capacity_mode")
        saved.pop("engine_request_data")
        saved.pop("entity_weights")
        recovered = ResourceQueueCoordinator.from_state(
            2, self.entities.get, saved, monitored_entities=self.entities,
        )
        self.assertTrue(recovered.paused)
        self.assertEqual(recovered.capacity_mode, "classic")
        self.assertEqual(recovered.snapshot().active, ("a",))


if __name__ == "__main__":
    unittest.main()
