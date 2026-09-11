"""Durable guest and verified-email access for the private beta server.

Only opaque hashes, verified Supabase user UUIDs, local session hashes, rate
events, and quota/accounting state are persisted.  Email addresses, peer IPs,
provider access tokens, prompts, and answers are never written to the ledger.
"""
from __future__ import annotations

from contextlib import closing
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import hmac
import ipaddress
import json
import os
from pathlib import Path
import secrets
import sqlite3
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen
import uuid


GUEST_COOKIE = "meforash_guest"
ACCOUNT_COOKIE = "meforash_account"
CHALLENGE_COOKIE = "meforash_auth_challenge"
GUEST_COOKIE_SECONDS = 400 * 24 * 3600
ACCOUNT_SESSION_SECONDS = 30 * 24 * 3600
CHALLENGE_SECONDS = 10 * 60
GUEST_QUESTION_LIMIT = 3
DEFAULT_ACCOUNT_DAILY_LIMIT = 20
MAX_ACCOUNT_DAILY_LIMIT = 1_000
MAX_IDENTITIES = 100_000
RATE_RETENTION_SECONDS = 24 * 3600


class AccessError(RuntimeError):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class AccessIdentity:
    kind: str
    subject: str

    def __post_init__(self):
        if self.kind not in {"guest", "account", "invite"} or not self.subject:
            raise ValueError("Invalid access identity.")


