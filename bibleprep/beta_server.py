"""Invite-only Candidate Beta backend; loopback-only unless explicitly hosted.

The backend reuses the retained B chat model and passage library.  It stores no
conversation text.  SQLite retains only hashed authentication material,
sessions, request timing/status, and conservative cost accounting.
"""
from __future__ import annotations

import argparse
from contextlib import closing
from decimal import Decimal, ROUND_CEILING
import hashlib
from http.cookies import SimpleCookie, CookieError
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import math
import os
from pathlib import Path
import secrets
import sqlite3
import threading
import time
from urllib.parse import urlsplit

from bibleprep.account_access import (
    ACCOUNT_COOKIE,
    ACCOUNT_SESSION_SECONDS,
    CHALLENGE_COOKIE,
    CHALLENGE_SECONDS,
    GUEST_COOKIE,
    GUEST_COOKIE_SECONDS,
    AccessError,
    AccessIdentity,
    AccountAccess,
    utc_day,
    validated_peer,
)
from bibleprep.chat_model import ChatModel, ChatModelError, build_payload
from bibleprep.chat_sources import PassageLibrary
from bibleprep.chat_server import strict_json


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PORT = 8876
MAX_REQUEST_BYTES = 192_000
MAX_RESERVATION_NANO = 24_000 * 1_870 + 8_192 * 4_680
SESSION_COOKIE = "bible_beta_session"
SESSION_TTL_SECONDS = 12 * 3600
RATE_WINDOW_SECONDS = 3600
RATE_REQUESTS_PER_WINDOW = 12
MIN_REQUEST_INTERVAL_SECONDS = 10
RESULT_TTL_SECONDS = 15 * 60
MAX_RETAINED_RESULTS = 20
SCRYPT_N = 2**14
SCRYPT_R = 8
SCRYPT_P = 1
GLOBAL_COST_CEILING_NANO = 5_000_000_000


class BetaError(RuntimeError):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


def _sha(value):
    return hashlib.sha256(value).hexdigest()


def _canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False,
                      separators=(",", ":"), allow_nan=False).encode("utf-8")


def hash_invite_secret(secret, salt_hex):
    if not isinstance(secret, str) or len(secret) < 24:
        raise ValueError("Invite secrets must contain at least 24 characters.")
    try:
        salt = bytes.fromhex(salt_hex)
    except (TypeError, ValueError):
        raise ValueError("Invite salt must be lowercase hexadecimal.") from None
    if len(salt) != 16 or salt.hex() != salt_hex:
        raise ValueError("Invite salt must be exactly 16 bytes of lowercase hexadecimal.")
    return hashlib.scrypt(secret.encode("utf-8"), salt=salt, n=SCRYPT_N,
                          r=SCRYPT_R, p=SCRYPT_P, dklen=32).hex()


def make_invite_record(invite_id, secret, user_cap_nano_usd, *, salt_hex=None):
    """Create a hash-only invite record for an operator-managed config file."""
    if not isinstance(invite_id, str) or not invite_id.isascii() or not 3 <= len(invite_id) <= 64:
        raise ValueError("Invite IDs must be 3–64 ASCII characters.")
    if type(user_cap_nano_usd) is not int or user_cap_nano_usd < MAX_RESERVATION_NANO:
        raise ValueError("Invite cap must cover at least one maximum reservation.")
    salt_hex = salt_hex or secrets.token_bytes(16).hex()
    return {"invite_id": invite_id, "secret_salt_hex": salt_hex,
            "secret_scrypt_hex": hash_invite_secret(secret, salt_hex),
            "user_cap_nano_usd": user_cap_nano_usd, "enabled": True}


