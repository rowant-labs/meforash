"""Independent failure-path checks for the bounded beta model pool."""
from collections import deque
from contextlib import closing
from pathlib import Path
import sqlite3
import tempfile
import threading
import time
import unittest

from bibleprep import beta_server as subject
from tests.test_beta_server import FakeLibrary, FakeModel, invite_config, messages


class PoolFailureTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = subject.BetaStore(
            Path(self.temp.name) / "pool-failures.sqlite3", invite_config())

    def identity(self, pool, name):
        identity = subject.AccessIdentity("account", name)
        pool.access.accept_terms(identity, subject.TERMS_VERSION, True, now=100)
        return identity

    def wait_for(self, pool, identity, request_id, *, timeout=2):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            result = pool.result(identity, request_id)
            if result and result["status"] not in {"queued", "running"}:
                return result
            threading.Event().wait(.005)
        self.fail(f"synthetic request {request_id} did not reach a terminal state")

    def test_partially_blocked_pool_keeps_serving_with_healthy_worker(self):
        blocked_entered = threading.Event()
        healthy_entered = threading.Event()
        healthy_release = threading.Event()
        self.addCleanup(healthy_release.set)

        class BlockedModel(FakeModel):
            def generate(model_self, payload, evidence_context=""):
                model_self.calls.append((payload, evidence_context))
                model_self.blocked = True
                blocked_entered.set()
                raise subject.ChatModelError("blocked")

        class HealthyModel(FakeModel):
            def generate(model_self, payload, evidence_context=""):
                model_self.calls.append((payload, evidence_context))
                healthy_entered.set()
                healthy_release.wait(2)
                return {"answer": "Healthy worker answer.", "answer_complete": True,
                        "warnings": [], "usage": {"estimated_usd": .01}}

        available = deque((BlockedModel(), HealthyModel()))
        factory_lock = threading.Lock()

        def factory():
            with factory_lock:
                return available.popleft()

        pool = subject.BetaApplication(
            store=self.store, model_factory=factory, library=FakeLibrary(),
            worker_count=2)
        self.addCleanup(pool.close)
        first, second, third = [
            self.identity(pool, f"partial-{index}") for index in range(3)
        ]
        first_request = pool.submit(first, messages("first"))
        second_request = pool.submit(second, messages("second"))
        self.assertTrue(blocked_entered.wait(1))
        self.assertTrue(healthy_entered.wait(1))

        self.assertTrue(pool.health()["ready"])
        third_request = pool.submit(third, messages("third"))
        queued = pool.result(third, third_request)
        self.assertEqual((queued["status"], queued["queue_position"]), ("queued", 1))

        healthy_release.set()
        results = [self.wait_for(pool, identity, request_id) for identity, request_id in (
            (first, first_request), (second, second_request), (third, third_request))]
        self.assertEqual([result["status"] for result in results].count("complete"), 2)
        self.assertEqual([result["status"] for result in results].count("error"), 1)
        self.assertEqual(results[2]["answer"], "Healthy worker answer.")
        self.assertTrue(pool.health()["ready"])

    def test_all_blocked_workers_refund_queue_and_reject_before_reserving(self):
        both_entered = threading.Barrier(3)
        fail_together = threading.Event()
        self.addCleanup(fail_together.set)

        class BlockedTogetherModel(FakeModel):
            def generate(model_self, payload, evidence_context=""):
                model_self.calls.append((payload, evidence_context))
                both_entered.wait(2)
                fail_together.wait(2)
                model_self.blocked = True
                raise subject.ChatModelError("blocked")

        pool = subject.BetaApplication(
            store=self.store, model_factory=BlockedTogetherModel,
            library=FakeLibrary(), worker_count=2)
        self.addCleanup(pool.close)
        identities = [
            self.identity(pool, f"blocked-{index}") for index in range(4)
        ]
        first = pool.submit(identities[0], messages("first"))
        second = pool.submit(identities[1], messages("second"))
        both_entered.wait(2)
        queued = pool.submit(identities[2], messages("queued"))
        self.assertEqual(pool.result(identities[2], queued)["status"], "queued")

        fail_together.set()
        first_result = self.wait_for(pool, identities[0], first)
        second_result = self.wait_for(pool, identities[1], second)
        queued_result = self.wait_for(pool, identities[2], queued)
        self.assertEqual(first_result["status"], "error")
        self.assertEqual(second_result["status"], "error")
        self.assertEqual(queued_result["error"]["code"], "model_unavailable")
        self.assertEqual(queued_result["run_elapsed_seconds"], 0.0)
        self.assertEqual(self.store.usage(identities[2])["user_accounted_nano_usd"], 0)
        self.assertFalse(pool.health()["ready"])

        before = self.store.usage(identities[3])
        with self.assertRaisesRegex(subject.BetaError, "blocked|model_unavailable"):
            pool.submit(identities[3], messages("must not reserve"))
        self.assertEqual(self.store.usage(identities[3]), before)
        with closing(sqlite3.connect(self.store.path)) as db:
            self.assertEqual(db.execute(
                "SELECT COUNT(*) FROM usage WHERE principal_id=?",
                (identities[3].subject,)).fetchone()[0], 0)

    def test_unexpected_worker_exception_makes_single_slot_pool_unready(self):
        pool = subject.BetaApplication(
            store=self.store, model_factory=FakeModel, library=FakeLibrary())
        self.addCleanup(pool.close)

        def crash_worker(slot_index, request_id, identity, payload):
            raise RuntimeError("synthetic coordinator failure")

        pool._generate = crash_worker
        first = self.identity(pool, "crashed-worker")
        request_id = pool.submit(first, messages("crash"))
        result = self.wait_for(pool, first, request_id)
        self.assertEqual(result["error"]["code"], "generation_unavailable")
        self.assertEqual(pool.health(), {
            "status": "unavailable", "ready": False, "busy": False,
            "provider_initialized": False,
        })
        self.assertEqual(
            self.store.usage(first)["user_accounted_nano_usd"],
            subject.MAX_RESERVATION_NANO)

        second = self.identity(pool, "after-crash")
        before = self.store.usage(second)
        with self.assertRaisesRegex(subject.BetaError, "worker_unavailable"):
            pool.submit(second, messages("must not reserve"))
        self.assertEqual(self.store.usage(second), before)


if __name__ == "__main__":
    unittest.main()
