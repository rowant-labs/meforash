"""Real-HTTP and coordinator tests for beta job event streams."""
from collections import deque
import http.client
import json
from pathlib import Path
import socket
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from bibleprep import beta_server as subject
from tests.test_beta_server import FakeLibrary, FakeModel, SECRET, invite_config, messages


SECOND_SECRET = "another-correct-horse-battery-staple-secret"


def unused_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class UnicodeStreamingModel(FakeModel):
    supports_progress = True

    def __init__(self, gate):
        super().__init__()
        self.gate = gate
        self.progress_ready = threading.Event()

    def generate(self, payload, evidence_context="", on_progress=None):
        self.calls.append((payload, evidence_context))
        on_progress("λόγος ו", 1)
        self.progress_ready.set()
        self.gate.wait(2)
        on_progress("λόγος ושלום", 2)
        return {"answer": "λόγος ושלום — complete", "answer_complete": True,
                "warnings": [], "usage": {"estimated_usd": .01}}


class EventStreamHTTPTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        config = invite_config()
        config["invites"].append(subject.make_invite_record(
            "reader-two", SECOND_SECRET, 5 * subject.MAX_RESERVATION_NANO,
            salt_hex="22" * 16))
        self.store = subject.BetaStore(Path(self.temp.name) / "sse.sqlite3", config)
        self.gate = threading.Event()
        self.addCleanup(self.gate.set)
        self.model = UnicodeStreamingModel(self.gate)
        self.app = subject.BetaApplication(
            store=self.store, model_factory=lambda: self.model,
            library=FakeLibrary(), streaming=True)
        self.port = unused_port()
        self.origin = f"http://127.0.0.1:{self.port}"
        self.server = subject.BetaHTTPServer(
            ("127.0.0.1", self.port), subject.handler_for(
                self.app, origin=self.origin, secure_cookie=False))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.stop)

    def stop(self):
        self.gate.set()
        self.server.shutdown()
        self.server.server_close()
        self.app.close()
        self.thread.join(2)

    def request(self, method, path, body=None, *, cookie=None, origin=None):
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=2)
        raw = json.dumps(body).encode("utf-8") if body is not None else None
        headers = {"Host": f"127.0.0.1:{self.port}"}
        if body is not None:
            headers.update({"Content-Type": "application/json",
                            "Content-Length": str(len(raw))})
        if cookie:
            headers["Cookie"] = cookie
        if origin is not None:
            headers["Origin"] = origin
        connection.request(method, path, body=raw, headers=headers)
        response = connection.getresponse()
        value = json.loads(response.read())
        status, response_headers = response.status, dict(response.getheaders())
        connection.close()
        return status, value, response_headers

    def login(self, invite_id="reader-one", secret=SECRET):
        status, _, headers = self.request(
            "POST", "/api/login",
            {"invite_id": invite_id, "invite_secret": secret}, origin=self.origin)
        self.assertEqual(status, 200)
        cookie = headers["Set-Cookie"].split(";", 1)[0]
        status, _, _ = self.request(
            "POST", "/api/accept-terms",
            {"terms_version": subject.TERMS_VERSION, "adult": True},
            cookie=cookie, origin=self.origin)
        self.assertEqual(status, 200)
        return cookie

    def submit(self, cookie):
        status, value, _ = self.request(
            "POST", "/api/chat", messages(), cookie=cookie, origin=self.origin)
        self.assertEqual(status, 202)
        return value["request_id"]

    def open_events(self, cookie, request_id, *, origin=None):
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=2)
        raw = b"{}"
        connection.request(
            "POST", f"/api/chat/{request_id}/events", body=raw,
            headers={"Host": f"127.0.0.1:{self.port}",
                     "Origin": self.origin if origin is None else origin,
                     "Cookie": cookie, "Content-Type": "application/json",
                     "Content-Length": str(len(raw)), "Accept": "text/event-stream"})
        return connection, connection.getresponse()

    def read_event(self, response):
        data = []
        while True:
            line = response.readline()
            if not line:
                return None
            line = line.rstrip(b"\r\n")
            if not line:
                if data:
                    return json.loads(b"\n".join(data).decode("utf-8"))
                continue
            if line.startswith(b"data:"):
                data.append(line[5:].lstrip(b" "))

    def test_real_http_stream_delivers_unicode_progress_and_terminal(self):
        cookie = self.login()
        request_id = self.submit(cookie)
        self.assertTrue(self.model.progress_ready.wait(1))
        connection, response = self.open_events(cookie, request_id)
        self.addCleanup(connection.close)
        self.assertEqual(response.status, 200)
        self.assertEqual(response.getheader("Content-Type"),
                         "text/event-stream; charset=utf-8")
        self.assertEqual(response.getheader("X-Accel-Buffering"), "no")

        first = self.read_event(response)
        self.assertEqual((first["status"], first["revision"], first["answer"]),
                         ("running", 1, "λόγος ו"))
        self.gate.set()
        received = [first]
        while received[-1]["status"] != "complete" and len(received) < 5:
            received.append(self.read_event(response))
        self.assertEqual(received[-1]["answer"], "λόγος ושלום — complete")
        self.assertTrue(received[-1]["complete"])
        self.assertNotIn("identity", json.dumps(received, ensure_ascii=False))

    def test_origin_auth_and_job_ownership_are_checked_before_stream_headers(self):
        owner_cookie = self.login()
        other_cookie = self.login("reader-two", SECOND_SECRET)
        request_id = self.submit(owner_cookie)
        self.assertTrue(self.model.progress_ready.wait(1))

        wrong_origin, value, headers = self.request(
            "POST", f"/api/chat/{request_id}/events", {}, cookie=owner_cookie,
            origin="http://wrong.invalid")
        self.assertEqual((wrong_origin, value["error"]["code"]),
                         (403, "origin_rejected"))
        self.assertNotIn("text/event-stream", headers.get("Content-Type", ""))

        connection, response = self.open_events(other_cookie, request_id)
        value = json.loads(response.read())
        connection.close()
        self.assertEqual((response.status, value["error"]["code"]), (404, "not_found"))
        self.assertNotIn("text/event-stream", response.getheader("Content-Type", ""))

    def test_session_revocation_stops_stream_before_later_progress(self):
        cookie = self.login()
        request_id = self.submit(cookie)
        self.assertTrue(self.model.progress_ready.wait(1))
        connection, response = self.open_events(cookie, request_id)
        self.addCleanup(connection.close)
        first = self.read_event(response)
        self.assertEqual(first["answer"], "λόγος ו")

        token = cookie.split("=", 1)[1]
        self.store.delete_session(token)
        self.gate.set()
        self.assertEqual(response.readline(), b"")

    def test_idle_stream_emits_heartbeat_and_releases_terminal_connection(self):
        cookie = self.login()
        request_id = self.submit(cookie)
        self.assertTrue(self.model.progress_ready.wait(1))
        with patch.object(subject, "SSE_HEARTBEAT_SECONDS", .05):
            connection, response = self.open_events(cookie, request_id)
            self.addCleanup(connection.close)
            self.assertEqual(self.read_event(response)["status"], "running")
            self.assertEqual(response.readline(), b": keep-alive\n")
            self.assertEqual(response.readline(), b"\n")
            self.gate.set()
            terminal = None
            while terminal is None or terminal["status"] != "complete":
                terminal = self.read_event(response)
        deadline = time.monotonic() + 1
        while self.app.event_streams:
            self.assertLess(time.monotonic(), deadline)
            time.sleep(.005)
        self.assertEqual(self.app.event_streams_by_job, {})


