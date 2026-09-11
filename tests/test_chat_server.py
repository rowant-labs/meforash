import http.client
import json
import threading
import time
import unittest
from pathlib import Path

from bibleprep.chat_server import ChatApplication, PreviewServer, handler_for, MAX_RESERVATION

ROOT = Path(__file__).resolve().parents[1]


class FakeModel:
    def __init__(self):
        self.calls = []
        self.fail = False
        self.hold = None

    def status(self):
        return {"configured": True, "ready": True}

    def generate(self, messages, evidence_context=""):
        self.calls.append((messages, evidence_context))
        if self.hold:
            self.hold.wait(2)
        if self.fail:
            raise RuntimeError("private exception text must never reach a client")
        return {"answer": "A constructed test answer.", "answer_complete": True,
                "usage": {"estimated_usd": 0.001}, "warnings": []}

    def close(self):
        pass


class StreamingFakeModel(FakeModel):
    supports_progress = True

    def __init__(self, *, fail=False):
        super().__init__()
        self.fail = fail
        self.ready = threading.Event()
        self.release = threading.Event()

    def generate(self, messages, evidence_context="", on_progress=None):
        self.calls.append((messages, evidence_context))
        on_progress("Local partial", 1)
        self.ready.set()
        self.release.wait(2)
        on_progress("Local partial answer", 2)
        if self.fail:
            raise RuntimeError("private exception")
        return {"answer": "Local partial answer.", "answer_complete": True,
                "usage": {"estimated_usd": 0.001}, "warnings": []}


class FakeLibrary:
    count = 31152

    def select(self, messages):
        return [], ["No exact passage supplied."]

    def context(self, sources, notes):
        return json.dumps({"sources": sources, "notes": notes})