def utc_day(unix=None):
    return int((time.time() if unix is None else unix) // 86400)


def next_utc_reset(unix=None):
    value = time.time() if unix is None else unix
    next_unix = (int(value) // 86400 + 1) * 86400
    return datetime.fromtimestamp(next_unix, tz=timezone.utc).isoformat().replace("+00:00", "Z")


def normalize_email(value):
    if not isinstance(value, str):
        raise AccessError("invalid_email")
    email = value.strip()
    if (not 3 <= len(email) <= 254 or email.count("@") != 1
            or any(ord(char) < 33 or ord(char) > 126 for char in email)):
        raise AccessError("invalid_email")
    local, domain = email.rsplit("@", 1)
    if not local or not domain or "." not in domain or domain.startswith(".") or domain.endswith("."):
        raise AccessError("invalid_email")
    return f"{local}@{domain}".casefold()


def validated_peer(value):
    try:
        return ipaddress.ip_address(value).compressed
    except (TypeError, ValueError):
        return "invalid-peer"


class SupabaseAuthClient:
    """Minimal server-side Supabase email OTP client."""
    def __init__(self, url, publishable_key, *, opener=urlopen, timeout=12):
        parsed = urlsplit(url)
        if (parsed.scheme != "https" or not parsed.netloc or parsed.path not in {"", "/"}
                or parsed.query or parsed.fragment or parsed.username or parsed.password):
            raise ValueError("SUPABASE_URL must be an HTTPS origin.")
        if not isinstance(publishable_key, str) or not 16 <= len(publishable_key) <= 4096:
            raise ValueError("SUPABASE_PUBLISHABLE_KEY is invalid.")
        self.url = url.rstrip("/")
        self.key = publishable_key
        self.opener = opener
        self.timeout = timeout

    def _request(self, path, *, body=None, token=None):
        data = None if body is None else json.dumps(body, separators=(",", ":")).encode("utf-8")
        headers = {"apikey": self.key, "Accept": "application/json"}
        if data is not None:
            headers["Content-Type"] = "application/json"
        if token is not None:
            headers["Authorization"] = f"Bearer {token}"
        request = Request(self.url + path, data=data, headers=headers,
                          method="GET" if data is None else "POST")
        try:
            with self.opener(request, timeout=self.timeout) as response:
                raw = response.read(256_001)
                if len(raw) > 256_000:
                    raise AccessError("auth_unavailable")
                return json.loads(raw)
        except HTTPError as exc:
            if path == "/auth/v1/verify" and exc.code in {400, 401, 403, 422}:
                raise AccessError("invalid_code") from None
            raise AccessError("auth_unavailable") from None
        except (URLError, TimeoutError, OSError, UnicodeError, json.JSONDecodeError, ValueError):
            raise AccessError("auth_unavailable") from None

    def start(self, email):
        self._request("/auth/v1/otp", body={"email": email, "create_user": True})

    def verify(self, email, token):
        if not isinstance(token, str) or len(token) != 8 or not token.isascii() or not token.isdigit():
            raise AccessError("invalid_code")
        verified = self._request(
            "/auth/v1/verify", body={"email": email, "token": token, "type": "email"})
        access_token = verified.get("access_token") if isinstance(verified, dict) else None
        if not isinstance(access_token, str) or not access_token:
            raise AccessError("invalid_code")
        user = self._request("/auth/v1/user", token=access_token)
        try:
            user_id = str(uuid.UUID(user["id"]))
            returned_email = normalize_email(user["email"])
        except (KeyError, TypeError, ValueError, AccessError):
            raise AccessError("auth_unavailable") from None
        confirmed = user.get("email_confirmed_at") or user.get("confirmed_at")
        if (not isinstance(confirmed, str) or not confirmed
                or not hmac.compare_digest(returned_email.casefold(), email.casefold())):
            raise AccessError("invalid_code")
        return user_id


class AccountAccess:
    """Guest issuance, OTP flow, local sessions, and quota descriptions."""
    def __init__(self, path, *, enabled=False, secret=None, auth_client=None,
                 daily_limit=DEFAULT_ACCOUNT_DAILY_LIMIT):
        self.path = Path(path)
        self.enabled = enabled is True
        self.auth_client = auth_client
        if type(daily_limit) is not int or not 1 <= daily_limit <= MAX_ACCOUNT_DAILY_LIMIT:
            raise ValueError("Account daily limit is outside the supported range.")
        self.daily_limit = daily_limit
        if self.enabled:
            if not isinstance(secret, str) or len(secret.encode("utf-8")) < 32:
                raise ValueError("Public access requires a stable 32-byte HMAC secret.")
            self.secret = secret.encode("utf-8")
            self._initialize()
        else:
            self.secret = b""

    @classmethod
    def from_environ(cls, path, environ=None, *, auth_client=None):
        env = os.environ if environ is None else environ
        enabled = env.get("MEFORASH_PUBLIC_ACCESS") == "1"
        if not enabled:
            return cls(path)
        try:
            daily_limit = int(env.get("MEFORASH_ACCOUNT_DAILY_LIMIT", DEFAULT_ACCOUNT_DAILY_LIMIT))
        except ValueError:
            raise ValueError("MEFORASH_ACCOUNT_DAILY_LIMIT must be an integer.") from None
        email_enabled = env.get("MEFORASH_EMAIL_LOGIN_ENABLED") == "1"
        url, key = env.get("SUPABASE_URL"), env.get("SUPABASE_PUBLISHABLE_KEY")
        if email_enabled and (not url or not key):
            raise ValueError("Enabled email login requires Supabase URL and publishable key.")
        client = (auth_client or SupabaseAuthClient(url, key)) if email_enabled else None
        return cls(path, enabled=True, secret=env.get("MEFORASH_ACCESS_HMAC_SECRET"),
                   auth_client=client, daily_limit=daily_limit)

    def _connect(self):
        db = sqlite3.connect(self.path, timeout=5, isolation_level=None)
        db.execute("PRAGMA foreign_keys=ON")
        db.execute("PRAGMA journal_mode=DELETE")
        db.execute("PRAGMA synchronous=FULL")
        return db

    def _initialize(self):
        with closing(self._connect()) as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS guest_tokens(
                    token_hmac TEXT PRIMARY KEY, created_unix INTEGER NOT NULL,
                    expires_unix INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS account_sessions(
                    token_sha256 TEXT PRIMARY KEY, user_uuid TEXT NOT NULL,
                    created_unix INTEGER NOT NULL, expires_unix INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS auth_challenges(
                    token_sha256 TEXT PRIMARY KEY, email_hmac TEXT NOT NULL,
                    created_unix INTEGER NOT NULL, expires_unix INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS access_rate_events(
                    kind TEXT NOT NULL, key_hmac TEXT NOT NULL, created_unix INTEGER NOT NULL);
                CREATE INDEX IF NOT EXISTS access_rate_lookup
                    ON access_rate_events(kind,key_hmac,created_unix);
            """)
            db.execute("BEGIN IMMEDIATE")
            fingerprint = hashlib.sha256(
                b"meforash-access-hmac-v1\0" + self.secret).hexdigest()
            stored = db.execute(
                "SELECT value FROM metadata WHERE key='access_hmac_sha256'").fetchone()
            if stored is None:
                db.execute("INSERT INTO metadata(key,value) VALUES('access_hmac_sha256',?)",
                           (fingerprint,))
            elif not hmac.compare_digest(stored[0], fingerprint):
                db.execute("ROLLBACK")
                raise ValueError("The public-access HMAC secret changed for this ledger.")
            self._cleanup(db, int(time.time()))
            db.execute("COMMIT")

    def _hmac(self, namespace, value):
        return hmac.new(self.secret, f"{namespace}\0{value}".encode("utf-8"),
                        hashlib.sha256).hexdigest()

    def peer_hash(self, peer):
        return self._hmac("peer", validated_peer(peer))

    def email_hash(self, email):
        return self._hmac("email", normalize_email(email).casefold())

    def _cleanup(self, db, now):
        db.execute("DELETE FROM guest_tokens WHERE expires_unix<=?", (now,))
        db.execute("DELETE FROM account_sessions WHERE expires_unix<=?", (now,))
        db.execute("DELETE FROM auth_challenges WHERE expires_unix<=?", (now,))
        db.execute("DELETE FROM access_rate_events WHERE created_unix<?",
                   (now - RATE_RETENTION_SECONDS,))

    def _rate(self, db, kind, key, *, now, window, limit, minimum=0):
        latest = db.execute(
            "SELECT created_unix FROM access_rate_events WHERE kind=? AND key_hmac=? "
            "ORDER BY created_unix DESC LIMIT ?", (kind, key, limit)).fetchall()
        if (latest and now - latest[0][0] < minimum) or (
                len(latest) >= limit and now - latest[-1][0] < window):
            raise AccessError("rate_limited")
        db.execute("INSERT INTO access_rate_events VALUES(?,?,?)", (kind, key, now))

    def guest(self, cookie, peer, *, now=None):
        if not self.enabled:
            raise AccessError("not_found")
        now = int(time.time() if now is None else now)
        current = self.guest_identity(cookie, now=now)
        if current is not None:
            return current, None
        peer_hmac = self.peer_hash(peer)
        with closing(self._connect()) as db:
            db.execute("BEGIN IMMEDIATE")
            self._cleanup(db, now)
            self._rate(db, "guest_issue", peer_hmac, now=now, window=3600, limit=5,
                       minimum=2)
            count = db.execute("SELECT COUNT(*) FROM guest_tokens").fetchone()[0]
            if count >= MAX_IDENTITIES:
                db.execute("ROLLBACK")
                raise AccessError("rate_limited")
            token = secrets.token_urlsafe(32)
            digest = self._hmac("guest-token", token)
            db.execute("INSERT INTO guest_tokens VALUES(?,?,?)",
                       (digest, now, now + GUEST_COOKIE_SECONDS))
            db.execute("COMMIT")
        return AccessIdentity("guest", digest), token

    def guest_identity(self, token, *, now=None):
        if not self.enabled or not isinstance(token, str) or not 32 <= len(token) <= 128:
            return None
        now = int(time.time() if now is None else now)
        digest = self._hmac("guest-token", token)
        with closing(self._connect()) as db:
            row = db.execute("SELECT 1 FROM guest_tokens WHERE token_hmac=? AND expires_unix>?",
                             (digest, now)).fetchone()
        return AccessIdentity("guest", digest) if row else None

    def start(self, email, peer, *, now=None):
        if not self.enabled or self.auth_client is None:
            raise AccessError("auth_unavailable")
        email = normalize_email(email)
        now = int(time.time() if now is None else now)
        email_hmac, peer_hmac = self.email_hash(email), self.peer_hash(peer)
        pair_hmac = self._hmac("otp-pair", peer_hmac + email_hmac)
        challenge = secrets.token_urlsafe(32)
        challenge_sha = hashlib.sha256(challenge.encode()).hexdigest()
        with closing(self._connect()) as db:
            db.execute("BEGIN IMMEDIATE")
            self._cleanup(db, now)
            self._rate(db, "otp_start_peer", peer_hmac, now=now, window=3600, limit=8,
                       minimum=5)
            self._rate(db, "otp_start_email", email_hmac, now=now, window=3600, limit=4,
                       minimum=20)
            self._rate(db, "otp_start_pair", pair_hmac, now=now, window=3600, limit=3,
                       minimum=20)
            count = db.execute("SELECT COUNT(*) FROM auth_challenges").fetchone()[0]
            if count >= MAX_IDENTITIES:
                db.execute("ROLLBACK")
                raise AccessError("rate_limited")
            db.execute("INSERT INTO auth_challenges VALUES(?,?,?,?)",
                       (challenge_sha, email_hmac, now, now + CHALLENGE_SECONDS))
            db.execute("COMMIT")
        try:
            self.auth_client.start(email)
        except Exception as exc:
            with closing(self._connect()) as db:
                db.execute("DELETE FROM auth_challenges WHERE token_sha256=?",
                           (challenge_sha,))
            if isinstance(exc, AccessError):
                raise
            raise AccessError("auth_unavailable") from None
        return challenge

    def verify(self, email, token, challenge, peer, *, now=None):
        if not self.enabled or self.auth_client is None:
            raise AccessError("auth_unavailable")
        email = normalize_email(email)
        if not isinstance(challenge, str) or not 32 <= len(challenge) <= 128:
            raise AccessError("invalid_code")
        now = int(time.time() if now is None else now)
        email_hmac, peer_hmac = self.email_hash(email), self.peer_hash(peer)
        pair_hmac = self._hmac("verify-pair", peer_hmac + email_hmac)
        challenge_sha = hashlib.sha256(challenge.encode()).hexdigest()
        with closing(self._connect()) as db:
            db.execute("BEGIN IMMEDIATE")
            self._cleanup(db, now)
            self._rate(db, "otp_verify_peer", peer_hmac, now=now, window=3600, limit=30)
            self._rate(db, "otp_verify_email", email_hmac, now=now, window=3600, limit=15)
            self._rate(db, "otp_verify_pair", pair_hmac, now=now, window=3600, limit=10)
            row = db.execute(
                "SELECT email_hmac FROM auth_challenges WHERE token_sha256=? AND expires_unix>?",
                (challenge_sha, now)).fetchone()
            if row is None or not hmac.compare_digest(row[0], email_hmac):
                # Keep failed-verification rate events durable as well.
                db.execute("COMMIT")
                raise AccessError("invalid_code")
            db.execute("COMMIT")
        user_uuid = self.auth_client.verify(email, token)
        session = secrets.token_urlsafe(32)
        with closing(self._connect()) as db:
            db.execute("BEGIN IMMEDIATE")
            self._cleanup(db, now)
            deleted = db.execute(
                "DELETE FROM auth_challenges WHERE token_sha256=? AND email_hmac=?",
                (challenge_sha, email_hmac)).rowcount
            if deleted != 1:
                db.execute("ROLLBACK")
                raise AccessError("invalid_code")
            count = db.execute("SELECT COUNT(*) FROM account_sessions").fetchone()[0]
            if count >= MAX_IDENTITIES:
                db.execute("ROLLBACK")
                raise AccessError("auth_unavailable")
            db.execute("INSERT INTO account_sessions VALUES(?,?,?,?)", (
                hashlib.sha256(session.encode()).hexdigest(), user_uuid, now,
                now + ACCOUNT_SESSION_SECONDS))
            db.execute("COMMIT")
        return AccessIdentity("account", user_uuid), session

    def account_identity(self, token, *, now=None):
        if not self.enabled or not isinstance(token, str) or not 32 <= len(token) <= 128:
            return None
        now = int(time.time() if now is None else now)
        digest = hashlib.sha256(token.encode()).hexdigest()
        with closing(self._connect()) as db:
            db.execute("DELETE FROM account_sessions WHERE expires_unix<=?", (now,))
            row = db.execute("SELECT user_uuid FROM account_sessions WHERE token_sha256=? "
                             "AND expires_unix>?", (digest, now)).fetchone()
        return AccessIdentity("account", row[0]) if row else None

    def logout(self, token):
        if self.enabled and isinstance(token, str):
            with closing(self._connect()) as db:
                db.execute("DELETE FROM account_sessions WHERE token_sha256=?",
                           (hashlib.sha256(token.encode()).hexdigest(),))

    def access_description(self, identity, store, *, now=None):
        if identity.kind == "invite":
            return {"kind": "invite", "questions_remaining": None,
                    "daily_limit": self.daily_limit, "reset_at": None}
        remaining = store.questions_remaining(
            identity, GUEST_QUESTION_LIMIT if identity.kind == "guest" else self.daily_limit,
            day=None if identity.kind == "guest" else utc_day(now))
        return {"kind": identity.kind, "questions_remaining": remaining,
                "daily_limit": self.daily_limit,
                "reset_at": None if identity.kind == "guest" else next_utc_reset(now)}