def validate_invite_config(config):
    required = {"schema_version", "status", "global_cap_nano_usd",
                "session_ttl_seconds", "invites"}
    if (not isinstance(config, dict) or set(config) != required
            or config["schema_version"] != 1 or config["status"] != "active_hash_only_invites"
            or type(config["global_cap_nano_usd"]) is not int
            or config["global_cap_nano_usd"] < MAX_RESERVATION_NANO
            or config["session_ttl_seconds"] != SESSION_TTL_SECONDS
            or not isinstance(config["invites"], list) or not config["invites"]):
        raise ValueError("Invite configuration differs from the beta candidate contract.")
    ids = set()
    for invite in config["invites"]:
        if set(invite) != {"invite_id", "secret_salt_hex", "secret_scrypt_hex",
                           "user_cap_nano_usd", "enabled"}:
            raise ValueError("Invite record fields differ.")
        invite_id = invite["invite_id"]
        if (not isinstance(invite_id, str) or not invite_id.isascii()
                or not 3 <= len(invite_id) <= 64 or invite_id in ids
                or type(invite["user_cap_nano_usd"]) is not int
                or invite["user_cap_nano_usd"] < MAX_RESERVATION_NANO
                or invite["user_cap_nano_usd"] > config["global_cap_nano_usd"]
                or invite["enabled"] is not True):
            raise ValueError("Invite ID, cap, enabled state, or uniqueness is invalid.")
        try:
            salt = bytes.fromhex(invite["secret_salt_hex"])
            digest = bytes.fromhex(invite["secret_scrypt_hex"])
        except (TypeError, ValueError):
            raise ValueError("Invite hashes must be hexadecimal.") from None
        if (len(salt) != 16 or len(digest) != 32
                or salt.hex() != invite["secret_salt_hex"]
                or digest.hex() != invite["secret_scrypt_hex"]):
            raise ValueError("Invite hash lengths or encoding are invalid.")
        ids.add(invite_id)
    return config


