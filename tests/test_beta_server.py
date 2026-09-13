"""Focused offline tests for the invite-only beta backend candidate."""
import http.client
from contextlib import closing
import json
import os
from pathlib import Path
import socket
import sqlite3
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from bibleprep import beta_server as subject


SECRET = "correct-horse-battery-staple-beta-secret"
SALT = "11" * 16


def invite_config(*, user_cap=None, global_cap=None):
    user_cap = user_cap or 5 * subject.MAX_RESERVATION_NANO
    global_cap = global_cap or 10 * subject.MAX_RESERVATION_NANO
    return {"schema_version": 1, "status": "active_hash_only_invites",
            "global_cap_nano_usd": global_cap,
            "session_ttl_seconds": subject.SESSION_TTL_SECONDS,
            "invites": [subject.make_invite_record("reader-one", SECRET, user_cap,
                                                     salt_hex=SALT)]}


class FakeLibrary:
    count = 42
    def select(self, messages):
        return ([{"reference": "Gen 1:1"}], ["fixture source note"])
    def context(self, sources, notes):
        return "fixture original-language source context"


class FakeModel:
    def __init__(self, *, gate=None, error=None, cost=0.01):
        self.gate, self.error, self.cost = gate, error, cost
        self.calls, self.blocked, self.closed = [], False, False
    def status(self):
        return {"ready": not self.blocked and not self.closed,
                "blocked": self.blocked, "closed": self.closed}
    def generate(self, messages, evidence_context=""):
        self.calls.append((messages, evidence_context))
        if self.gate:
            self.gate.wait(2)
        if self.error:
            raise self.error
        return {"answer": "A final answer only.", "answer_complete": True,
                "warnings": [], "usage": {"estimated_usd": self.cost}}
    def close(self):
        self.closed = True


class StreamingFakeModel(FakeModel):
    supports_progress = True

    def __init__(self, *, gate=None, error=None, cost=0.01):
        super().__init__(gate=gate, error=error, cost=cost)
        self.progress_ready = threading.Event()

    def generate(self, messages, evidence_context="", on_progress=None):
        self.calls.append((messages, evidence_context))
        on_progress("A partial", 1)
        self.progress_ready.set()
        if self.gate:
            self.gate.wait(2)
        on_progress("A partial answer", 2)
        if self.error:
            raise self.error
        return {"answer": "A partial answer only.", "answer_complete": True,
                "warnings": [], "usage": {"estimated_usd": self.cost}}


class ConcurrentFakeModel(FakeModel):
    def __init__(self, *, rendezvous, release):
        super().__init__()
        self.rendezvous = rendezvous
        self.release = release

    def generate(self, messages, evidence_context=""):
        self.calls.append((messages, evidence_context))
        if not self.release.is_set():
            self.rendezvous.wait(2)
        self.release.wait(2)
        return {"answer": "A concurrent synthetic answer.", "answer_complete": True,
                "warnings": [], "usage": {"estimated_usd": self.cost}}