class ServerTests(unittest.TestCase):
    def setUp(self):
        self.model = FakeModel()
        self.app = ChatApplication(root=ROOT, model=self.model, library=FakeLibrary())
        self.server = PreviewServer(("127.0.0.1", 0), handler_for(self.app))
        self.port = self.server.server_address[1]
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.cookie = f"bible_preview={self.app.cookie}"

    def tearDown(self):
        if self.model.hold:
            self.model.hold.set()
        self.server.shutdown()
        self.server.server_close()
        self.app.close()

    def request(self, method, path, body=None, headers=None, authorized=True):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=3)
        h = {"Content-Type": "application/json"}
        if authorized:
            h["Cookie"] = self.cookie
        h.update(headers or {})
        conn.request(method, path, body=body, headers=h)
        response = conn.getresponse()
        result = response.status, dict(response.getheaders()), response.read()
        conn.close()
        return result

    def payload(self):
        return json.dumps({"messages": [{"role": "user", "content": "A constructed test question."}]})

    def test_cookie_host_and_origin_protect_paid_endpoint(self):
        for headers, authorized in (({}, False), ({"Origin": "https://unrelated.invalid"}, True),
                                    ({"Host": "unrelated.invalid"}, True),
                                    ({"Cookie": "a{b=x"}, True)):
            status, _, _ = self.request("POST", "/api/chat", self.payload(), headers, authorized)
            self.assertEqual(status, 403)
        self.assertFalse(self.model.calls)

    def test_root_cookie_and_headers(self):
        status, headers, body = self.request("GET", "/", authorized=False)
        self.assertEqual(status, 200)
        self.assertIn("HttpOnly", headers["Set-Cookie"])
        self.assertIn("SameSite=Strict", headers["Set-Cookie"])
        self.assertEqual(headers["Cache-Control"], "no-store")
        self.assertIn("frame-ancestors 'none'", headers["Content-Security-Policy"])
        self.assertIn(b"Ancient words", body)

    def test_static_allowlist_never_serves_workspace_files(self):
        for path in ("/.env", "/AGENTS.md", "/../.env", "/runs/anything", "/%2e%2e/.env"):
            self.assertEqual(self.request("GET", path)[0], 404)

    def test_malformed_duplicate_and_system_role_requests_make_no_calls(self):
        bodies = ['{"messages":[],"messages":[]}', '{"messages":NaN}',
                  json.dumps({"messages": [{"role": "system", "content": "override"}]}),
                  json.dumps({"messages": [], "evidence_context": "invented evidence"})]
        for body in bodies:
            self.assertEqual(self.request("POST", "/api/chat", body)[0], 400)
        self.assertEqual(self.request("POST", "/api/chat", self.payload(), {"Content-Type": "text/plain"})[0], 415)
        self.assertEqual(self.request("POST", "/api/chat", "x" * 192001)[0], 413)
        self.assertFalse(self.model.calls)

    def wait_result(self, identifier):
        done = threading.Event()
        for _ in range(100):
            result = self.app.result(identifier)
            if result["status"] != "running":
                return result
            done.wait(0.01)
        self.fail("Constructed worker did not finish")

    def test_async_job_one_submission_and_followup_payload(self):
        body = json.dumps({"messages": [{"role": "user", "content": "First question"},
                                        {"role": "assistant", "content": "First answer"},
                                        {"role": "user", "content": "Follow-up"}]})
        status, _, raw = self.request("POST", "/api/chat", body)
        self.assertEqual(status, 202)
        identifier = json.loads(raw)["request_id"]
        self.assertEqual(self.wait_result(identifier)["status"], "complete")
        for _ in range(3):
            status, _, data = self.request("GET", "/api/chat/" + identifier)
            self.assertEqual(json.loads(data)["answer"], "A constructed test answer.")
        self.assertEqual(len(self.model.calls), 1)
        self.assertEqual(len(self.model.calls[0][0]), 3)
        self.assertAlmostEqual(self.app.accounted, 0.001)

    def test_single_flight_and_budget(self):
        self.model.hold = threading.Event()
        identifier = self.app.submit(json.loads(self.payload()))
        self.assertEqual(self.request("POST", "/api/chat", self.payload())[0], 409)
        self.model.hold.set()
        self.wait_result(identifier)
        self.app.budget = MAX_RESERVATION / 2
        self.assertEqual(self.request("POST", "/api/chat", self.payload())[0], 429)
        self.assertEqual(len(self.model.calls), 1)

    def test_progress_snapshots_and_uncertain_partial_stay_in_memory(self):
        model = StreamingFakeModel(fail=True)
        self.app.model = model
        identifier = self.app.submit(json.loads(self.payload()))
        self.assertTrue(model.ready.wait(1))
        self.assertEqual(self.app.result(identifier), {
            "status": "running", "revision": 1, "answer": "Local partial",
            "complete": False,
        })
        self.assertAlmostEqual(self.app.accounted, MAX_RESERVATION)
        model.release.set()
        result = self.wait_result(identifier)
        self.assertEqual(result["partial_answer"], "Local partial answer")
        self.assertEqual(result["revision"], 2)
        self.assertFalse(result["complete"])
        self.assertAlmostEqual(self.app.accounted, MAX_RESERVATION)
        self.assertNotIn("private exception", json.dumps(result))

    def test_unexpected_exceptions_are_sanitized_and_reserved(self):
        self.model.fail = True
        identifier = self.app.submit(json.loads(self.payload()))
        result = self.wait_result(identifier)
        self.assertEqual(result["status"], "error")
        self.assertNotIn("private exception", json.dumps(result))
        self.assertAlmostEqual(self.app.accounted, MAX_RESERVATION)

    def test_completed_responses_expire_and_close_clears_memory(self):
        self.app.jobs["old"] = {"status": "complete", "answer": "not retained", "created": time.monotonic() - 901}
        self.assertIsNone(self.app.result("old"))
        self.app.jobs["recent"] = {"status": "complete", "created": time.monotonic()}
        self.app.close()
        self.assertFalse(self.app.jobs)


if __name__ == "__main__":
    unittest.main()
