"""Offline security, migration, quota, and HTTP tests for public access."""
import http.client
from contextlib import closing
import io
import json
from pathlib import Path
import socket
import sqlite3
import tempfile
import threading
import time
import unittest
from urllib.error import HTTPError

from bibleprep import account_access as access_subject
from bibleprep import beta_server


SECRET = "correct-horse-battery-staple-beta-secret"
ACCESS_SECRET = "stable-test-access-hmac-secret-32-bytes-minimum"
USER_UUID = "12345678-1234-5678-9234-567812345678"


def invite_config(*, global_cap=5_000_000_000):
    return {
        "schema_version": 1,
        "status": "active_hash_only_invites",
        "global_cap_nano_usd": global_cap,
        "session_ttl_seconds": beta_server.SESSION_TTL_SECONDS,
        "invites": [beta_server.make_invite_record(
            "reader-one", SECRET, min(global_cap, 1_000_000_000), salt_hex="22" * 16)],
    }


class FakeAuth:
    def __init__(self):
        self.started = []
        self.verified = []
        self.error = None

    def start(self, email):
        self.started.append(email)
        if self.error:
            raise self.error

    def verify(self, email, token):
        self.verified.append((email, token))
        if self.error:
            raise self.error
        return USER_UUID


class FakeLibrary:
    count = 1

    def select(self, messages):
        return [], []

    def context(self, sources, notes):
        return ""


class BrokenLibrary(FakeLibrary):
    def select(self, messages):
        raise RuntimeError("local source preparation failed")


class FakeModel:
    def generate(self, messages, evidence_context=""):
        return {"answer": "fixture", "answer_complete": True, "warnings": [],
                "usage": {"estimated_usd": 0.001}}

    def close(self):
        pass


class FakeResponse:
    def __init__(self, value):
        self.value = value

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self, size):
        return json.dumps(self.value).encode()


class AccessStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "state/beta.sqlite3"
        self.store = beta_server.BetaStore(self.path, invite_config())
        self.auth = FakeAuth()
        self.access = access_subject.AccountAccess(
            self.path, enabled=True, secret=ACCESS_SECRET, auth_client=self.auth)

    def test_public_and_email_rollout_flags_fail_closed(self):
        disabled = access_subject.AccountAccess.from_environ(self.path, {
            "MEFORASH_ACCOUNT_DAILY_LIMIT": "malformed-disabled-value",
            "SUPABASE_URL": "not-a-url",
        })
        self.assertFalse(disabled.enabled)
        with self.assertRaisesRegex(ValueError, "stable 32-byte"):
            access_subject.AccountAccess.from_environ(
                self.path, {"MEFORASH_PUBLIC_ACCESS": "1"})
        guest_only = access_subject.AccountAccess.from_environ(self.path, {
            "MEFORASH_PUBLIC_ACCESS": "1",
            "MEFORASH_ACCESS_HMAC_SECRET": ACCESS_SECRET,
            "SUPABASE_URL": "https://secret-project.supabase.co",
            "SUPABASE_PUBLISHABLE_KEY": "secret-publishable-key-value",
        })
        self.assertTrue(guest_only.enabled)
        self.assertIsNone(guest_only.auth_client)
        with self.assertRaisesRegex(ValueError, "requires Supabase"):
            access_subject.AccountAccess.from_environ(self.path, {
                "MEFORASH_PUBLIC_ACCESS": "1",
                "MEFORASH_EMAIL_LOGIN_ENABLED": "1",
                "MEFORASH_ACCESS_HMAC_SECRET": ACCESS_SECRET,
            })

    def test_guest_cookie_is_random_hash_only_durable_and_peer_limited(self):
        base = int(time.time())
        identity, token = self.access.guest(None, "192.0.2.10", now=base)
        self.assertEqual(identity.kind, "guest")
        self.assertNotIn(token.encode(), self.path.read_bytes())
        reopened = access_subject.AccountAccess(
            self.path, enabled=True, secret=ACCESS_SECRET, auth_client=self.auth)
        self.assertEqual(reopened.guest_identity(token, now=base + 1), identity)
        same, replacement = reopened.guest(token, "198.51.100.5", now=base + 1)
        self.assertEqual((same, replacement), (identity, None))
        for offset in (10, 20, 30, 40, 50):
            reopened.guest(None, "192.0.2.11", now=base + offset)
        with self.assertRaisesRegex(access_subject.AccessError, "rate_limited"):
            reopened.guest(None, "192.0.2.11", now=base + 60)
        raw = self.path.read_bytes()
        self.assertNotIn(b"192.0.2.10", raw)
        self.assertNotIn(b"192.0.2.11", raw)

    def test_hmac_secret_is_bound_to_durable_ledger(self):
        access_subject.AccountAccess(
            self.path, enabled=True, secret=ACCESS_SECRET, auth_client=self.auth)
        with self.assertRaisesRegex(ValueError, "HMAC secret changed"):
            access_subject.AccountAccess(
                self.path, enabled=True,
                secret="different-stable-access-secret-that-is-long-enough",
                auth_client=self.auth)

    def test_terms_acceptance_is_versioned_durable_idempotent_and_per_principal(self):
        base = int(time.time())
        guest, _ = self.access.guest(None, "192.0.2.80", now=base)
        account = access_subject.AccessIdentity("account", USER_UUID)
        invite = access_subject.AccessIdentity("invite", "reader-one")
        for version, adult in (("2026-09-10", True), ("2026-09-11.1", False),
                               ("2026-09-11.1", 1), (None, True)):
            with self.subTest(version=version, adult=adult), self.assertRaisesRegex(
                    access_subject.AccessError, "terms_required"):
                self.access.accept_terms(guest, version, adult, now=base + 1)
        self.assertFalse(self.access.terms_accepted(guest))
        self.access.accept_terms(guest, access_subject.TERMS_VERSION, True, now=base + 2)
        self.access.accept_terms(guest, access_subject.TERMS_VERSION, True, now=base + 1000)
        self.assertTrue(self.access.terms_accepted(guest))
        self.assertFalse(self.access.terms_accepted(account))
        self.assertFalse(self.access.terms_accepted(invite))
        with closing(sqlite3.connect(self.path)) as db:
            row = db.execute("SELECT terms_version,accepted_unix,adult_confirmed "
                             "FROM terms_acceptances").fetchone()
        self.assertEqual(row, (access_subject.TERMS_VERSION, base + 2, 1))
        reopened = access_subject.AccountAccess(
            self.path, enabled=True, secret=ACCESS_SECRET, auth_client=self.auth)
        self.assertTrue(reopened.terms_accepted(guest))
        raw = self.path.read_bytes()
        self.assertNotIn(b"192.0.2.80", raw)
        self.assertNotIn(b"date_of_birth", raw)

    def test_invitation_terms_work_with_public_access_disabled(self):
        disabled = access_subject.AccountAccess(self.path)
        invite = access_subject.AccessIdentity("invite", "reader-one")
        disabled.accept_terms(invite, access_subject.TERMS_VERSION, True, now=55)
        self.assertTrue(access_subject.AccountAccess(self.path).terms_accepted(invite))

    def test_otp_persists_only_hashes_and_local_session_hides_provider_material(self):
        challenge = self.access.start(" Reader@Example.COM ", "192.0.2.15", now=1000)
        identity, session = self.access.verify(
            "Reader@example.com", "876543", challenge, "192.0.2.15", now=1001)
        self.assertEqual(identity, access_subject.AccessIdentity("account", USER_UUID))
        self.assertEqual(self.access.account_identity(session, now=1002), identity)
        raw = self.path.read_bytes()
        for private in (b"Reader@example.com", b"reader@example.com", b"876543",
                        challenge.encode(), session.encode()):
            self.assertNotIn(private, raw)
        self.assertEqual(self.auth.started, ["reader@example.com"])
        self.assertEqual(self.auth.verified, [("reader@example.com", "876543")])

    def test_provider_start_failure_leaves_rate_event_but_no_orphan_challenge(self):
        self.auth.error = access_subject.AccessError("auth_unavailable")
        with self.assertRaisesRegex(access_subject.AccessError, "auth_unavailable"):
            self.access.start("reader@example.com", "192.0.2.18")
        with closing(sqlite3.connect(self.path)) as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM auth_challenges").fetchone()[0], 0)
            self.assertEqual(db.execute(
                "SELECT COUNT(*) FROM access_rate_events WHERE kind='otp_start_email'").fetchone()[0], 1)

    def test_invalid_code_can_be_retried_but_challenge_cannot_be_replayed_after_success(self):
        challenge = self.access.start("reader@example.com", "192.0.2.16", now=2000)
        self.auth.error = access_subject.AccessError("invalid_code")
        with self.assertRaisesRegex(access_subject.AccessError, "invalid_code"):
            self.access.verify("reader@example.com", "000000", challenge,
                               "192.0.2.16", now=2001)
        self.auth.error = None
        self.access.verify("reader@example.com", "123456", challenge,
                           "192.0.2.16", now=2002)
        with self.assertRaisesRegex(access_subject.AccessError, "invalid_code"):
            self.access.verify("reader@example.com", "123456", challenge,
                               "192.0.2.16", now=2003)

    def test_invalid_verification_attempts_are_durably_rate_limited(self):
        base = int(time.time())
        challenge = self.access.start("reader@example.com", "192.0.2.17", now=base)
        self.auth.error = access_subject.AccessError("invalid_code")
        for offset in range(10):
            with self.assertRaisesRegex(access_subject.AccessError, "invalid_code"):
                self.access.verify("reader@example.com", "000000", challenge,
                                   "192.0.2.17", now=base + 1 + offset)
        with self.assertRaisesRegex(access_subject.AccessError, "rate_limited"):
            self.access.verify("reader@example.com", "000000", challenge,
                               "192.0.2.17", now=base + 11)
        reopened = access_subject.AccountAccess(
            self.path, enabled=True, secret=ACCESS_SECRET, auth_client=self.auth)
        with self.assertRaisesRegex(access_subject.AccessError, "rate_limited"):
            reopened.verify("reader@example.com", "000000", challenge,
                            "192.0.2.17", now=base + 12)

    def test_guest_lifetime_and_account_utc_daily_quotas_survive_restart(self):
        guest, _ = self.access.guest(None, "192.0.2.20", now=1000)
        for index in range(3):
            self.store.reserve(guest, f"guest-{index}", now=1000 + index)
            self.store.finalize(f"guest-{index}", actual_nano=1)
        with self.assertRaisesRegex(beta_server.BetaError, "guest_limit_reached"):
            self.store.reserve(guest, "guest-four", now=2000)

        account = access_subject.AccessIdentity("account", USER_UUID)
        for index in range(2):
            self.store.reserve(account, f"account-{index}", now=86390 + index,
                               daily_limit=2)
            self.store.finalize(f"account-{index}", actual_nano=1)
        with self.assertRaisesRegex(beta_server.BetaError, "daily_limit_reached"):
            self.store.reserve(account, "account-three", now=86399, daily_limit=2)
        reopened = beta_server.BetaStore(self.path, invite_config())
        reopened.reserve(account, "next-day", now=86400, daily_limit=2)
        self.assertEqual(reopened.questions_remaining(account, 2, day=1), 1)

    def test_atomic_quota_and_release_or_uncertain_rules(self):
        account = access_subject.AccessIdentity("account", USER_UUID)
        outcomes = []
        barrier = threading.Barrier(5)

        def reserve(index):
            barrier.wait()
            try:
                self.store.reserve(account, f"race-{index}", now=100,
                                   daily_limit=3)
                outcomes.append("reserved")
            except beta_server.BetaError as exc:
                outcomes.append(exc.code)

        workers = [threading.Thread(target=reserve, args=(index,)) for index in range(5)]
        for worker in workers:
            worker.start()
        for worker in workers:
            worker.join()
        self.assertEqual(outcomes.count("reserved"), 3)
        self.assertEqual(outcomes.count("daily_limit_reached"), 2)

        with closing(sqlite3.connect(self.path)) as db:
            reserved = [row[0] for row in db.execute(
                "SELECT request_id FROM usage WHERE request_id LIKE 'race-%' ORDER BY request_id")]
        for index, request_id in enumerate(reserved):
            self.store.finalize(request_id, actual_nano=0,
                                release_question=index == 0)
        self.assertEqual(self.store.questions_remaining(account, 3, day=0), 1)
        self.store.reserve(account, "uncertain", now=101, daily_limit=3)
        self.store.finalize("uncertain", uncertain=True)
        self.assertEqual(self.store.questions_remaining(account, 3, day=0), 0)

    def test_invite_usage_and_public_usage_share_one_global_ledger(self):
        self.store.reserve("reader-one", "invite", now=100)
        self.store.finalize("invite", actual_nano=123)
        guest, _ = self.access.guest(None, "192.0.2.30", now=1000)
        self.store.reserve(guest, "guest", now=1000)
        self.store.finalize("guest", actual_nano=456)
        self.assertEqual(self.store.usage(guest)["global_accounted_nano_usd"], 579)

    def test_definitive_local_preparation_failure_releases_public_question(self):
        account = access_subject.AccessIdentity("account", USER_UUID)
        self.access.accept_terms(account, access_subject.TERMS_VERSION, True)
        app = beta_server.BetaApplication(
            store=self.store, access=self.access, model_factory=FakeModel,
            library=BrokenLibrary())
        self.addCleanup(app.close)
        request_id = app.submit(
            account, {"messages": [{"role": "user", "content": "fixture"}]})
        for _ in range(100):
            result = app.result(account, request_id)
            if result and result["status"] != "running":
                break
            time.sleep(0.005)
        self.assertEqual(result["error"]["code"], "generation_unavailable")
        self.assertEqual(self.store.questions_remaining(account, 20, day=access_subject.utc_day()),
                         20)
        self.assertEqual(self.store.usage(account)["user_accounted_nano_usd"], 0)

    def test_legacy_usage_schema_migrates_without_changing_config_identity(self):
        config_sha = self.store.config_sha256
        invite = access_subject.AccessIdentity("invite", "reader-one")
        self.access.accept_terms(invite, access_subject.TERMS_VERSION, True, now=50)
        with closing(sqlite3.connect(self.path)) as db:
            db.execute("ALTER TABLE usage RENAME TO usage_v2")
            db.execute("""CREATE TABLE usage(
                request_id TEXT PRIMARY KEY, invite_id TEXT NOT NULL,
                created_unix INTEGER NOT NULL, updated_unix INTEGER NOT NULL,
                reserved_nano INTEGER NOT NULL, actual_nano INTEGER, status TEXT NOT NULL,
                FOREIGN KEY(invite_id) REFERENCES invites(invite_id))""")
            db.execute("INSERT INTO usage VALUES(?,?,?,?,?,?,?)",
                       ("old", "reader-one", 1, 1, 99, 7, "complete"))
            db.execute("DROP TABLE usage_v2")
            db.commit()
        reopened = beta_server.BetaStore(self.path, invite_config())
        self.assertEqual(reopened.config_sha256, config_sha)
        self.assertEqual(reopened.usage("reader-one")["user_accounted_nano_usd"], 7)
        self.assertTrue(access_subject.AccountAccess(self.path).terms_accepted(invite))
        with closing(sqlite3.connect(self.path)) as db:
            indexes = {row[1] for row in db.execute("PRAGMA index_list(usage)")}
        self.assertIn("usage_identity_quota", indexes)
        self.assertIn("usage_identity_recent", indexes)