def messages(text="What does this passage say?"):
    return {"messages": [{"role": "user", "content": text}]}


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "private/beta.sqlite3"
        self.config = invite_config()
        self.store = subject.BetaStore(self.path, self.config)

    def test_hash_only_invites_are_strict_and_database_is_private(self):
        record = self.config["invites"][0]
        self.assertNotIn(SECRET, json.dumps(self.config))
        self.assertEqual(record["secret_scrypt_hex"], subject.hash_invite_secret(SECRET, SALT))
        self.assertTrue(self.store.authenticate_invite("reader-one", SECRET))
        self.assertFalse(self.store.authenticate_invite("reader-one", "x" * 30))
        self.assertFalse(self.store.authenticate_invite("unknown", "x" * 30))
        self.assertEqual(self.path.stat().st_mode & 0o777, 0o600)
        self.assertNotIn(SECRET.encode(), self.path.read_bytes())
        with self.assertRaises(ValueError):
            subject.make_invite_record("x", "short", subject.MAX_RESERVATION_NANO)

    def test_sessions_store_only_hash_and_expire(self):
        with patch.object(subject.time, "time", return_value=1000):
            token, expires = self.store.create_session("reader-one")
        self.assertNotIn(token.encode(), self.path.read_bytes())
        with patch.object(subject.time, "time", return_value=1001):
            self.assertEqual(self.store.session_user(token), "reader-one")
        with patch.object(subject.time, "time", return_value=expires):
            self.assertIsNone(self.store.session_user(token))

    def test_reservations_survive_restart_and_unfinished_is_uncertain(self):
        self.store.reserve("reader-one", "request-a", now=100)
        self.store.mark_submitted("request-a")
        reopened = subject.BetaStore(self.path, self.config)
        usage = reopened.usage("reader-one")
        self.assertEqual(usage["user_accounted_nano_usd"], subject.MAX_RESERVATION_NANO)
        self.assertEqual(usage["uncertain_requests"], 1)
        with closing(sqlite3.connect(self.path)) as db:
            self.assertEqual(db.execute("SELECT status FROM usage").fetchone()[0], "uncertain")

    def test_unsubmitted_reservation_is_released_on_restart(self):
        self.store.reserve("reader-one", "queued-before-restart", now=100)
        reopened = subject.BetaStore(self.path, self.config)
        self.assertEqual(reopened.usage("reader-one")["user_accounted_nano_usd"], 0)
        with closing(sqlite3.connect(self.path)) as db:
            self.assertEqual(
                db.execute("SELECT status,actual_nano,quota_charged FROM usage").fetchone(),
                ("complete", 0, 0))

    def test_actual_cost_releases_reservation_but_uncertain_retains_it(self):
        self.store.reserve("reader-one", "complete", now=100)
        self.store.mark_submitted("complete")
        self.store.finalize("complete", actual_nano=1234)
        self.store.reserve("reader-one", "uncertain", now=111)
        self.store.mark_submitted("uncertain")
        self.store.finalize("uncertain", uncertain=True)
        usage = self.store.usage("reader-one")
        self.assertEqual(usage["user_accounted_nano_usd"],
                         1234 + subject.MAX_RESERVATION_NANO)

    def test_per_user_and_global_caps_fail_before_new_reservation(self):
        config = invite_config(user_cap=subject.MAX_RESERVATION_NANO,
                               global_cap=subject.MAX_RESERVATION_NANO)
        path = Path(self.temp.name) / "limited.sqlite3"
        store = subject.BetaStore(path, config)
        store.reserve("reader-one", "first", now=100)
        store.mark_submitted("first")
        store.finalize("first", uncertain=True)
        with self.assertRaisesRegex(subject.BetaError, "allowance_exhausted"):
            store.reserve("reader-one", "second", now=111)
        with closing(sqlite3.connect(path)) as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM usage").fetchone()[0], 1)

    def test_rate_limit_is_durable_and_config_change_is_rejected(self):
        self.store.reserve("reader-one", "first", now=100)
        self.store.finalize("first", actual_nano=0)
        with self.assertRaisesRegex(subject.BetaError, "rate_limited"):
            self.store.reserve("reader-one", "too-soon", now=109)
        self.store.reserve("reader-one", "later", now=110)
        changed = invite_config(global_cap=11 * subject.MAX_RESERVATION_NANO)
        with self.assertRaisesRegex(ValueError, "configuration changed"):
            subject.BetaStore(self.path, changed)

    def test_stored_invite_hash_tamper_is_rejected_on_restart(self):
        with closing(sqlite3.connect(self.path)) as db:
            db.execute("UPDATE invites SET secret_scrypt_hex=? WHERE invite_id=?",
                       ("0" * 64, "reader-one"))
            db.commit()
        with self.assertRaisesRegex(ValueError, "Stored invite hashes"):
            subject.BetaStore(self.path, self.config)


class ApplicationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = subject.BetaStore(Path(self.temp.name) / "beta.sqlite3", invite_config())
        self.model = FakeModel()
        self.factory_calls = 0
        def factory():
            self.factory_calls += 1
            return self.model
        self.app = subject.BetaApplication(store=self.store, model_factory=factory,
                                           library=FakeLibrary())
        self.app.access.accept_terms(
            subject.AccessIdentity("invite", "reader-one"),
            "2026-09-11.1", True, now=100)
        self.addCleanup(self.app.close)

    def wait(self, request_id, identity="reader-one"):
        for _ in range(100):
            result = self.app.result(identity, request_id)
            if result and result["status"] not in {"queued", "running"}:
                return result
            time.sleep(0.005)
        self.fail("synthetic job did not finish")

    def test_model_is_lazy_and_complete_answer_is_not_logged(self):
        self.assertEqual(self.factory_calls, 0)
        request = self.app.submit("reader-one", messages("PRIVATE CHAT SENTENCE"))
        result = self.wait(request)
        self.assertEqual(result["answer"], "A final answer only.")
        self.assertEqual(self.factory_calls, 1)
        self.assertEqual(self.store.usage("reader-one")["user_accounted_nano_usd"], 10_000_000)
        self.assertNotIn(b"PRIVATE CHAT SENTENCE", self.store.path.read_bytes())
        self.assertIsNone(self.app.result("another-user", request))

    def test_one_identity_cannot_hold_two_outstanding_reservations(self):
        gate = threading.Event()
        self.model.gate = gate
        first = self.app.submit("reader-one", messages())
        for _ in range(100):
            if self.model.calls:
                break
            time.sleep(0.005)
        with self.assertRaisesRegex(subject.BetaError, "request_pending"):
            self.app.submit("reader-one", messages("second"))
        with closing(sqlite3.connect(self.store.path)) as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM usage").fetchone()[0], 1)
        gate.set()
        self.wait(first)

    def test_existing_terminal_model_rejects_before_reservation(self):
        self.app.model = self.model
        for state in ("blocked", "closed"):
            with self.subTest(state=state):
                setattr(self.model, state, True)
                self.assertFalse(self.app.health()["ready"])
                before = self.store.usage("reader-one")
                with self.assertRaisesRegex(subject.BetaError, state):
                    self.app.submit("reader-one", messages(state))
                self.assertEqual(self.store.usage("reader-one"), before)
                with closing(sqlite3.connect(self.store.path)) as db:
                    self.assertEqual(db.execute("SELECT COUNT(*) FROM usage").fetchone()[0], 0)
                setattr(self.model, state, False)

    def test_revisioned_progress_is_owned_read_only_and_finalized_once(self):
        gate = threading.Event()
        self.model = StreamingFakeModel(gate=gate)
        request = self.app.submit("reader-one", messages())
        self.assertTrue(self.model.progress_ready.wait(1))
        running = self.app.result("reader-one", request)
        self.assertEqual(
            {key: running[key] for key in ("status", "revision", "answer", "complete")},
            {"status": "running", "revision": 1, "answer": "A partial",
             "complete": False})
        self.assertIsInstance(running["queue_wait_seconds"], (float, int))
        self.assertIsInstance(running["run_elapsed_seconds"], (float, int))
        self.assertIsNone(self.app.result("another-user", request))
        before = self.store.usage("reader-one")
        for _ in range(2):
            current = self.app.result("reader-one", request)
            self.assertEqual(
                {key: current[key] for key in ("status", "revision", "answer", "complete")},
                {key: running[key] for key in ("status", "revision", "answer", "complete")})
        self.assertEqual(self.store.usage("reader-one"), before)
        gate.set()
        result = self.wait(request)
        self.assertEqual(result["answer"], "A partial answer only.")
        self.assertEqual(result["revision"], 3)
        self.assertTrue(result["complete"])
        self.assertEqual(len(self.model.calls), 1)
        self.assertEqual(self.store.usage("reader-one")["user_accounted_nano_usd"],
                         10_000_000)

    def test_post_submission_failure_returns_only_last_safe_partial(self):
        self.model = StreamingFakeModel(error=RuntimeError("private provider detail"))
        request = self.app.submit("reader-one", messages())
        result = self.wait(request)
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["partial_answer"], "A partial answer")
        self.assertEqual(result["revision"], 2)
        self.assertFalse(result["complete"])
        self.assertNotIn("private provider", json.dumps(result))
        usage = self.store.usage("reader-one")
        self.assertEqual(usage["user_accounted_nano_usd"],
                         subject.MAX_RESERVATION_NANO)
        self.assertEqual(usage["uncertain_requests"], 1)

    def test_unexpected_failure_is_safe_and_keeps_full_reservation(self):
        self.model.error = RuntimeError("provider secret/path detail")
        request = self.app.submit("reader-one", messages())
        result = self.wait(request)
        self.assertEqual(result["error"]["code"], "generation_unavailable")
        self.assertNotIn("provider", json.dumps(result))
        usage = self.store.usage("reader-one")
        self.assertEqual(usage["user_accounted_nano_usd"], subject.MAX_RESERVATION_NANO)
        self.assertEqual(usage["uncertain_requests"], 1)

    def test_known_local_model_error_accounts_zero(self):
        self.model.error = subject.ChatModelError("not_configured")
        request = self.app.submit("reader-one", messages())
        result = self.wait(request)
        self.assertEqual(result["status"], "error")
        self.assertEqual(self.store.usage("reader-one")["user_accounted_nano_usd"], 0)

    def test_worker_start_failure_releases_reservation(self):
        with patch.object(threading.Thread, "start", side_effect=RuntimeError("start")):
            with self.assertRaisesRegex(subject.BetaError, "worker_unavailable"):
                subject.BetaApplication(store=self.store, model_factory=FakeModel,
                                        library=FakeLibrary())
        self.assertEqual(self.store.usage("reader-one")["user_accounted_nano_usd"], 0)
        self.assertEqual(self.factory_calls, 0)

    def test_completed_answers_have_short_bounded_memory_retention(self):
        now = time.monotonic()
        with self.app.lock:
            for index in range(25):
                self.app.jobs[f"done-{index}"] = {
                    "identity": subject.AccessIdentity("invite", "reader-one"),
                    "status": "complete", "answer": "temporary",
                    "completed_at": now,
                }
            self.app.jobs["expired"] = {
                "identity": subject.AccessIdentity("invite", "reader-one"),
                "status": "complete", "answer": "temporary",
                "completed_at": now - subject.RESULT_TTL_SECONDS,
            }
        self.assertIsNone(self.app.result("reader-one", "missing"))
        self.assertLessEqual(len(self.app.jobs), subject.MAX_RETAINED_RESULTS)
        self.assertNotIn("expired", self.app.jobs)

    def test_three_workers_overlap_with_distinct_models_and_fifo_queue(self):
        rendezvous = threading.Barrier(4)
        release = threading.Event()
        models = []
        factory_lock = threading.Lock()

        def factory():
            model = ConcurrentFakeModel(rendezvous=rendezvous, release=release)
            with factory_lock:
                models.append(model)
            return model

        pool = subject.BetaApplication(
            store=self.store, model_factory=factory, library=FakeLibrary(),
            worker_count=3, queue_limit=12)
        self.addCleanup(pool.close)
        identities = [subject.AccessIdentity("account", f"person-{index}")
                      for index in range(4)]
        for identity in identities:
            pool.access.accept_terms(identity, subject.TERMS_VERSION, True, now=100)
        requests = [pool.submit(identity, messages(str(index)))
                    for index, identity in enumerate(identities)]
        rendezvous.wait(2)
        states = [pool.result(identity, request_id)
                  for identity, request_id in zip(identities, requests)]
        self.assertEqual([state["status"] for state in states],
                         ["running", "running", "running", "queued"])
        self.assertEqual(states[3]["queue_position"], 1)
        self.assertEqual(len(models), 3)
        self.assertEqual(len({id(model) for model in models}), 3)
        release.set()
        for identity, request_id in zip(identities, requests):
            for _ in range(100):
                result = pool.result(identity, request_id)
                if result and result["status"] == "complete":
                    break
                threading.Event().wait(.005)
            else:
                self.fail("concurrent synthetic job did not finish")

    def test_queue_timeout_reaper_refunds_without_result_polling(self):
        entered = threading.Event()
        release = threading.Event()

        class HeldModel(FakeModel):
            def generate(model_self, payload, evidence_context=""):
                model_self.calls.append((payload, evidence_context))
                entered.set()
                release.wait(3)
                return super().generate(payload, evidence_context)

        pool = subject.BetaApplication(
            store=self.store, model_factory=HeldModel, library=FakeLibrary(),
            queue_timeout_seconds=1)
        self.addCleanup(pool.close)
        first = subject.AccessIdentity("account", "timeout-first")
        second = subject.AccessIdentity("account", "timeout-second")
        for identity in (first, second):
            pool.access.accept_terms(identity, subject.TERMS_VERSION, True, now=100)
        first_request = pool.submit(first, messages("first"))
        self.assertTrue(entered.wait(1))
        released = threading.Event()
        original_finalize = self.store.finalize

        def finalize(request_id, **options):
            result = original_finalize(request_id, **options)
            if options.get("release_question"):
                released.set()
            return result

        with patch.object(self.store, "finalize", side_effect=finalize):
            second_request = pool.submit(second, messages("second"))
            self.assertTrue(released.wait(2))
        timed_out = pool.result(second, second_request)
        self.assertEqual(timed_out["error"]["code"], "queue_timeout")
        self.assertEqual(timed_out["run_elapsed_seconds"], 0.0)
        self.assertEqual(self.store.usage(second)["user_accounted_nano_usd"], 0)
        release.set()
        for _ in range(100):
            result = pool.result(first, first_request)
            if result and result["status"] == "complete":
                break
            threading.Event().wait(.005)

    def test_shutdown_during_lazy_factory_closes_orphan_without_provider_call(self):
        factory_entered = threading.Event()
        factory_release = threading.Event()
        model = FakeModel()

        def factory():
            factory_entered.set()
            factory_release.wait(2)
            return model

        pool = subject.BetaApplication(
            store=self.store, model_factory=factory, library=FakeLibrary())
        identity = subject.AccessIdentity("account", "factory-shutdown")
        pool.access.accept_terms(identity, subject.TERMS_VERSION, True, now=100)
        pool.submit(identity, messages())
        self.assertTrue(factory_entered.wait(1))
        closer = threading.Thread(target=pool.close)
        closer.start()
        with pool.condition:
            while not pool.closed:
                pool.condition.wait(1)
        factory_release.set()
        closer.join(2)
        self.assertFalse(closer.is_alive())
        self.assertTrue(model.closed)
        self.assertEqual(model.calls, [])
        self.assertEqual(self.store.usage(identity)["user_accounted_nano_usd"], 0)

    def test_full_queue_rejects_before_third_identity_reservation(self):
        entered = threading.Event()
        release = threading.Event()

        class HeldModel(FakeModel):
            def generate(model_self, payload, evidence_context=""):
                model_self.calls.append((payload, evidence_context))
                entered.set()
                release.wait(2)
                return {"answer": "done", "answer_complete": True,
                        "warnings": [], "usage": {"estimated_usd": .01}}

        pool = subject.BetaApplication(
            store=self.store, model_factory=HeldModel, library=FakeLibrary(),
            queue_limit=1)
        self.addCleanup(pool.close)
        identities = [subject.AccessIdentity("account", f"queue-{index}")
                      for index in range(3)]
        for identity in identities:
            pool.access.accept_terms(identity, subject.TERMS_VERSION, True, now=100)
        first = pool.submit(identities[0], messages("first"))
        self.assertTrue(entered.wait(1))
        second = pool.submit(identities[1], messages("second"))
        self.assertEqual(pool.result(identities[1], second)["queue_position"], 1)
        with self.assertRaisesRegex(subject.BetaError, "queue_full"):
            pool.submit(identities[2], messages("third"))
        self.assertEqual(self.store.usage(identities[2])["user_accounted_nano_usd"], 0)
        release.set()
        for identity, request_id in zip(identities[:2], (first, second)):
            for _ in range(100):
                if pool.result(identity, request_id)["status"] == "complete":
                    break
                threading.Event().wait(.005)


