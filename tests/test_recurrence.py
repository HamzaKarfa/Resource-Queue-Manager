"""Recurrence counting is independent of scheduling and capacity; no HA dependencies."""

from pathlib import Path
import sys
import types
import unittest

COMPONENTS_DIR = Path(__file__).resolve().parents[1] / "custom_components"
package = types.ModuleType("resource_queue_manager")
package.__path__ = [str(COMPONENTS_DIR / "resource_queue_manager")]
sys.modules.setdefault("resource_queue_manager", package)

from resource_queue_manager.engine import ResourceQueue  # noqa: E402
from resource_queue_manager.coordinator import (  # noqa: E402
    QueueStateError, ResourceQueueCoordinator,
)
from resource_queue_manager.recurrence import (  # noqa: E402
    DEFAULT_RECURRENCE_MODE, get_recurrence_policy,
)


class RecurrenceTests(unittest.TestCase):
    def test_default_ignore_remains_idempotent(self):
        q = ResourceQueue(1)
        self.assertEqual(q.recurrence_mode, DEFAULT_RECURRENCE_MODE)
        q.request("active")
        q.request("pending")
        for _ in range(3):
            q.request("pending")
            q.request("active")
        self.assertEqual(q.snapshot().waiting, ("pending",))
        self.assertEqual(q.export_occurrence_counts(), {"active": 1, "pending": 1})
        self.assertEqual(q.release("active").granted, ("pending",))
        self.assertEqual(q.occurrences("pending"), 1)

    def test_provider_registry_produces_independent_policies(self):
        self.assertIsNot(get_recurrence_policy("count"), get_recurrence_policy("count"))
        with self.assertRaisesRegex(ValueError, "Unsupported recurrence"):
            get_recurrence_policy("bogus")
        with self.assertRaises(ValueError):
            ResourceQueue(recurrence_mode="bogus")

    def test_all_twelve_strategy_capacity_and_recurrence_combinations(self):
        for strategy in ("fifo", "lifo", "priority_fifo"):
            for capacity_mode in ("classic", "weighted"):
                for recurrence_mode in ("ignore", "count"):
                    with self.subTest(
                        strategy=strategy, capacity=capacity_mode,
                        recurrence=recurrence_mode,
                    ):
                        q = ResourceQueue(
                            1 if capacity_mode == "classic" else 5,
                            strategy=strategy,
                            capacity_mode=capacity_mode,
                            recurrence_mode=recurrence_mode,
                        )
                        for index, rid in enumerate(("a", "b", "c", "d"), start=1):
                            strategy_data = (
                                {"priority": index} if strategy == "priority_fifo" else None
                            )
                            engine_data = (
                                {"weight": 5 if rid == "a" else 1}
                                if capacity_mode == "weighted" else None
                            )
                            q.request(rid, strategy_data, engine_data=engine_data)
                        expected = {
                            "fifo": ("b", "c", "d"),
                            "lifo": ("d", "c", "b"),
                            "priority_fifo": ("d", "c", "b"),
                        }[strategy]
                        self.assertEqual(q.snapshot().waiting, expected)
                        metadata = {"priority": 2} if strategy == "priority_fifo" else None
                        q.request("b", metadata)
                        q.request("b", metadata)
                        q.request(
                            "a",
                            {"priority": 1} if strategy == "priority_fifo" else None,
                        )
                        self.assertEqual(q.snapshot().waiting, expected)
                        self.assertEqual(q.occurrences("b"), 3 if recurrence_mode == "count" else 1)
                        self.assertEqual(q.occurrences("a"), 1)
                        if capacity_mode == "weighted":
                            self.assertEqual(q.capacity_used, 5)
                        result = q.release("a")
                        self.assertEqual(
                            result.granted,
                            expected if capacity_mode == "weighted" else expected[:1],
                        )
                        self.assertEqual(q.occurrences("b"), 3 if recurrence_mode == "count" else 1)
                        self.assertIsNone(q.occurrences("a"))
                        q.request("b", metadata)
                        # An already-granted request is never recounted.
                        if "b" in q.snapshot().active:
                            self.assertEqual(
                                q.occurrences("b"), 3 if recurrence_mode == "count" else 1
                            )

    def test_pending_count_survives_restart_then_grant_and_release(self):
        q = ResourceQueue(1, recurrence_mode="count")
        q.request("busy")
        q.request("tts_garage")
        q.request("tts_garage")
        q.request("tts_garage")
        saved = q.snapshot()
        restored = ResourceQueue.from_snapshot(
            1, list(saved.active), list(saved.waiting),
            recurrence_mode="count",
            occurrence_counts=q.export_occurrence_counts(),
        )
        self.assertEqual(restored.occurrences("tts_garage"), 3)
        self.assertEqual(restored.release("busy").granted, ("tts_garage",))
        self.assertEqual(restored.occurrences("tts_garage"), 3)
        restored.request("tts_garage")
        self.assertEqual(restored.occurrences("tts_garage"), 3)
        restored.release("tts_garage")
        self.assertIsNone(restored.occurrences("tts_garage"))
        restored.request("tts_garage")
        self.assertEqual(restored.occurrences("tts_garage"), 1)

    def test_duplicate_metadata_rejection_is_atomic(self):
        q = ResourceQueue(10, strategy="priority_fifo", capacity_mode="weighted", recurrence_mode="count")
        q.request("busy", {"priority": 4}, engine_data={"weight": 10})
        q.request("tts", {"priority": 8}, engine_data={"weight": 3})
        q.request("tts", {"priority": 8})
        self.assertEqual(q.occurrences("tts"), 2)
        with self.assertRaisesRegex(ValueError, "different request metadata"):
            q.request("tts", {"priority": 9})
        with self.assertRaisesRegex(ValueError, "different effective weight"):
            q.request("tts", {"priority": 8}, engine_data={"weight": 4})
        self.assertEqual(q.occurrences("tts"), 2)
        self.assertEqual(q.effective_weight("tts"), 3)
        self.assertEqual(q.snapshot().waiting, ("tts",))

    def test_corrupt_count_snapshot_fails_closed(self):
        for counts in ({}, {"a": 1}, {"a": 1, "b": True},
                       {"a": 1, "b": 0}, {"a": 1, "b": -3},
                       {"a": 1, "b": 3.5}, {"a": 1, "b": 2, "ghost": 1},
                       ["a", "b"]):
            with self.subTest(counts=counts), self.assertRaises(ValueError):
                ResourceQueue.from_snapshot(
                    1, ["a"], ["b"], recurrence_mode="count",
                    occurrence_counts=counts,
                )
        with self.assertRaisesRegex(ValueError, "missing occurrence counts"):
            ResourceQueue.from_snapshot(1, ["a"], [], recurrence_mode="count")
        with self.assertRaisesRegex(ValueError, "ignore-mode"):
            ResourceQueue.from_snapshot(
                1, ["a"], [], occurrence_counts={"a": 2}
            )

    def test_legacy_snapshot_restores_counts_of_one(self):
        q = ResourceQueue.from_snapshot(1, ["a"], ["b"])
        self.assertEqual(q.recurrence_mode, "ignore")
        self.assertEqual(q.export_occurrence_counts(), {"a": 1, "b": 1})