class EventStreamLimitTests(unittest.TestCase):
    def test_global_and_per_job_limits_release_on_disconnect_cleanup(self):
        with tempfile.TemporaryDirectory() as directory:
            store = subject.BetaStore(Path(directory) / "limits.sqlite3", invite_config())
            pool = subject.BetaApplication(
                store=store, model_factory=FakeModel, library=FakeLibrary())
            self.addCleanup(pool.close)
            identities = [subject.AccessIdentity("account", f"stream-{index}")
                          for index in range(3)]
            requests = []
            for index, identity in enumerate(identities):
                pool.access.accept_terms(
                    identity, subject.TERMS_VERSION, True, now=100)
                request_id = pool.submit(identity, messages(str(index)))
                deadline = time.monotonic() + 1
                while pool.result(identity, request_id)["status"] != "complete":
                    self.assertLess(time.monotonic(), deadline)
                    time.sleep(.005)
                requests.append(request_id)

            with patch.object(subject, "MAX_EVENT_STREAMS", 2):
                self.assertIsNotNone(pool.open_event_stream(identities[0], requests[0]))
                self.assertIsNotNone(pool.open_event_stream(identities[1], requests[1]))
                with self.assertRaisesRegex(subject.BetaError, "stream_limit"):
                    pool.open_event_stream(identities[2], requests[2])
                pool.close_event_stream(identities[0], requests[0])
                self.assertIsNotNone(pool.open_event_stream(identities[2], requests[2]))
                pool.close_event_stream(identities[1], requests[1])
                pool.close_event_stream(identities[2], requests[2])

            self.assertEqual(pool.event_streams, 0)
            self.assertEqual(pool.event_streams_by_identity, {})
            self.assertEqual(pool.event_streams_by_job, {})


if __name__ == "__main__":
    unittest.main()