def unused_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class HTTPTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = subject.BetaStore(Path(self.temp.name) / "beta.sqlite3", invite_config())
        self.factory_calls = 0
        def factory():
            self.factory_calls += 1
            return FakeModel()
        self.app = subject.BetaApplication(store=self.store, model_factory=factory,
                                           library=FakeLibrary())
        self.port = unused_port()
        self.origin = f"http://127.0.0.1:{self.port}"
        self.server = subject.BetaHTTPServer(
            ("127.0.0.1", self.port),
            subject.handler_for(self.app, origin=self.origin, secure_cookie=False))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.stop)

    def stop(self):
        self.server.shutdown()
        self.server.server_close()
        self.app.close()
        self.thread.join(1)

    def request(self, method, path, body=None, headers=None):
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=2)
        raw = json.dumps(body).encode() if body is not None else None
        final = dict(headers or {})
        if raw is not None:
            final.setdefault("Content-Type", "application/json")
            final.setdefault("Content-Length", str(len(raw)))
        connection.request(method, path, body=raw, headers=final)
        response = connection.getresponse()
        value = json.loads(response.read())
        response_headers = dict(response.getheaders())
        connection.close()
        return response.status, value, response_headers

    def login(self):
        status, value, headers = self.request("POST", "/api/login",
            {"invite_id": "reader-one", "invite_secret": SECRET},
            {"Origin": self.origin, "Host": f"127.0.0.1:{self.port}"})
        self.assertEqual((status, value), (200, {"status": "signed_in"}))
        return headers["Set-Cookie"].split(";", 1)[0]

    def accept_terms(self, cookie):
        status, value, _ = self.request("POST", "/api/accept-terms",
            {"terms_version": "2026-09-11.1", "adult": True},
            {"Origin": self.origin, "Host": f"127.0.0.1:{self.port}",
             "Cookie": cookie})
        self.assertEqual(status, 200)
        self.assertEqual(value["access"]["terms_version"], "2026-09-11.1")
        self.assertTrue(value["access"]["terms_accepted"])

    def test_unauthorized_and_wrong_origin_never_initialize_provider(self):
        status, _, _ = self.request("POST", "/api/chat", messages(),
                                     {"Origin": self.origin})
        self.assertEqual(status, 401)
        status, _, _ = self.request("POST", "/api/login",
            {"invite_id": "reader-one", "invite_secret": SECRET},
            {"Origin": "https://wrong.invalid"})
        self.assertEqual(status, 403)
        status, _, _ = self.request("POST", "/api/login",
            {"invite_id": "reader-one", "invite_secret": "x" * 30},
            {"Origin": self.origin})
        self.assertEqual(status, 401)
        self.assertEqual(self.factory_calls, 0)
        self.assertEqual(self.store.usage("reader-one")["global_accounted_nano_usd"], 0)

    def test_login_cookie_is_http_only_and_authenticated_generation_works(self):
        cookie = self.login()
        status, health, headers = self.request("GET", "/health")
        self.assertEqual(status, 200)
        self.assertEqual(health, {"status": "candidate", "ready": True,
                                 "busy": False, "provider_initialized": False})
        self.assertNotIn("Set-Cookie", headers)
        self.assertEqual(self.factory_calls, 0)
        status, value, _ = self.request("GET", "/api/status",
            headers={"Cookie": cookie})
        self.assertEqual((status, value["access"]["kind"],
                          value["access"]["terms_version"],
                          value["access"]["terms_accepted"]),
                         (200, "invite", "2026-09-11.1", False))
        status, value, _ = self.request("POST", "/api/chat", messages(),
            {"Origin": self.origin, "Cookie": cookie})
        self.assertEqual((status, value["error"]["code"]), (403, "terms_required"))
        self.assertEqual(self.factory_calls, 0)
        with closing(sqlite3.connect(self.store.path)) as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM usage").fetchone()[0], 0)
        self.accept_terms(cookie)
        status, value, _ = self.request("POST", "/api/chat", messages(),
            {"Origin": self.origin, "Cookie": cookie})
        self.assertEqual(status, 202)
        self.assertIn("request_id", value)
        for _ in range(100):
            if self.factory_calls:
                break
            time.sleep(0.005)
        self.assertEqual(self.factory_calls, 1)
        status, value, headers = self.request("POST", "/api/logout", {},
            {"Origin": self.origin, "Cookie": cookie})
        self.assertEqual((status, value), (200, {"status": "signed_out"}))
        self.assertIn("Max-Age=0", headers["Set-Cookie"])

    def test_blocked_existing_model_is_unready_and_rejected_without_reservation(self):
        cookie = self.login()
        self.accept_terms(cookie)
        model = FakeModel()
        model.blocked = True
        self.app.model = model

        status, health, _ = self.request("GET", "/health")
        self.assertEqual(status, 503)
        self.assertEqual(health, {"status": "unavailable", "ready": False,
                                 "busy": False, "provider_initialized": True})
        status, value, _ = self.request("POST", "/api/chat", messages(),
            {"Origin": self.origin, "Cookie": cookie})
        self.assertEqual((status, value["error"]["code"]), (503, "blocked"))
        self.assertEqual(self.factory_calls, 0)
        self.assertEqual(model.calls, [])
        with closing(sqlite3.connect(self.store.path)) as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM usage").fetchone()[0], 0)

    def test_queue_admission_errors_have_exact_retryable_http_statuses(self):
        cookie = self.login()
        self.accept_terms(cookie)
        for code, expected in (("request_pending", 409), ("queue_full", 503),
                               ("model_unavailable", 503)):
            with self.subTest(code=code), patch.object(
                    self.app, "submit", side_effect=subject.BetaError(code)):
                status, value, _ = self.request(
                    "POST", "/api/chat", messages(),
                    {"Origin": self.origin, "Cookie": cookie})
                self.assertEqual(status, expected)
                self.assertEqual(value["error"]["code"], code)
                self.assertNotEqual(value["error"]["message"],
                                    "The beta could not accept this request.")

    def test_request_bounds_duplicate_json_and_hosted_cookie_policy(self):
        cookie = self.login()
        status, _, _ = self.request("POST", "/api/chat", messages(),
            {"Origin": self.origin, "Cookie": cookie, "Content-Type": "text/plain"})
        self.assertEqual(status, 415)
        with self.assertRaises(ValueError):
            subject.strict_json(b'{"messages":[],"messages":[]}')
        with self.assertRaises(ValueError):
            subject.handler_for(self.app, origin="http://beta.example", secure_cookie=True)
        handler = subject.handler_for(self.app, origin="https://beta.example", secure_cookie=True)
        self.assertTrue(issubclass(handler, subject.BaseHTTPRequestHandler))

        self.stop()
        self.app = subject.BetaApplication(store=self.store, model_factory=FakeModel,
                                           library=FakeLibrary())
        self.port = unused_port()
        self.origin = "https://beta.example"
        self.server = subject.BetaHTTPServer(
            ("127.0.0.1", self.port),
            subject.handler_for(self.app, origin=self.origin, secure_cookie=True))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        status, _, headers = self.request("POST", "/api/login",
            {"invite_id": "reader-one", "invite_secret": SECRET},
            {"Origin": self.origin, "Host": "beta.example"})
        self.assertEqual(status, 200)
        self.assertIn("; Secure", headers["Set-Cookie"])


if __name__ == "__main__":
    unittest.main()
