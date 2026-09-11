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
        self.calls, self.closed = [], False
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
            "2026-09-11", True, now=100)
        self.addCleanup(self.app.close)

    def wait(self, request_id):
        for _ in range(100):
            result = self.app.result("reader-one", request_id)
            if result and result["status"] != "running":
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

    def test_one_generation_flight_rejects_busy_without_second_reservation(self):
        gate = threading.Event()
        self.model.gate = gate
        first = self.app.submit("reader-one", messages())
        for _ in range(100):
            if self.model.calls:
                break
            time.sleep(0.005)
        with self.assertRaisesRegex(subject.BetaError, "busy"):
            self.app.submit("reader-one", messages("second"))
        with closing(sqlite3.connect(self.store.path)) as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM usage").fetchone()[0], 1)
        gate.set()
        self.wait(first)

    def test_revisioned_progress_is_owned_read_only_and_finalized_once(self):
        gate = threading.Event()
        self.model = StreamingFakeModel(gate=gate)
        request = self.app.submit("reader-one", messages())
        self.assertTrue(self.model.progress_ready.wait(1))
        running = self.app.result("reader-one", request)
        self.assertEqual(running, {
            "status": "running", "revision": 1, "answer": "A partial",
            "complete": False,
        })
        self.assertIsNone(self.app.result("another-user", request))
        before = self.store.usage("reader-one")
        self.assertEqual(self.app.result("reader-one", request), running)
        self.assertEqual(self.app.result("reader-one", request), running)
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
                self.app.submit("reader-one", messages())
        self.assertEqual(self.store.usage("reader-one")["user_accounted_nano_usd"], 0)
        self.assertEqual(self.factory_calls, 0)

    def test_completed_answers_have_short_bounded_memory_retention(self):
        now = time.monotonic()
        with self.app.lock:
            for index in range(25):
                self.app.jobs[f"done-{index}"] = {
                    "invite_id": "reader-one", "status": "complete",
                    "answer": "temporary", "created": now,
                }
            self.app.jobs["expired"] = {
                "invite_id": "reader-one", "status": "complete",
                "answer": "temporary", "created": now - subject.RESULT_TTL_SECONDS,
            }
        self.assertIsNone(self.app.result("reader-one", "missing"))
        self.assertLessEqual(len(self.app.jobs), subject.MAX_RETAINED_RESULTS)
        self.assertNotIn("expired", self.app.jobs)


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
            {"terms_version": "2026-09-11", "adult": True},
            {"Origin": self.origin, "Host": f"127.0.0.1:{self.port}",
             "Cookie": cookie})
        self.assertEqual(status, 200)
        self.assertEqual(value["access"]["terms_version"], "2026-09-11")
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
        status, _, headers = self.request("GET", "/health")
        self.assertEqual(status, 200)
        self.assertNotIn("Set-Cookie", headers)
        status, value, _ = self.request("GET", "/api/status",
            headers={"Cookie": cookie})
        self.assertEqual((status, value["access"]["kind"],
                          value["access"]["terms_version"],
                          value["access"]["terms_accepted"]),
                         (200, "invite", "2026-09-11", False))
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