class RecurrenceCoordinatorTests(unittest.TestCase):
    def setUp(self):
        self.entities = {
            "light.garage": "off",
            "light.entrance": "off",
        }

    def manager(self, mode="count"):
        return ResourceQueueCoordinator(
            1, self.entities.get, self.entities, recurrence_mode=mode,
        )

    def test_counts_restore_and_reset_without_entity_control(self):
        m = self.manager()
        m.request("garage", "light.garage")
        m.request("entrance", "light.entrance")
        m.request("entrance", "light.entrance")
        self.assertEqual(m.snapshot().waiting, ("entrance",))
        self.assertEqual(m.export_state()["occurrence_counts"], {"garage": 1, "entrance": 2})
        restored = ResourceQueueCoordinator.from_state(
            1, self.entities.get, m.export_state(),
            monitored_entities=self.entities,
            recurrence_mode="count",
        )
        self.assertTrue(restored.paused)
        self.assertEqual(restored.queue.occurrences("entrance"), 2)
        restored.resume()
        restored.release("garage")
        self.assertEqual(restored.snapshot().active, ("entrance",))
        self.assertEqual(restored.queue.occurrences("entrance"), 2)
        restored.cancel("entrance")
        self.assertEqual(restored.queue.export_occurrence_counts(), {})

    def test_cannot_change_mode_while_active_or_pending(self):
        m = self.manager()
        m.request("garage", "light.garage")
        with self.assertRaisesRegex(QueueStateError, "Cannot change recurrence"):
            ResourceQueueCoordinator.from_state(
                1, self.entities.get, m.export_state(),
                monitored_entities=self.entities, recurrence_mode="ignore",
            )
        m.release("garage")
        restored = ResourceQueueCoordinator.from_state(
            1, self.entities.get, m.export_state(),
            monitored_entities=self.entities, recurrence_mode="ignore",
        )
        self.assertEqual(restored.recurrence_mode, "ignore")
