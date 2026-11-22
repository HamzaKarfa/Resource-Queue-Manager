"""Capacity policy contract tests; no Home Assistant installation required."""

from pathlib import Path
import sys
import types
import unittest

COMPONENTS_DIR = Path(__file__).resolve().parents[1] / "custom_components"
package = types.ModuleType("resource_queue_manager")
package.__path__ = [str(COMPONENTS_DIR / "resource_queue_manager")]
sys.modules.setdefault("resource_queue_manager", package)

from resource_queue_manager.capacity import (  # noqa: E402
    CAPACITY_PROVIDERS,
    DEFAULT_CAPACITY_MODE,
    get_capacity_policy,
    get_capacity_provider,
)
from resource_queue_manager.engine import ResourceQueue  # noqa: E402


class CapacityPolicyTests(unittest.TestCase):
    def test_default_classic_provider_is_registered_and_fresh(self):
        self.assertEqual(DEFAULT_CAPACITY_MODE, "classic")
        self.assertEqual(get_capacity_provider("classic").key, "classic")
        self.assertIsNot(get_capacity_policy(), get_capacity_policy())
        self.assertRaises(ValueError, get_capacity_policy, "unknown")

    def test_classic_policy_matches_v1_slot_behavior(self):
        classic = get_capacity_policy("classic")
        self.assertTrue(
            classic.can_allocate(active_units=(1, 1), candidate_units=1, capacity=3)
        )
        self.assertFalse(
            classic.can_allocate(active_units=(1, 1, 1), candidate_units=1, capacity=3)
        )
        classic.validate_restored(
            active_units=(1, 1), waiting_units=(1,), capacity=2
        )
        with self.assertRaisesRegex(ValueError, "exceed current limit"):
            classic.validate_restored(
                active_units=(1, 1, 1), waiting_units=(), capacity=2
            )
        with self.assertRaisesRegex(ValueError, "unallocated free slots"):
            classic.validate_restored(
                active_units=(1,), waiting_units=(1,), capacity=2
            )

    def test_classic_allocation_is_unchanged_for_all_strategies(self):
        for strategy in ("fifo", "lifo", "priority_fifo"):
            with self.subTest(strategy=strategy):
                q = ResourceQueue(1, strategy=strategy, capacity_mode="classic")
                for i, resource in enumerate(("a", "b", "c"), 1):
                    data = {"priority": i} if strategy == "priority_fifo" else None
                    q.request(resource, data)
                self.assertEqual(q.snapshot().active, ("a",))
                self.assertEqual(
                    q.snapshot().waiting,
                    ("b", "c") if strategy == "fifo" else ("c", "b"),
                )
                self.assertEqual(q.release("a").granted, ("b",) if strategy == "fifo" else ("c",))
                saved = q.snapshot()
                restored = ResourceQueue.from_snapshot(
                    max_active=1,
                    active=list(saved.active),
                    waiting=list(saved.waiting),
                    strategy=strategy,
                    request_data=q.export_request_data(),
                )
                self.assertEqual(restored.capacity_mode, "classic")
                self.assertEqual(restored.snapshot(), saved)

    def test_engine_delegates_and_does_not_skip_blocked_head(self):
        class NeverGrant:
            key = "never_grant"

            def resolve_request_units(self, *, engine_data, default_units, capacity):
                return 1

            def can_allocate(self, *, active_units, candidate_units, capacity):
                return False

            def validate_restored(self, *, active_units, waiting_units, capacity):
                return None

        class NeverGrantProvider:
            key = "never_grant"
            label = "Test-only policy"
            description = "Always reject grants"

            def create(self):
                return NeverGrant()

        CAPACITY_PROVIDERS["never_grant"] = NeverGrantProvider()
        try:
            queue = ResourceQueue(3, capacity_mode="never_grant")
            queue.request("a")
            queue.request("b")
            self.assertEqual(queue.snapshot().active, ())
            self.assertEqual(queue.snapshot().waiting, ("a", "b"))
        finally:
            del CAPACITY_PROVIDERS["never_grant"]


if __name__ == "__main__":
    unittest.main()