class BetaStore:
    """Small durable authentication, rate, and reservation ledger."""
    def __init__(self, path, invite_config):
        self.path = Path(path)
        validate_invite_config(invite_config)
        if self.path.exists() and (self.path.is_symlink() or not self.path.is_file()):
            raise ValueError("Beta database must be a regular non-symlink file.")
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(self.path.parent, 0o700)
        if not self.path.exists():
            fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            os.close(fd)
        os.chmod(self.path, 0o600)
        self.config = invite_config
        self.config_sha256 = _sha(_canonical(invite_config))
        self._initialize()

    def _connect(self):
        db = sqlite3.connect(self.path, timeout=5, isolation_level=None)
        db.execute("PRAGMA foreign_keys=ON")
        db.execute("PRAGMA journal_mode=DELETE")
        db.execute("PRAGMA synchronous=FULL")
        return db

    def _initialize(self):
        with closing(self._connect()) as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS metadata(key TEXT PRIMARY KEY, value TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS invites(
                    invite_id TEXT PRIMARY KEY, secret_salt_hex TEXT NOT NULL,
                    secret_scrypt_hex TEXT NOT NULL, user_cap_nano INTEGER NOT NULL,
                    enabled INTEGER NOT NULL CHECK(enabled IN (0,1)));
                CREATE TABLE IF NOT EXISTS sessions(
                    token_sha256 TEXT PRIMARY KEY, invite_id TEXT NOT NULL,
                    expires_unix INTEGER NOT NULL, FOREIGN KEY(invite_id) REFERENCES invites(invite_id));
            """)
            db.execute("BEGIN IMMEDIATE")
            columns = [row[1] for row in db.execute("PRAGMA table_info(usage)").fetchall()]
            if columns and "principal_kind" not in columns:
                db.execute("ALTER TABLE usage RENAME TO usage_legacy")
                db.execute("""CREATE TABLE usage(
                        request_id TEXT PRIMARY KEY, invite_id TEXT,
                        principal_kind TEXT NOT NULL,
                        principal_id TEXT NOT NULL,
                        quota_day INTEGER, quota_charged INTEGER NOT NULL DEFAULT 0,
                        created_unix INTEGER NOT NULL, updated_unix INTEGER NOT NULL,
                        reserved_nano INTEGER NOT NULL, actual_nano INTEGER,
                        status TEXT NOT NULL,
                        FOREIGN KEY(invite_id) REFERENCES invites(invite_id))""")
                db.execute("""INSERT INTO usage(
                        request_id,invite_id,principal_kind,principal_id,
                        quota_day,quota_charged,created_unix,updated_unix,
                        reserved_nano,actual_nano,status)
                    SELECT request_id,invite_id,'invite',invite_id,NULL,0,
                        created_unix,updated_unix,reserved_nano,actual_nano,status
                    FROM usage_legacy""")
                db.execute("DROP TABLE usage_legacy")
            elif not columns:
                db.execute("""
                    CREATE TABLE usage(
                        request_id TEXT PRIMARY KEY, invite_id TEXT,
                        principal_kind TEXT NOT NULL,
                        principal_id TEXT NOT NULL,
                        quota_day INTEGER, quota_charged INTEGER NOT NULL DEFAULT 0,
                        created_unix INTEGER NOT NULL, updated_unix INTEGER NOT NULL,
                        reserved_nano INTEGER NOT NULL, actual_nano INTEGER,
                        status TEXT NOT NULL,
                        FOREIGN KEY(invite_id) REFERENCES invites(invite_id))
                """)
            db.execute("CREATE INDEX IF NOT EXISTS usage_identity_quota ON usage("
                       "principal_kind,principal_id,quota_charged,quota_day)")
            db.execute("CREATE INDEX IF NOT EXISTS usage_identity_recent ON usage("
                       "principal_kind,principal_id,created_unix DESC)")
            current = db.execute("SELECT value FROM metadata WHERE key='config_sha256'").fetchone()
            if current is None:
                db.execute("INSERT INTO metadata(key,value) VALUES('config_sha256',?)",
                           (self.config_sha256,))
                db.execute("INSERT INTO metadata(key,value) VALUES('global_cap_nano',?)",
                           (str(self.config["global_cap_nano_usd"]),))
                for invite in self.config["invites"]:
                    db.execute("INSERT INTO invites VALUES(?,?,?,?,?)", (
                        invite["invite_id"], invite["secret_salt_hex"],
                        invite["secret_scrypt_hex"], invite["user_cap_nano_usd"], 1))
            elif (current[0] != self.config_sha256
                  or db.execute("SELECT value FROM metadata WHERE key='global_cap_nano'").fetchone()
                  != (str(self.config["global_cap_nano_usd"]),)):
                db.execute("ROLLBACK")
                raise ValueError("Invite configuration changed for an existing beta ledger.")
            expected_invites = sorted((item["invite_id"], item["secret_salt_hex"],
                item["secret_scrypt_hex"], item["user_cap_nano_usd"], 1)
                for item in self.config["invites"])
            stored_invites = db.execute("SELECT invite_id,secret_salt_hex,secret_scrypt_hex,"
                "user_cap_nano,enabled FROM invites ORDER BY invite_id").fetchall()
            if stored_invites != expected_invites:
                db.execute("ROLLBACK")
                raise ValueError("Stored invite hashes or caps differ from the configured ledger identity.")
            now = int(time.time())
            db.execute("DELETE FROM sessions WHERE expires_unix<=?", (now,))
            # A restart cannot prove whether an unfinished request reached the provider.
            db.execute("UPDATE usage SET status='uncertain',updated_unix=? "
                       "WHERE status IN ('reserved','submitted','running')", (now,))
            db.execute("COMMIT")

    def authenticate_invite(self, invite_id, secret):
        if not isinstance(invite_id, str) or not isinstance(secret, str):
            return False
        with closing(self._connect()) as db:
            row = db.execute("SELECT secret_salt_hex,secret_scrypt_hex,enabled "
                             "FROM invites WHERE invite_id=?", (invite_id,)).fetchone()
        if row is None or row[2] != 1:
            # Equalize the expensive path without revealing invite existence.
            hash_invite_secret(secret if len(secret) >= 24 else secret.ljust(24, "x"), "00" * 16)
            return False
        try:
            actual = hash_invite_secret(secret, row[0])
        except ValueError:
            actual = "0" * 64
        return secrets.compare_digest(actual, row[1])

    def create_session(self, invite_id):
        token = secrets.token_urlsafe(32)
        now = int(time.time())
        expires = now + self.config["session_ttl_seconds"]
        with closing(self._connect()) as db:
            db.execute("INSERT INTO sessions VALUES(?,?,?)", (_sha(token.encode()), invite_id, expires))
        return token, expires

    def session_user(self, token):
        if not isinstance(token, str) or len(token) < 32:
            return None
        now = int(time.time())
        digest = _sha(token.encode())
        with closing(self._connect()) as db:
            db.execute("DELETE FROM sessions WHERE expires_unix<=?", (now,))
            row = db.execute("SELECT invite_id FROM sessions WHERE token_sha256=? "
                             "AND expires_unix>?", (digest, now)).fetchone()
        return row[0] if row else None

    def delete_session(self, token):
        if isinstance(token, str):
            with closing(self._connect()) as db:
                db.execute("DELETE FROM sessions WHERE token_sha256=?", (_sha(token.encode()),))

    @staticmethod
    def _accounted_sql():
        return "COALESCE(SUM(CASE WHEN actual_nano IS NULL THEN reserved_nano ELSE actual_nano END),0)"

    @staticmethod
    def _identity(value):
        if isinstance(value, str):
            return AccessIdentity("invite", value)
        if isinstance(value, AccessIdentity):
            return value
        raise BetaError("unauthorized")

    def reserve(self, identity, request_id, now=None, *, daily_limit=20, guest_limit=3):
        now = int(time.time() if now is None else now)
        identity = self._identity(identity)
        with closing(self._connect()) as db:
            db.execute("BEGIN IMMEDIATE")
            invite_id = identity.subject if identity.kind == "invite" else None
            if identity.kind == "invite":
                invite = db.execute("SELECT user_cap_nano,enabled FROM invites WHERE invite_id=?",
                                    (invite_id,)).fetchone()
                if invite is None or invite[1] != 1:
                    db.execute("ROLLBACK")
                    raise BetaError("unauthorized")
                recent = db.execute(
                    "SELECT created_unix FROM usage WHERE principal_kind='invite' AND principal_id=? "
                    "ORDER BY created_unix DESC LIMIT ?",
                    (identity.subject, RATE_REQUESTS_PER_WINDOW)).fetchall()
                if (recent and now - recent[0][0] < MIN_REQUEST_INTERVAL_SECONDS) or (
                        len(recent) >= RATE_REQUESTS_PER_WINDOW
                        and now - recent[-1][0] < RATE_WINDOW_SECONDS):
                    db.execute("ROLLBACK")
                    raise BetaError("rate_limited")
                user_used = db.execute(
                    f"SELECT {self._accounted_sql()} FROM usage "
                    "WHERE principal_kind='invite' AND principal_id=?",
                    (identity.subject,)).fetchone()[0]
                if user_used + MAX_RESERVATION_NANO > invite[0]:
                    db.execute("ROLLBACK")
                    raise BetaError("allowance_exhausted")
                quota_day, quota_charged = None, 0
            else:
                quota_day = None if identity.kind == "guest" else utc_day(now)
                condition = "principal_kind=? AND principal_id=? AND quota_charged=1"
                parameters = [identity.kind, identity.subject]
                if quota_day is not None:
                    condition += " AND quota_day=?"
                    parameters.append(quota_day)
                used = db.execute(f"SELECT COUNT(*) FROM usage WHERE {condition}", parameters).fetchone()[0]
                limit = guest_limit if identity.kind == "guest" else daily_limit
                if used >= limit:
                    db.execute("ROLLBACK")
                    raise BetaError("guest_limit_reached" if identity.kind == "guest"
                                    else "daily_limit_reached")
                quota_charged = 1
            global_used = db.execute(f"SELECT {self._accounted_sql()} FROM usage").fetchone()[0]
            global_cap = int(db.execute("SELECT value FROM metadata WHERE key='global_cap_nano'").fetchone()[0])
            global_cap = min(global_cap, GLOBAL_COST_CEILING_NANO)
            if global_used + MAX_RESERVATION_NANO > global_cap:
                db.execute("ROLLBACK")
                raise BetaError("allowance_exhausted")
            db.execute("INSERT INTO usage VALUES(?,?,?,?,?,?,?,?,?,?,?)", (
                request_id, invite_id, identity.kind, identity.subject, quota_day,
                quota_charged, now, now, MAX_RESERVATION_NANO, None, "reserved"))
            db.execute("COMMIT")

    def mark_submitted(self, request_id):
        now = int(time.time())
        with closing(self._connect()) as db:
            changed = db.execute("UPDATE usage SET status='submitted',updated_unix=? "
                                 "WHERE request_id=? AND status='reserved'", (now, request_id)).rowcount
        if changed != 1:
            raise BetaError("reservation_changed")

    def finalize(self, request_id, *, actual_nano=None, uncertain=False,
                 release_question=False):
        if uncertain:
            status, actual_nano = "uncertain", None
        else:
            if type(actual_nano) is not int or not 0 <= actual_nano <= MAX_RESERVATION_NANO:
                raise BetaError("usage_unverifiable")
            status = "complete"
        with closing(self._connect()) as db:
            changed = db.execute("UPDATE usage SET status=?,actual_nano=?,updated_unix=?,"
                                 "quota_charged=CASE WHEN ? THEN 0 ELSE quota_charged END "
                                 "WHERE request_id=? AND status IN ('reserved','submitted','running')",
                                 (status, actual_nano, int(time.time()), release_question,
                                  request_id)).rowcount
        if changed != 1:
            raise BetaError("reservation_changed")

    def usage(self, identity):
        identity = self._identity(identity)
        with closing(self._connect()) as db:
            user = db.execute(
                f"SELECT {self._accounted_sql()} FROM usage WHERE principal_kind=? AND principal_id=?",
                (identity.kind, identity.subject)).fetchone()[0]
            total = db.execute(f"SELECT {self._accounted_sql()} FROM usage").fetchone()[0]
            uncertain = db.execute(
                "SELECT COUNT(*) FROM usage WHERE principal_kind=? AND principal_id=? "
                "AND status='uncertain'", (identity.kind, identity.subject)).fetchone()[0]
        return {"user_accounted_nano_usd": user, "global_accounted_nano_usd": total,
                "uncertain_requests": uncertain,
                "reservation_nano_usd_per_request": MAX_RESERVATION_NANO}

    def questions_remaining(self, identity, limit, *, day=None):
        identity = self._identity(identity)
        sql = ("SELECT COUNT(*) FROM usage WHERE principal_kind=? AND principal_id=? "
               "AND quota_charged=1")
        parameters = [identity.kind, identity.subject]
        if day is not None:
            sql += " AND quota_day=?"
            parameters.append(day)
        with closing(self._connect()) as db:
            used = db.execute(sql, parameters).fetchone()[0]
        return max(0, limit - used)


class BetaApplication:
    def __init__(self, *, store, root=ROOT, model_factory=None, library=None,
                 access=None, streaming=False):
        self.store = store
        self.access = access if access is not None else AccountAccess.from_environ(store.path)
        self.root = Path(root)
        self.model_factory = model_factory or (
            lambda: ChatModel(root=self.root, streaming=streaming))
        self.library = library if library is not None else PassageLibrary(self.root)
        self.model = None
        self.lock = threading.Lock()
        self.running = False
        self.closed = False
        self.jobs = {}

    def _expire_locked(self):
        now = time.monotonic()
        for request_id in list(self.jobs):
            job = self.jobs[request_id]
            if job["status"] != "running" and now - job["created"] >= RESULT_TTL_SECONDS:
                del self.jobs[request_id]
        completed = [key for key, value in self.jobs.items() if value["status"] != "running"]
        for request_id in completed[:-MAX_RETAINED_RESULTS]:
            del self.jobs[request_id]

    def submit(self, identity, body):
        identity = self.store._identity(identity)
        if not isinstance(body, dict) or set(body) != {"messages"}:
            raise BetaError("invalid_messages")
        messages = body["messages"]
        try:
            build_payload(messages)
        except ChatModelError:
            raise BetaError("invalid_messages") from None
        with self.lock:
            self._expire_locked()
            if self.closed:
                raise BetaError("closed")
            if self.running:
                raise BetaError("busy")
            request_id = secrets.token_urlsafe(24)
            self.store.reserve(identity, request_id, daily_limit=self.access.daily_limit)
            self.running = True
            self.jobs[request_id] = {
                "identity": identity, "status": "running", "revision": 0,
                "answer": "", "complete": False, "created": time.monotonic(),
            }
        worker = threading.Thread(target=self._generate, args=(request_id, identity, messages), daemon=True)
        try:
            worker.start()
        except Exception:
            self.store.finalize(request_id, actual_nano=0, release_question=True)
            with self.lock:
                self.running = False
                self.jobs.pop(request_id, None)
            raise BetaError("worker_unavailable") from None
        return request_id

    def _generate(self, request_id, identity, messages):
        def on_progress(answer, revision):
            with self.lock:
                job = self.jobs.get(request_id)
                if (self.closed or job is None or job.get("identity") != identity
                        or job.get("status") != "running"
                        or type(revision) is not int or revision <= job.get("revision", 0)
                        or not isinstance(answer, str)
                        or not answer.startswith(job.get("answer", ""))):
                    return
                job["answer"] = answer
                job["revision"] = revision

        def snapshot():
            with self.lock:
                job = self.jobs.get(request_id, {})
                return job.get("answer", ""), job.get("revision", 0)

        try:
            if self.model is None:
                self.model = self.model_factory()
            sources, notes = self.library.select(messages)
            evidence_context = self.library.context(sources, notes)
        except Exception:
            try:
                self.store.finalize(request_id, actual_nano=0, release_question=True)
            except BetaError:
                pass
            outcome = {"status": "error", "error": {"code": "generation_unavailable",
                "message": "The beta could not finish this request. It was not retried."}}
        else:
            try:
                self.store.mark_submitted(request_id)
                options = {"evidence_context": evidence_context}
                if getattr(self.model, "supports_progress", False):
                    options["on_progress"] = on_progress
                result = self.model.generate(messages, **options)
                value = result.get("usage", {}).get("estimated_usd")
                if type(value) not in (float, int) or not math.isfinite(value) or value < 0:
                    raise BetaError("usage_unverifiable")
                actual = int((Decimal(str(value)) * Decimal(1_000_000_000)).to_integral_value(
                    rounding=ROUND_CEILING))
                self.store.finalize(request_id, actual_nano=actual)
                partial, revision = snapshot()
                final_answer = result["answer"]
                if final_answer != partial:
                    revision += 1
                outcome = {"status": "complete", "answer": final_answer,
                           "sources": sources, "source_notes": notes,
                           "complete": result["answer_complete"],
                           "warnings": result.get("warnings", []),
                           "revision": revision}
            except ChatModelError as exc:
                if exc.code in {"invalid_messages", "input_too_long", "not_configured",
                                "checkpoint_unavailable", "runtime_unavailable", "busy",
                                "blocked", "closed"}:
                    try:
                        self.store.finalize(request_id, actual_nano=0, release_question=True)
                    except BetaError:
                        pass
                else:
                    try:
                        self.store.finalize(request_id, uncertain=True)
                    except BetaError:
                        pass
                outcome = {"status": "error", "error": {"code": "generation_unavailable",
                    "message": "The beta could not finish this request. It was not retried."}}
            except Exception:
                try:
                    self.store.finalize(request_id, uncertain=True)
                except BetaError:
                    pass
                outcome = {"status": "error", "error": {"code": "generation_unavailable",
                    "message": "The beta could not finish this request. It was not retried."}}
        partial, revision = snapshot()
        if outcome["status"] == "error" and partial:
            outcome.update({"partial_answer": partial, "complete": False,
                            "revision": revision})
        with self.lock:
            if not self.closed:
                self.jobs[request_id] = {**outcome, "identity": identity,
                                         "created": time.monotonic()}
                self._expire_locked()
            self.running = False

    def result(self, identity, request_id):
        identity = self.store._identity(identity)
        with self.lock:
            self._expire_locked()
            job = self.jobs.get(request_id)
            if job is None or job["identity"] != identity:
                return None
            return {key: value for key, value in job.items()
                    if key not in {"identity", "created"}}

    def status(self, identity):
        identity = self.store._identity(identity)
        return {"ready": not self.closed, "busy": self.running,
                "public_model": "Meforash 0.1",
                "model": "Inkling · retained B original-text adapter",
                "provider": "Thinking Machines / Tinker",
                "source_count": self.library.count,
                "conversation_storage": "not_stored",
                "usage": self.store.usage(identity),
                "access": self.access.access_description(identity, self.store)}

    def close(self):
        with self.lock:
            self.closed = True
            self.jobs.clear()
        if self.model is not None:
            self.model.close()


class BetaHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    def handle_error(self, request, client_address):
        pass


class LoginLimiter:
    def __init__(self):
        self.lock = threading.Lock()
        self.attempts = {}

    def allow(self, peer_hash, now=None):
        now = time.monotonic() if now is None else now
        with self.lock:
            values = [value for value in self.attempts.get(peer_hash, []) if now - value < 300]
            if len(values) >= 8:
                self.attempts[peer_hash] = values
                return False
            values.append(now)
            self.attempts[peer_hash] = values
            return True


def handler_for(app, *, origin, secure_cookie, trust_real_ip=False):
    parsed = urlsplit(origin)
    if (parsed.scheme not in ({"https"} if secure_cookie else {"http"})
            or not parsed.netloc or parsed.path or parsed.query or parsed.fragment
            or parsed.username is not None or parsed.password is not None):
        raise ValueError("Configured beta origin is invalid for its cookie mode.")
    limiter = LoginLimiter()

    class Handler(BaseHTTPRequestHandler):
        server_version = "BibleBetaCandidateV1"
        def log_message(self, format, *args):
            pass

        def _origin_valid(self):
            return (self.headers.get("Host") == parsed.netloc
                    and self.headers.get("Origin") == origin)

        def _cookie(self, name):
            try:
                return SimpleCookie(self.headers.get("Cookie", ""))[name].value
            except (KeyError, ValueError, CookieError):
                return None

        def _identity(self):
            account = app.access.account_identity(self._cookie(ACCOUNT_COOKIE))
            if account is not None:
                return account
            invite = app.store.session_user(self._cookie(SESSION_COOKIE))
            if invite is not None:
                return AccessIdentity("invite", invite)
            return app.access.guest_identity(self._cookie(GUEST_COOKIE))

        def _peer(self):
            if not trust_real_ip:
                return str(self.client_address[0])
            values = self.headers.get_all("X-Real-IP", [])
            if len(values) != 1 or "," in values[0]:
                raise AccessError("origin_rejected")
            peer = validated_peer(values[0].strip())
            if peer == "invalid-peer":
                raise AccessError("origin_rejected")
            return peer

        def _send(self, code, value, *, cookie=None, clear_cookie=False, cookies=()):
            data = json.dumps(value, ensure_ascii=False, allow_nan=False).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header("Content-Security-Policy", "default-src 'none'; frame-ancestors 'none'")
            configured = list(cookies)
            if cookie is not None:
                configured.append((SESSION_COOKIE, cookie, SESSION_TTL_SECONDS))
            elif clear_cookie:
                configured.append((SESSION_COOKIE, "", 0))
            for name, value, max_age in configured:
                suffix = "; Secure" if secure_cookie else ""
                self.send_header("Set-Cookie", f"{name}={value}; Path=/; HttpOnly; "
                                 f"SameSite=Strict; Max-Age={max_age}{suffix}")
            self.end_headers()
            try:
                self.wfile.write(data)
            except (BrokenPipeError, ConnectionResetError):
                pass

        def _body(self):
            if self.headers.get("Content-Type", "").split(";")[0].strip() != "application/json":
                raise BetaError("json_required")
            if self.headers.get("Transfer-Encoding"):
                raise BetaError("request_too_large")
            try:
                size = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                raise BetaError("request_too_large") from None
            if not 0 < size <= MAX_REQUEST_BYTES:
                raise BetaError("request_too_large")
            self.connection.settimeout(15)
            try:
                return strict_json(self.rfile.read(size))
            except (ValueError, TypeError, UnicodeError, TimeoutError):
                raise BetaError("invalid_json") from None

        def do_GET(self):
            path = urlsplit(self.path).path
            if path == "/health":
                return self._send(200, {"status": "candidate", "provider_initialized": app.model is not None})
            if path == "/api/access":
                return self._send(200, {"public_access": app.access.enabled,
                    "email_login_available": app.access.enabled and app.access.auth_client is not None})
            identity = self._identity()
            if identity is None:
                return self._send(401, {"error": {"code": "unauthorized", "message": "Sign in with an invitation."}})
            if path == "/api/status":
                return self._send(200, app.status(identity))
            if path.startswith("/api/chat/"):
                result = app.result(identity, path.removeprefix("/api/chat/"))
                if result is not None:
                    return self._send(200, result)
            return self._send(404, {"error": {"code": "not_found", "message": "This beta resource is unavailable."}})

        def do_POST(self):
            if not self._origin_valid():
                return self._send(403, {"error": {"code": "origin_rejected", "message": "This request origin is not allowed."}})
            path = urlsplit(self.path).path
            try:
                body = self._body()
                if path == "/api/login":
                    peer_hash = _sha(str(self.client_address[0]).encode())
                    if not limiter.allow(peer_hash):
                        raise BetaError("rate_limited")
                    if (not isinstance(body, dict) or set(body) != {"invite_id", "invite_secret"}
                            or not app.store.authenticate_invite(body["invite_id"], body["invite_secret"])):
                        raise BetaError("unauthorized")
                    token, _ = app.store.create_session(body["invite_id"])
                    return self._send(200, {"status": "signed_in"}, cookie=token)
                if path == "/api/guest":
                    if not isinstance(body, dict) or body:
                        raise BetaError("invalid_json")
                    identity, token = app.access.guest(
                        self._cookie(GUEST_COOKIE), self._peer())
                    cookies = () if token is None else (
                        (GUEST_COOKIE, token, GUEST_COOKIE_SECONDS),)
                    return self._send(200, app.status(identity), cookies=cookies)
                if path == "/api/auth/start":
                    if not isinstance(body, dict) or set(body) != {"email"}:
                        raise BetaError("invalid_json")
                    challenge = app.access.start(body["email"], self._peer())
                    return self._send(200, {"status": "code_sent"}, cookies=(
                        (CHALLENGE_COOKIE, challenge, CHALLENGE_SECONDS),))
                if path == "/api/auth/verify":
                    if not isinstance(body, dict) or set(body) != {"email", "token"}:
                        raise BetaError("invalid_json")
                    identity, session = app.access.verify(
                        body["email"], body["token"], self._cookie(CHALLENGE_COOKIE),
                        self._peer())
                    return self._send(200, app.status(identity), cookies=(
                        (ACCOUNT_COOKIE, session, ACCOUNT_SESSION_SECONDS),
                        (CHALLENGE_COOKIE, "", 0)))
                identity = self._identity()
                if identity is None:
                    raise BetaError("unauthorized")
                if path == "/api/logout":
                    account_token = self._cookie(ACCOUNT_COOKIE)
                    if account_token is not None:
                        app.access.logout(account_token)
                        return self._send(200, {"status": "signed_out"}, cookies=(
                            (ACCOUNT_COOKIE, "", 0),))
                    app.store.delete_session(self._cookie(SESSION_COOKIE))
                    return self._send(200, {"status": "signed_out"}, clear_cookie=True)
                if path != "/api/chat":
                    return self._send(404, {"error": {"code": "not_found", "message": "This beta resource is unavailable."}})
                request_id = app.submit(identity, body)
                return self._send(202, {"request_id": request_id})
            except (BetaError, AccessError) as exc:
                status = {"unauthorized": 401, "origin_rejected": 403,
                          "request_too_large": 413, "json_required": 415,
                          "busy": 409, "rate_limited": 429,
                          "allowance_exhausted": 429,
                          "guest_limit_reached": 403,
                          "daily_limit_reached": 429,
                          "auth_unavailable": 503,
                          "invalid_code": 400,
                          "closed": 503, "worker_unavailable": 503}.get(exc.code, 400)
                messages = {"unauthorized": "Invitation credentials are invalid.",
                            "busy": "One answer is already being generated.",
                            "rate_limited": "Please wait before trying again.",
                            "allowance_exhausted": "This beta allowance is exhausted.",
                            "guest_limit_reached": "The three guest questions have been used.",
                            "daily_limit_reached": "The daily account question limit has been reached.",
                            "auth_unavailable": "Email sign-in is temporarily unavailable.",
                            "invalid_code": "The sign-in code is invalid or expired.",
                            "request_too_large": "The request is too large.",
                            "json_required": "This endpoint requires JSON."}
                return self._send(status, {"error": {"code": exc.code,
                    "message": messages.get(exc.code, "The beta could not accept this request.")}})

        def do_OPTIONS(self):
            self._send(403, {"error": {"code": "origin_rejected",
                                       "message": "Cross-site requests are not supported."}})

    return Handler


def load_invite_config(path):
    path = Path(path)
    if path.is_symlink() or not path.is_file():
        raise ValueError("Invite config must be a regular non-symlink file.")
    return validate_invite_config(strict_json(path.read_bytes()))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--invite-config", required=True)
    parser.add_argument("--database", default="runs/private-beta-v1/beta.sqlite3")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--origin")
    args = parser.parse_args(argv)
    if not 1024 <= args.port <= 65535:
        parser.error("Choose a port between 1024 and 65535.")
    local = args.host in {"127.0.0.1", "localhost"}
    origin = args.origin or (f"http://{args.host}:{args.port}" if local else None)
    if not local and (origin is None or urlsplit(origin).scheme != "https"):
        parser.error("Hosted mode requires an explicit HTTPS origin and TLS-terminating proxy.")
    try:
        store = BetaStore(args.database, load_invite_config(args.invite_config))
        app = BetaApplication(store=store)
        server = BetaHTTPServer((args.host, args.port),
                                handler_for(app, origin=origin, secure_cookie=not local))
    except Exception:
        parser.exit(1, "The beta backend candidate could not start. Check its hash-only invite config, ledger, runtime and source files.\n")
    print(f"Bible beta backend candidate: {origin}", flush=True)
    print("Conversation text is sent to Tinker for answers and is not stored by this backend.", flush=True)
    try:
        server.serve_forever(poll_interval=0.25)
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        app.close()


if __name__ == "__main__":
    raise SystemExit(main())