class SupabaseClientTests(unittest.TestCase):
    def test_code_must_be_exactly_six_ascii_digits_before_provider_call(self):
        calls = []

        def opener(request, timeout):
            calls.append(request)
            return FakeResponse({})

        client = access_subject.SupabaseAuthClient(
            "https://project.supabase.co", "publishable-key-long-enough", opener=opener)
        for token in (None, "", "12345", "1234567", "12a456", "123 56", "１２３４５６"):
            with self.subTest(token=token):
                with self.assertRaisesRegex(access_subject.AccessError, "invalid_code"):
                    client.verify("reader@example.com", token)
        self.assertEqual(calls, [])

    def test_exact_server_side_otp_verify_and_user_lookup(self):
        calls = []

        def opener(request, timeout):
            calls.append((request.full_url, request.get_method(), dict(request.header_items()),
                          None if request.data is None else json.loads(request.data)))
            if request.full_url.endswith("/verify"):
                return FakeResponse({"access_token": "provider-secret-token"})
            if request.full_url.endswith("/user"):
                return FakeResponse({"id": USER_UUID, "email": "reader@example.com",
                                     "email_confirmed_at": "2026-09-11T12:00:00Z"})
            return FakeResponse({})

        client = access_subject.SupabaseAuthClient(
            "https://project.supabase.co", "publishable-key-long-enough", opener=opener)
        client.start("reader@example.com")
        self.assertEqual(client.verify("reader@example.com", "123456"), USER_UUID)
        self.assertEqual([call[0].rsplit("/", 1)[-1] for call in calls], ["otp", "verify", "user"])
        self.assertEqual(calls[0][3], {"email": "reader@example.com", "create_user": True})
        self.assertEqual(calls[1][3]["type"], "email")
        self.assertEqual(calls[2][2]["Authorization"], "Bearer provider-secret-token")

    def test_user_must_be_confirmed_before_local_session_identity_is_returned(self):
        def opener(request, timeout):
            if request.full_url.endswith("/verify"):
                return FakeResponse({"access_token": "provider-secret-token"})
            return FakeResponse({"id": USER_UUID, "email": "reader@example.com"})

        client = access_subject.SupabaseAuthClient(
            "https://project.supabase.co", "publishable-key-long-enough", opener=opener)
        with self.assertRaisesRegex(access_subject.AccessError, "invalid_code"):
            client.verify("reader@example.com", "123456")

    def test_provider_rejection_maps_to_public_error(self):
        def opener(request, timeout):
            raise HTTPError(request.full_url, 400, "private detail", {}, io.BytesIO(b"detail"))

        client = access_subject.SupabaseAuthClient(
            "https://project.supabase.co", "publishable-key-long-enough", opener=opener)
        with self.assertRaisesRegex(access_subject.AccessError, "invalid_code"):
            client.verify("reader@example.com", "123456")


