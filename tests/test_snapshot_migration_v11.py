"""v1.1 recovery/migration contracts (pure Python, no HA dependencies)."""

from pathlib import Path
import sys
import types
import unittest

COMPONENTS_DIR = Path(__file__).resolve().parents[1] / "custom_components"
package = types.ModuleType("resource_queue_manager")
package.__path__ = [str(COMPONENTS_DIR / "resource_queue_manager")]
sys.modules.setdefault("resource_queue_manager", package)

from resource_queue_manager.coordinator import (  # noqa: E402
    QueueStateError, ResourceQueueCoordinator,
)


class MigrationRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.states = {f"light.r{i}": "off" for i in range(1, 6)}
        self.ents = tuple(self.states)

    def restore(self, data, capacity=3, **opts):
        return ResourceQueueCoordinator.from_state(
            capacity, self.states.get, data,
            monitored_entities=self.ents, **opts,
        )

    def test_v04_snapshot_without_any_v11_keys_is_classic_ignore(self):
        legacy = {
            "active": ["a", "b", "c"],
            "waiting": ["d", "e"],
            "max_active": 3,
            "bindings": {
                "a": self.ents[0], "b": self.ents[1], "c": self.ents[2],
                "d": self.ents[3], "e": self.ents[4],
            },
        }
        restored = self.restore(legacy)
        self.assertTrue(restored.paused)
        self.assertEqual(restored.capacity_mode, "classic")
        self.assertEqual(restored.recurrence_mode, "ignore")
        self.assertEqual(restored.snapshot().granted, ())
        self.assertEqual(restored.snapshot().waiting, ("d", "e"))
        state = restored.export_state()
        self.assertEqual(state["active"], legacy["active"])
        self.assertEqual(state["waiting"], legacy["waiting"])
        self.assertEqual(state["bindings"], legacy["bindings"])
        self.assertEqual(state["occurrence_counts"], dict.fromkeys("abcde", 1))
        self.assertEqual(state["engine_request_data"], {})
        self.assertEqual(state["entity_weights"], {})
        with self.assertRaises(QueueStateError):
            restored.request("a", self.ents[0])
        self.assertEqual(restored.resume().granted, ())
        self.assertEqual(restored.release("a").granted, ("d",))

    def test_weighted_head_of_line_snapshot_with_free_units_is_valid(self):
        queue = ResourceQueueCoordinator(
            10, self.states.get, self.ents,
            capacity_mode="weighted", recurrence_mode="count",
            entity_weights={self.ents[0]: 7, self.ents[1]: 5, self.ents[2]: 2},
        )
        queue.request("active", self.ents[0])
        queue.request("large", self.ents[1])
        queue.request("small", self.ents[2])
        queue.request("large", self.ents[1])
        queue.request("large", self.ents[1])
        original = queue.export_state()
        self.assertEqual(original["occurrence_counts"]["large"], 3)
        self.assertEqual(queue.capacity_remaining, 3)

        restored = self.restore(
            original, capacity=10, capacity_mode="weighted",
            recurrence_mode="count",
            entity_weights={
                self.ents[0]: 7, self.ents[1]: 5, self.ents[2]: 2,
            },
        )
        self.assertTrue(restored.paused)
        self.assertEqual(restored.snapshot().granted, ())
        self.assertEqual(restored.snapshot().active, ("active",))
        self.assertEqual(restored.snapshot().waiting, ("large", "small"))
        self.assertEqual(restored.capacity_remaining, 3)
        self.assertEqual(restored.queue.occurrences("large"), 3)
        self.assertEqual(restored.resume().granted, ())
        self.assertEqual(restored.release("active").granted, ("large", "small"))
        self.assertEqual(restored.queue.occurrences("large"), 3)
        self.assertEqual(restored.capacity_used, 7)

    def test_capacity_increase_defers_promotions_until_explicit_resume(self):
        original = ResourceQueueCoordinator(
            7, self.states.get, self.ents,
            capacity_mode="weighted", recurrence_mode="count",
            entity_weights={self.ents[0]: 7, self.ents[1]: 2},
        )
        original.request("busy", self.ents[0])
        original.request("waiting", self.ents[1])
        data = original.export_state()

        restored = self.restore(
            data, capacity=10, capacity_mode="weighted",
            recurrence_mode="count",
            entity_weights={self.ents[0]: 7, self.ents[1]: 2},
        )
        self.assertTrue(restored.paused)
        self.assertEqual(restored.snapshot().granted, ())
        self.assertEqual(restored.snapshot().waiting, ("waiting",))
        result = restored.resume()
        self.assertEqual(result.granted, ("waiting",))
        self.assertEqual(result.waiting, ())
        self.assertEqual(restored.capacity_used, 9)

    def test_updated_default_does_not_modify_frozen_pending_weight(self):
        original = ResourceQueueCoordinator(
            10, self.states.get, self.ents,
            capacity_mode="weighted",
            entity_weights={self.ents[0]: 10, self.ents[1]: 6, self.ents[2]: 2},
        )
        original.request("busy", self.ents[0])
        original.request("pending", self.ents[1], engine_data={"weight": 5})
        data = original.export_state()

        restored = self.restore(
            data, capacity=10, capacity_mode="weighted",
            entity_weights={self.ents[0]: 10, self.ents[1]: 3, self.ents[2]: 2},
        )
        self.assertEqual(restored.queue.effective_weight("pending"), 5)
        self.assertEqual(restored.entity_weights[self.ents[1]], 3)
        restored.resume()
        self.assertEqual(restored.release("busy").granted, ("pending",))
        self.assertEqual(restored.capacity_used, 5)
        restored.release("pending")
        restored.request("next", self.ents[1])
        self.assertEqual(restored.queue.effective_weight("next"), 3)

    def test_shrink_fails_if_pending_weight_cannot_ever_fit(self):
        original = ResourceQueueCoordinator(
            10, self.states.get, self.ents,
            capacity_mode="weighted",
            entity_weights={self.ents[0]: 7, self.ents[1]: 8},
        )
        original.request("active", self.ents[0])
        original.request("large", self.ents[1])
        with self.assertRaisesRegex(QueueStateError, "New maximum"):
            self.restore(
                original.export_state(), capacity=7, capacity_mode="weighted",
                entity_weights={self.ents[0]: 7, self.ents[1]: 7},
            )

    def test_unsupported_saved_modes_are_invalid_even_for_empty_queue(self):
        empty = ResourceQueueCoordinator(3, self.states.get, self.ents).export_state()
        for key, value in (
            ("capacity_mode", "other"),
            ("capacity_mode", []),
            ("recurrence_mode", "other"),
            ("recurrence_mode", []),
        ):
            with self.subTest(key=key, value=value):
                changed = dict(empty)
                changed[key] = value
                with self.assertRaisesRegex(QueueStateError, "Unknown saved"):
                    self.restore(changed)

    def test_malformed_weights_and_counts_cannot_discard_reservations(self):
        q = ResourceQueueCoordinator(
            10, self.states.get, self.ents,
            capacity_mode="weighted", recurrence_mode="count",
            entity_weights={self.ents[0]: 10, self.ents[1]: 3},
        )
        q.request("active", self.ents[0])
        q.request("waiting", self.ents[1])
        q.request("waiting", self.ents[1])
        stable = q.export_state()
        for key, value in (
            ("engine_request_data", {}),
            ("engine_request_data", {"active": {"weight": 10}}),
            ("engine_request_data", {"active": {"weight": 10}, "waiting": {"weight": True}}),
            ("occurrence_counts", None),
            ("occurrence_counts", {}),
            ("occurrence_counts", {"active": 1, "waiting": 0}),
            ("occurrence_counts", {"active": 1, "waiting": 2, "unknown": 1}),
            ("bindings", {"active": self.ents[0]}),
        ):
            with self.subTest(key=key, value=value):
                changed = dict(stable)
                changed[key] = value
                with self.assertRaises(ValueError):
                    self.restore(
                        changed, capacity=10, capacity_mode="weighted",
                        recurrence_mode="count",
                        entity_weights={self.ents[0]: 10, self.ents[1]: 3},
                    )
                self.assertEqual(q.snapshot().active, ("active",))
                self.assertEqual(q.snapshot().waiting, ("waiting",))

    def test_mode_switch_blocked_with_bookings_but_allowed_when_empty(self):
        m = ResourceQueueCoordinator(
            10, self.states.get, self.ents,
            capacity_mode="weighted", recurrence_mode="count",
            entity_weights={self.ents[0]: 10},
        )
        m.request("active", self.ents[0])
        state = m.export_state()
        with self.assertRaisesRegex(QueueStateError, "Cannot change capacity mode"):
            self.restore(state, capacity=3, capacity_mode="classic")
        with self.assertRaisesRegex(QueueStateError, "Cannot change recurrence"):
            self.restore(
                state, capacity=10, capacity_mode="weighted",
                recurrence_mode="ignore",
                entity_weights={self.ents[0]: 10},
            )
        m.release("active")
        restored = self.restore(m.export_state(), capacity=3)
        self.assertEqual(restored.capacity_mode, "classic")
        self.assertEqual(restored.recurrence_mode, "ignore")
        self.assertTrue(restored.paused)


if __name__ == "__main__":
    unittest.main()
