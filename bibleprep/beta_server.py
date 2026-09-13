"""Invite-only Candidate Beta backend; loopback-only unless explicitly hosted.

The backend reuses the retained B chat model and passage library.  It stores no
conversation text.  SQLite retains only hashed authentication material,
sessions, request timing/status, and conservative cost accounting.
"""
from __future__ import annotations

import argparse
from collections import deque
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
    TERMS_VERSION,
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
DEFAULT_MODEL_WORKERS = 1
MAX_MODEL_WORKERS = 10
DEFAULT_QUEUE_LIMIT = 12
MAX_QUEUE_LIMIT = 64
DEFAULT_QUEUE_TIMEOUT_SECONDS = 120
MAX_QUEUE_TIMEOUT_SECONDS = 900
SSE_HEARTBEAT_SECONDS = 10
MAX_EVENT_STREAMS = 48
MAX_EVENT_STREAMS_PER_IDENTITY = 2
MAX_EVENT_STREAMS_PER_JOB = 2


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
            # mark_submitted commits before the provider call. A leftover reservation
            # therefore never left this process, while submitted work remains uncertain.
            db.execute("UPDATE usage SET status='complete',actual_nano=0,quota_charged=0,"
                       "updated_unix=? WHERE status='reserved'", (now,))
            db.execute("UPDATE usage SET status='uncertain',updated_unix=? "
                       "WHERE status IN ('submitted','running')", (now,))
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
    """Bounded FIFO coordinator whose workers never share model transports."""

    def __init__(self, *, store, root=ROOT, model_factory=None, library=None,
                 access=None, streaming=False, worker_count=DEFAULT_MODEL_WORKERS,
                 queue_limit=DEFAULT_QUEUE_LIMIT,
                 queue_timeout_seconds=DEFAULT_QUEUE_TIMEOUT_SECONDS,
                 clock=None):
        if type(worker_count) is not int or not 1 <= worker_count <= MAX_MODEL_WORKERS:
            raise ValueError(f"worker_count must be between 1 and {MAX_MODEL_WORKERS}.")
        if type(queue_limit) is not int or not 1 <= queue_limit <= MAX_QUEUE_LIMIT:
            raise ValueError(f"queue_limit must be between 1 and {MAX_QUEUE_LIMIT}.")
        if (type(queue_timeout_seconds) not in (int, float)
                or not 1 <= queue_timeout_seconds <= MAX_QUEUE_TIMEOUT_SECONDS):
            raise ValueError(
                f"queue_timeout_seconds must be between 1 and {MAX_QUEUE_TIMEOUT_SECONDS}.")
        self.store = store
        self.access = access if access is not None else AccountAccess.from_environ(store.path)
        self.root = Path(root)
        self.model_factory = model_factory or (
            lambda: ChatModel(root=self.root, streaming=streaming))
        self.library = library if library is not None else PassageLibrary(self.root)
        self.worker_count = worker_count
        self.queue_limit = queue_limit
        self.queue_timeout_seconds = float(queue_timeout_seconds)
        self.clock = clock or time.monotonic
        self.lock = threading.Lock()
        self.condition = threading.Condition(self.lock)
        self.closed = False
        self.jobs = {}
        self.queue = deque()
        self.event_streams = 0
        self.event_streams_by_identity = {}
        self.event_streams_by_job = {}
        self.slots = [
            {"model": None, "active": False, "terminal": None}
            for _ in range(worker_count)
        ]
        self.worker_threads = []
        self.reaper_thread = None
        try:
            for index in range(worker_count):
                worker = threading.Thread(
                    target=self._worker_loop, args=(index,), daemon=True,
                    name=f"meforash-model-{index + 1}")
                worker.start()
                self.worker_threads.append(worker)
            self.reaper_thread = threading.Thread(
                target=self._reaper_loop, daemon=True, name="meforash-queue-reaper")
            self.reaper_thread.start()
        except Exception:
            with self.condition:
                self.closed = True
                self.condition.notify_all()
            raise BetaError("worker_unavailable") from None

    @property
    def model(self):
        """Compatibility view of the first lazy model slot."""
        return self.slots[0]["model"]

    @model.setter
    def model(self, value):
        self.slots[0]["model"] = value

    @property
    def running(self):
        return any(slot["active"] for slot in self.slots)

    @staticmethod
    def _model_status(model):
        if model is None:
            return None
        status_method = getattr(model, "status", None)
        if not callable(status_method):
            return {}
        try:
            status = status_method()
        except Exception:
            return {"ready": False}
        return status if isinstance(status, dict) else {"ready": False}

    def _slot_error_locked(self, slot):
        if slot["terminal"] is not None:
            return slot["terminal"]
        status = self._model_status(slot["model"])
        if status is None:
            return None
        if status.get("closed") is True:
            return "closed"
        if status.get("blocked") is True:
            return "blocked"
        if status.get("ready") is False:
            return "worker_unavailable"
        return None

    def _acceptance_error_locked(self):
        errors = [self._slot_error_locked(slot) for slot in self.slots]
        if any(error is None for error in errors):
            return None
        return errors[0] if len(set(errors)) == 1 else "worker_unavailable"

    def health(self):
        """Report readiness without constructing or contacting a model provider."""
        with self.lock:
            ready = not self.closed and self._acceptance_error_locked() is None
            return {"status": "candidate" if ready else "unavailable",
                    "ready": ready, "busy": self.running,
                    "provider_initialized": any(slot["model"] is not None
                                                for slot in self.slots)}

    def _finish_queued_locked(self, request_id, *, code, message):
        job = self.jobs.get(request_id)
        if job is None or job.get("status") != "queued":
            return
        try:
            self.store.finalize(request_id, actual_nano=0, release_question=True)
        except BetaError:
            pass
        now = self.clock()
        self.jobs[request_id] = {
            "identity": job["identity"], "status": "error",
            "error": {"code": code, "message": message},
            "complete": False, "revision": 0,
            "queue_wait_seconds": round(max(0, now - job["queued_at"]), 3),
            "run_elapsed_seconds": 0.0, "completed_at": now,
        }
        self.condition.notify_all()

    def _release_queue_locked(self, *, code, message):
        while self.queue:
            self._finish_queued_locked(self.queue.popleft(), code=code, message=message)

    def _expire_locked(self):
        now = self.clock()
        while self.queue:
            request_id = self.queue[0]
            job = self.jobs.get(request_id)
            if job is None or job.get("status") != "queued":
                self.queue.popleft()
                continue
            if now - job["queued_at"] < self.queue_timeout_seconds:
                break
            self.queue.popleft()
            self._finish_queued_locked(
                request_id, code="queue_timeout",
                message="The request waited too long and was not submitted. Please try again.")
        terminal = [key for key, value in self.jobs.items()
                    if value.get("status") not in {"queued", "running"}]
        for request_id in list(terminal):
            if now - self.jobs[request_id]["completed_at"] >= RESULT_TTL_SECONDS:
                del self.jobs[request_id]
        terminal = [key for key, value in self.jobs.items()
                    if value.get("status") not in {"queued", "running"}]
        for request_id in terminal[:-MAX_RETAINED_RESULTS]:
            del self.jobs[request_id]

    def _reaper_loop(self):
        with self.condition:
            while not self.closed:
                self._expire_locked()
                delay = self.queue_timeout_seconds
                if self.queue:
                    job = self.jobs.get(self.queue[0])
                    if job is not None and job.get("status") == "queued":
                        delay = max(0.01, self.queue_timeout_seconds
                                    - (self.clock() - job["queued_at"]))
                self.condition.wait(timeout=delay)

    def submit(self, identity, body):
        identity = self.store._identity(identity)
        if not self.access.terms_accepted(identity):
            raise BetaError("terms_required")
        if not isinstance(body, dict) or set(body) != {"messages"}:
            raise BetaError("invalid_messages")
        messages = body["messages"]
        try:
            build_payload(messages)
        except ChatModelError:
            raise BetaError("invalid_messages") from None
        with self.condition:
            self._expire_locked()
            if self.closed:
                raise BetaError("closed")
            model_error = self._acceptance_error_locked()
            if model_error is not None:
                raise BetaError(model_error)
            if any(job.get("identity") == identity
                   and job.get("status") in {"queued", "running"}
                   for job in self.jobs.values()):
                raise BetaError("request_pending")
            if len(self.queue) >= self.queue_limit:
                raise BetaError("queue_full")
            request_id = secrets.token_urlsafe(24)
            self.store.reserve(identity, request_id, daily_limit=self.access.daily_limit)
            now = self.clock()
            self.jobs[request_id] = {
                "identity": identity, "status": "queued", "revision": 0,
                "answer": "", "complete": False, "queued_at": now,
                "messages": messages, "submitted": False,
            }
            self.queue.append(request_id)
            self.condition.notify_all()
            return request_id

    def _worker_loop(self, slot_index):
        slot = self.slots[slot_index]
        while True:
            with self.condition:
                self._expire_locked()
                error = self._slot_error_locked(slot)
                if error is not None:
                    slot["terminal"] = error
                    if self._acceptance_error_locked() is not None:
                        self._release_queue_locked(
                            code="model_unavailable",
                            message="The request was not submitted because the model became unavailable.")
                    return
                while not self.closed and not self.queue:
                    self.condition.wait(timeout=self.queue_timeout_seconds)
                    self._expire_locked()
                    error = self._slot_error_locked(slot)
                    if error is not None:
                        slot["terminal"] = error
                        if self._acceptance_error_locked() is not None:
                            self._release_queue_locked(
                                code="model_unavailable",
                                message="The request was not submitted because the model became unavailable.")
                        return
                if self.closed:
                    return
                request_id = self.queue.popleft()
                job = self.jobs.get(request_id)
                if job is None or job.get("status") != "queued":
                    continue
                now = self.clock()
                job.update({"status": "running", "started_at": now,
                            "queue_wait_seconds": round(max(0, now - job["queued_at"]), 3)})
                slot["active"] = True
                self.condition.notify_all()
            try:
                self._generate(slot_index, request_id, job["identity"], job["messages"])
            except Exception:
                with self.condition:
                    slot["active"] = False
                    slot["terminal"] = "worker_unavailable"
                    failed = self.jobs.get(request_id)
                    if (not self.closed and failed is not None
                            and failed.get("status") == "running"):
                        now = self.clock()
                        self.jobs[request_id] = {
                            "identity": failed["identity"], "status": "error",
                            "error": {"code": "generation_unavailable",
                                      "message": "The beta could not finish this request. It was not retried."},
                            "complete": False, "revision": failed.get("revision", 0),
                            "queue_wait_seconds": failed.get("queue_wait_seconds", 0.0),
                            "run_elapsed_seconds": round(
                                max(0, now - failed.get("started_at", now)), 3),
                            "completed_at": now,
                        }
                    if self._acceptance_error_locked() is not None:
                        self._release_queue_locked(
                            code="model_unavailable",
                            message="The request was not submitted because the model became unavailable.")
                    self.condition.notify_all()
                return
            with self.condition:
                slot["active"] = False
                error = self._slot_error_locked(slot)
                if error is not None:
                    slot["terminal"] = error
                    if self._acceptance_error_locked() is not None:
                        self._release_queue_locked(
                            code="model_unavailable",
                            message="The request was not submitted because the model became unavailable.")
                self.condition.notify_all()

    def _generate(self, slot_index, request_id, identity, messages):
        slot = self.slots[slot_index]

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
                self.condition.notify_all()

        def snapshot():
            with self.lock:
                job = self.jobs.get(request_id, {})
                return job.get("answer", ""), job.get("revision", 0)

        try:
            sources, notes = self.library.select(messages)
            evidence_context = self.library.context(sources, notes)
            if slot["model"] is None:
                candidate = self.model_factory()
                with self.lock:
                    duplicate = any(other["model"] is candidate
                                    for index, other in enumerate(self.slots)
                                    if index != slot_index)
                    publish = not self.closed and not duplicate
                    if publish:
                        slot["model"] = candidate
                if not publish:
                    if self.closed:
                        try:
                            candidate.close()
                        except Exception:
                            pass
                        try:
                            self.store.finalize(
                                request_id, actual_nano=0, release_question=True)
                        except BetaError:
                            pass
                        return
                    raise RuntimeError("Model factories must return independent instances.")
            model = slot["model"]
        except Exception:
            with self.lock:
                slot["terminal"] = "worker_unavailable"
            try:
                self.store.finalize(request_id, actual_nano=0, release_question=True)
            except BetaError:
                pass
            outcome = {"status": "error", "error": {"code": "generation_unavailable",
                "message": "The beta could not finish this request. It was not retried."}}
        else:
            try:
                with self.lock:
                    job = self.jobs.get(request_id)
                    if self.closed or job is None or job.get("status") != "running":
                        try:
                            self.store.finalize(
                                request_id, actual_nano=0, release_question=True)
                        except BetaError:
                            pass
                        return
                    self.store.mark_submitted(request_id)
                    job["submitted"] = True
                options = {"evidence_context": evidence_context}
                if getattr(model, "supports_progress", False):
                    options["on_progress"] = on_progress
                result = model.generate(messages, **options)
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
                if exc.code in {"blocked", "closed"}:
                    with self.lock:
                        slot["terminal"] = exc.code
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
            job = self.jobs.get(request_id)
            if not self.closed and job is not None:
                now = self.clock()
                started_at = job.get("started_at", now)
                self.jobs[request_id] = {
                    **outcome, "identity": identity,
                    "queue_wait_seconds": job.get("queue_wait_seconds", 0.0),
                    "run_elapsed_seconds": round(max(0, now - started_at), 3),
                    "completed_at": now,
                }
                self._expire_locked()
                self.condition.notify_all()

    def _result_locked(self, identity, request_id):
        job = self.jobs.get(request_id)
        if job is None or job["identity"] != identity:
            return None
        now = self.clock()
        safe_fields = {"status", "revision", "answer", "complete", "error",
                       "partial_answer", "sources", "source_notes", "warnings",
                       "queue_wait_seconds", "run_elapsed_seconds"}
        public = {key: value for key, value in job.items() if key in safe_fields}
        if job["status"] == "queued":
            try:
                public["queue_position"] = list(self.queue).index(request_id) + 1
            except ValueError:
                public["queue_position"] = 1
            public["queue_wait_seconds"] = round(max(0, now - job["queued_at"]), 3)
        elif job["status"] == "running":
            public["run_elapsed_seconds"] = round(max(0, now - job["started_at"]), 3)
        return public

    def result(self, identity, request_id):
        identity = self.store._identity(identity)
        with self.lock:
            self._expire_locked()
            return self._result_locked(identity, request_id)

    def open_event_stream(self, identity, request_id):
        """Reserve a bounded result subscription only after ownership is established."""
        identity = self.store._identity(identity)
        identity_key = (identity.kind, identity.subject)
        with self.condition:
            self._expire_locked()
            result = self._result_locked(identity, request_id)
            if result is None:
                return None
            if (self.event_streams >= MAX_EVENT_STREAMS
                    or self.event_streams_by_identity.get(identity_key, 0)
                    >= MAX_EVENT_STREAMS_PER_IDENTITY
                    or self.event_streams_by_job.get(request_id, 0)
                    >= MAX_EVENT_STREAMS_PER_JOB):
                raise BetaError("stream_limit")
            self.event_streams += 1
            self.event_streams_by_identity[identity_key] = (
                self.event_streams_by_identity.get(identity_key, 0) + 1)
            self.event_streams_by_job[request_id] = (
                self.event_streams_by_job.get(request_id, 0) + 1)
            return result

    def close_event_stream(self, identity, request_id):
        identity = self.store._identity(identity)
        identity_key = (identity.kind, identity.subject)
        with self.condition:
            if self.event_streams_by_identity.get(identity_key, 0) <= 0:
                return
            if self.event_streams_by_job.get(request_id, 0) <= 0:
                return
            self.event_streams = max(0, self.event_streams - 1)
            for counts, key in ((self.event_streams_by_identity, identity_key),
                                (self.event_streams_by_job, request_id)):
                counts[key] -= 1
                if counts[key] == 0:
                    del counts[key]

    def wait_for_result_change(self, identity, request_id, previous, timeout):
        """Wait for a safe public job snapshot to change or for a heartbeat deadline."""
        identity = self.store._identity(identity)
        deadline = time.monotonic() + timeout
        with self.condition:
            while True:
                self._expire_locked()
                result = self._result_locked(identity, request_id)
                if result is None or self._event_key(result) != self._event_key(previous):
                    return result
                remaining = deadline - time.monotonic()
                if remaining <= 0 or self.closed:
                    return result
                self.condition.wait(remaining)

    @staticmethod
    def _event_key(result):
        if not isinstance(result, dict):
            return None
        return (result.get("status"), result.get("revision"),
                result.get("queue_position"), result.get("complete"),
                result.get("error", {}).get("code")
                if isinstance(result.get("error"), dict) else None)

    def status(self, identity):
        identity = self.store._identity(identity)
        health = self.health()
        return {"ready": health["ready"], "busy": health["busy"],
                "public_model": "Meforash 0.1",
                "model": "Inkling · retained B original-text adapter",
                "provider": "Thinking Machines / Tinker",
                "source_count": self.library.count,
                "conversation_storage": "not_stored",
                "usage": self.store.usage(identity),
                "access": self.access.access_description(identity, self.store)}

    def close(self):
        with self.condition:
            if self.closed:
                return
            self.closed = True
            self._release_queue_locked(
                code="shutdown",
                message="The request was not submitted because the service stopped.")
            self.jobs.clear()
            self.condition.notify_all()
            models = [slot["model"] for slot in self.slots if slot["model"] is not None]
        for model in models:
            try:
                model.close()
            except Exception:
                pass
        deadline = time.monotonic() + 5
        for thread in self.worker_threads:
            thread.join(max(0, deadline - time.monotonic()))
        if self.reaper_thread is not None:
            self.reaper_thread.join(max(0, deadline - time.monotonic()))


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
        protocol_version = "HTTP/1.1"
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

        def _write_event(self, value):
            data = json.dumps(value, ensure_ascii=False, allow_nan=False,
                              separators=(",", ":")).encode("utf-8")
            self.wfile.write(b"event: result\n")
            self.wfile.write(b"data: " + data + b"\n\n")
            self.wfile.flush()

        def _serve_events(self, identity, request_id):
            initial = app.open_event_stream(identity, request_id)
            if initial is None:
                return self._send(404, {"error": {"code": "not_found",
                    "message": "This beta resource is unavailable."}})
            opened = False
            try:
                if self._identity() != identity:
                    return self._send(401, {"error": {"code": "unauthorized",
                        "message": "Sign in with an invitation."}})
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream; charset=utf-8")
                self.send_header("Cache-Control", "no-store")
                self.send_header("X-Accel-Buffering", "no")
                self.send_header("X-Content-Type-Options", "nosniff")
                self.send_header("Referrer-Policy", "no-referrer")
                self.send_header("X-Frame-Options", "DENY")
                self.send_header("Content-Security-Policy",
                                 "default-src 'none'; frame-ancestors 'none'")
                self.end_headers()
                opened = True
                current = initial
                self._write_event(current)
                while current.get("status") in {"queued", "running"}:
                    updated = app.wait_for_result_change(
                        identity, request_id, current, SSE_HEARTBEAT_SECONDS)
                    if self._identity() != identity or updated is None:
                        break
                    if app._event_key(updated) == app._event_key(current):
                        self.wfile.write(b": keep-alive\n\n")
                        self.wfile.flush()
                    else:
                        self._write_event(updated)
                    current = updated
            except (BrokenPipeError, ConnectionResetError, TimeoutError, OSError):
                pass
            finally:
                app.close_event_stream(identity, request_id)
                if opened:
                    self.close_connection = True

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
                health = app.health()
                return self._send(200 if health["ready"] else 503, health)
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
                if path.startswith("/api/chat/") and path.endswith("/events"):
                    identity = self._identity()
                    if identity is None:
                        raise BetaError("unauthorized")
                    request_id = path.removeprefix("/api/chat/").removesuffix("/events")
                    if not request_id or "/" in request_id or body:
                        raise BetaError("invalid_json")
                    return self._serve_events(identity, request_id)
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
                    if (not isinstance(body, dict)
                            or set(body) != {"email", "terms_version"}
                            or body["terms_version"] != TERMS_VERSION):
                        raise BetaError("terms_required")
                    challenge = app.access.start(
                        body["email"], self._peer(), terms_version=body["terms_version"])
                    return self._send(200, {"status": "code_sent"}, cookies=(
                        (CHALLENGE_COOKIE, challenge, CHALLENGE_SECONDS),))
                if path == "/api/auth/verify":
                    if (not isinstance(body, dict)
                            or set(body) != {"email", "token", "terms_version"}
                            or body["terms_version"] != TERMS_VERSION):
                        raise BetaError("terms_required")
                    identity, session = app.access.verify(
                        body["email"], body["token"], self._cookie(CHALLENGE_COOKIE),
                        self._peer(), terms_version=body["terms_version"])
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
                if path == "/api/accept-terms":
                    if (not isinstance(body, dict)
                            or set(body) != {"terms_version", "adult"}):
                        raise BetaError("terms_required")
                    app.access.accept_terms(
                        identity, body["terms_version"], body["adult"])
                    return self._send(200, app.status(identity))
                if path != "/api/chat":
                    return self._send(404, {"error": {"code": "not_found", "message": "This beta resource is unavailable."}})
                request_id = app.submit(identity, body)
                return self._send(202, {"request_id": request_id})
            except (BetaError, AccessError) as exc:
                status = {"unauthorized": 401, "origin_rejected": 403,
                          "request_too_large": 413, "json_required": 415,
                          "busy": 409, "request_pending": 409,
                          "queue_full": 503, "model_unavailable": 503,
                          "stream_limit": 429,
                          "rate_limited": 429,
                          "allowance_exhausted": 429,
                          "guest_limit_reached": 403,
                          "terms_required": 403,
                          "daily_limit_reached": 429,
                          "auth_unavailable": 503,
                          "invalid_code": 400,
                          "blocked": 503, "closed": 503,
                          "worker_unavailable": 503}.get(exc.code, 400)
                messages = {"unauthorized": "Invitation credentials are invalid.",
                            "busy": "One answer is already being generated.",
                            "request_pending": "Your previous question is still in progress.",
                            "queue_full": "The answer queue is full. Please try again shortly.",
                            "model_unavailable": "The model is temporarily unavailable.",
                            "stream_limit": "Too many answer streams are already open.",
                            "rate_limited": "Please wait before trying again.",
                            "allowance_exhausted": "This beta allowance is exhausted.",
                            "guest_limit_reached": "The three guest questions have been used.",
                            "terms_required": "Accept the current Terms and confirm that you are 18 or older before continuing.",
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
    parser.add_argument("--model-workers", type=int, default=DEFAULT_MODEL_WORKERS)
    parser.add_argument("--queue-limit", type=int, default=DEFAULT_QUEUE_LIMIT)
    parser.add_argument("--queue-timeout-seconds", type=int,
                        default=DEFAULT_QUEUE_TIMEOUT_SECONDS)
    args = parser.parse_args(argv)
    if not 1024 <= args.port <= 65535:
        parser.error("Choose a port between 1024 and 65535.")
    local = args.host in {"127.0.0.1", "localhost"}
    origin = args.origin or (f"http://{args.host}:{args.port}" if local else None)
    if not local and (origin is None or urlsplit(origin).scheme != "https"):
        parser.error("Hosted mode requires an explicit HTTPS origin and TLS-terminating proxy.")
    try:
        store = BetaStore(args.database, load_invite_config(args.invite_config))
        app = BetaApplication(
            store=store, worker_count=args.model_workers,
            queue_limit=args.queue_limit,
            queue_timeout_seconds=args.queue_timeout_seconds)
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