def unused_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class HTTPAccessTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "beta.sqlite3"
        self.store = beta_server.BetaStore(self.path, invite_config())
        self.auth = FakeAuth()
        self.access = access_subject.AccountAccess(
            self.path, enabled=True, secret=ACCESS_SECRET, auth_client=self.auth,
            daily_limit=20)
        self.app = beta_server.BetaApplication(
            store=self.store, access=self.access, model_factory=FakeModel,
            library=FakeLibrary())
        self.port = unused_port()
        self.origin = f"http://127.0.0.1:{self.port}"
        self.server = beta_server.BetaHTTPServer(
            ("127.0.0.1", self.port), beta_server.handler_for(
                self.app, origin=self.origin, secure_cookie=False))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.stop)

    def stop(self):
        self.server.shutdown()
        self.server.server_close()
        self.app.close()
        self.thread.join(1)

    def request(self, method, path, body=None, cookie=None, extra=None):
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=2)
        raw = json.dumps(body).encode() if body is not None else None
        headers = {"Host": f"127.0.0.1:{self.port}"}
        if method == "POST":
            headers["Origin"] = self.origin
        if raw is not None:
            headers.update({"Content-Type": "application/json",
                            "Content-Length": str(len(raw))})
        if cookie:
            headers["Cookie"] = cookie
        headers.update(extra or {})
        connection.request(method, path, body=raw, headers=headers)
        response = connection.getresponse()
        value = json.loads(response.read())
        result = response.status, value, response.getheaders()
        connection.close()
        return result

    def accept_terms(self, cookie, body=None):
        return self.request("POST", "/api/accept-terms", body or {
            "terms_version": access_subject.TERMS_VERSION, "adult": True}, cookie)

    @staticmethod
    def cookies(headers):
        return [value for name, value in headers if name.lower() == "set-cookie"]

    def test_contract_guest_quota_and_no_identity_disclosure(self):
        status, value, _ = self.request("GET", "/api/access")
        self.assertEqual((status, value), (200, {
            "public_access": True, "email_login_available": True}))
        status, value, headers = self.request("POST", "/api/guest", {})
        self.assertEqual(status, 200)
        self.assertEqual(value["access"], {"kind": "guest", "questions_remaining": 3,
            "daily_limit": 20, "reset_at": None,
            "terms_version": access_subject.TERMS_VERSION, "terms_accepted": False})
        guest_cookie = self.cookies(headers)[0].split(";", 1)[0]
        self.assertIn("HttpOnly", self.cookies(headers)[0])
        status, value, _ = self.request(
            "POST", "/api/chat", {"messages": [{"role": "user", "content": "fixture"}]},
            guest_cookie)
        self.assertEqual((status, value["error"]["code"]), (403, "terms_required"))
        with closing(sqlite3.connect(self.path)) as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM usage").fetchone()[0], 0)
        status, value, _ = self.accept_terms(guest_cookie)
        self.assertEqual(status, 200)
        self.assertTrue(value["access"]["terms_accepted"])
        with closing(sqlite3.connect(self.path)) as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM usage").fetchone()[0], 0)
        for remaining in (2, 1, 0):
            status, value, _ = self.request(
                "POST", "/api/chat", {"messages": [{"role": "user", "content": "fixture"}]},
                guest_cookie)
            self.assertEqual(status, 202)
            request_id = value["request_id"]
            for _ in range(100):
                status, result, _ = self.request("GET", f"/api/chat/{request_id}",
                                                  cookie=guest_cookie)
                if result.get("status") != "running":
                    break
                time.sleep(0.005)
            status, value, _ = self.request("GET", "/api/status", cookie=guest_cookie)
            self.assertEqual(value["access"]["questions_remaining"], remaining)
        status, value, _ = self.request(
            "POST", "/api/chat", {"messages": [{"role": "user", "content": "fourth"}]},
            guest_cookie)
        self.assertEqual((status, value["error"]["code"]), (403, "guest_limit_reached"))
        self.assertNotIn(USER_UUID, json.dumps(value))

    def test_email_session_and_logout_leave_guest_cookie_usable(self):
        _, _, headers = self.request("POST", "/api/guest", {})
        guest_cookie = self.cookies(headers)[0].split(";", 1)[0]
        status, value, headers = self.request(
            "POST", "/api/auth/start", {"email": "reader@example.com"}, guest_cookie)
        self.assertEqual((status, value), (200, {"status": "code_sent"}))
        challenge_cookie = self.cookies(headers)[0].split(";", 1)[0]
        status, value, headers = self.request(
            "POST", "/api/auth/verify",
            {"email": "reader@example.com", "token": "123456"},
            f"{guest_cookie}; {challenge_cookie}")
        self.assertEqual(status, 200)
        self.assertEqual(value["access"]["kind"], "account")
        self.assertFalse(value["access"]["terms_accepted"])
        self.assertNotIn(USER_UUID, json.dumps(value))
        self.assertNotIn("reader@example.com", json.dumps(value))
        account_cookie = next(item for item in self.cookies(headers)
                              if item.startswith(access_subject.ACCOUNT_COOKIE)).split(";", 1)[0]
        status, value, _ = self.request(
            "POST", "/api/chat", {"messages": [{"role": "user", "content": "fixture"}]},
            f"{guest_cookie}; {account_cookie}")
        self.assertEqual((status, value["error"]["code"]), (403, "terms_required"))
        status, value, _ = self.accept_terms(f"{guest_cookie}; {account_cookie}")
        self.assertEqual(status, 200)
        self.assertTrue(value["access"]["terms_accepted"])
        status, value, headers = self.request(
            "POST", "/api/logout", {}, f"{guest_cookie}; {account_cookie}")
        self.assertEqual((status, value), (200, {"status": "signed_out"}))
        cleared = self.cookies(headers)
        self.assertTrue(any(item.startswith(access_subject.ACCOUNT_COOKIE) and "Max-Age=0" in item
                            for item in cleared))
        self.assertFalse(any(item.startswith(access_subject.GUEST_COOKIE) for item in cleared))
        status, value, _ = self.request("GET", "/api/status", cookie=guest_cookie)
        self.assertEqual((status, value["access"]["kind"],
                          value["access"]["terms_accepted"]), (200, "guest", False))

    def test_email_start_remains_available_without_guest_or_terms_identity(self):
        status, value, headers = self.request(
            "POST", "/api/auth/start", {"email": "standalone@example.com"})
        self.assertEqual((status, value), (200, {"status": "code_sent"}))
        self.assertTrue(any(item.startswith(access_subject.CHALLENGE_COOKIE)
                            for item in self.cookies(headers)))
        self.assertEqual(self.auth.started, ["standalone@example.com"])

    def test_accept_terms_requires_identity_origin_and_exact_adult_contract(self):
        status, value, _ = self.accept_terms(None)
        self.assertEqual((status, value["error"]["code"]), (401, "unauthorized"))
        _, _, headers = self.request("POST", "/api/guest", {})
        guest_cookie = self.cookies(headers)[0].split(";", 1)[0]
        bad = [
            {},
            {"terms_version": access_subject.TERMS_VERSION, "adult": False},
            {"terms_version": access_subject.TERMS_VERSION, "adult": 1},
            {"terms_version": "old", "adult": True},
            {"terms_version": access_subject.TERMS_VERSION, "adult": True, "extra": 1},
        ]
        for body in bad:
            with self.subTest(body=body):
                status, value, _ = self.request(
                    "POST", "/api/accept-terms", body, guest_cookie)
                self.assertEqual((status, value["error"]["code"]),
                                 (403, "terms_required"))
        status, value, _ = self.request(
            "POST", "/api/accept-terms",
            {"terms_version": access_subject.TERMS_VERSION, "adult": True},
            guest_cookie, extra={"Origin": "https://wrong.invalid"})
        self.assertEqual((status, value["error"]["code"]), (403, "origin_rejected"))
        status, value, _ = self.request("GET", "/api/status", cookie=guest_cookie)
        self.assertFalse(value["access"]["terms_accepted"])
        status, value, _ = self.accept_terms(guest_cookie)
        self.assertEqual(status, 200)
        self.assertEqual(value["access"]["terms_version"], access_subject.TERMS_VERSION)
        self.assertTrue(value["access"]["terms_accepted"])

    def test_untrusted_x_real_ip_is_ignored_by_default(self):
        _, _, first = self.request("POST", "/api/guest", {}, extra={"X-Real-IP": "192.0.2.1"})
        first_cookie = self.cookies(first)[0]
        for index in range(4):
            time.sleep(0.01)
            self.request("POST", "/api/guest", {}, extra={"X-Real-IP": f"192.0.2.{index + 2}"})
        status, value, _ = self.request(
            "POST", "/api/guest", {}, extra={"X-Real-IP": "198.51.100.50"})
        self.assertEqual((status, value["error"]["code"]), (429, "rate_limited"))
        self.assertIn(access_subject.GUEST_COOKIE, first_cookie)

    def test_trusted_real_ip_mode_fails_closed_on_missing_or_malformed_header(self):
        port = unused_port()
        origin = f"http://127.0.0.1:{port}"
        server = beta_server.BetaHTTPServer(
            ("127.0.0.1", port), beta_server.handler_for(
                self.app, origin=origin, secure_cookie=False, trust_real_ip=True))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()

        def request(real_ip=None):
            connection = http.client.HTTPConnection("127.0.0.1", port, timeout=2)
            raw = b"{}"
            headers = {"Host": f"127.0.0.1:{port}", "Origin": origin,
                       "Content-Type": "application/json", "Content-Length": "2"}
            if real_ip is not None:
                headers["X-Real-IP"] = real_ip
            connection.request("POST", "/api/guest", body=raw, headers=headers)
            response = connection.getresponse()
            value = json.loads(response.read())
            connection.close()
            return response.status, value

        try:
            self.assertEqual(request()[0], 403)
            self.assertEqual(request("192.0.2.1, 198.51.100.1")[0], 403)
            self.assertEqual(request("not-an-ip")[0], 403)
            status, value = request("192.0.2.90")
            self.assertEqual((status, value["access"]["kind"]), (200, "guest"))
        finally:
            server.shutdown()
            server.server_close()
            thread.join(1)


if __name__ == "__main__":
    unittest.main()
