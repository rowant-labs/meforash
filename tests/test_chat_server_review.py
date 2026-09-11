"""Independent fake-only regressions for preview worker lifecycle and accounting."""
import threading
import unittest
from unittest.mock import patch

from bibleprep.chat_model import ChatModelError
from bibleprep.chat_server import ChatApplication


class ControlledModel:
    def __init__(self):
        self.entered = threading.Event()
        self.release = threading.Event()
        self.calls = 0

    def status(self):
        return {"configured": True, "ready": True}

    def generate(self, messages, evidence_context=""):
        self.calls += 1
        self.entered.set()
        self.release.wait(2)
        return {"answer": "Private synthetic answer.", "answer_complete": True,
                "usage": {"estimated_usd": .001}, "warnings": []}

    def close(self):
        pass


class EmptyLibrary:
    count = 0

    def select(self, messages):
        return [], []

    def context(self, sources, notes):
        return ""


class ServerIndependentReviewTests(unittest.TestCase):
    def setUp(self):
        self.model = ControlledModel()
        self.app = ChatApplication(model=self.model, library=EmptyLibrary())
        self.body = {"messages": [{"role": "user", "content": "Synthetic question."}]}

    def tearDown(self):
        self.model.release.set()
        self.app.close()

    def test_completion_after_close_cannot_retain_an_answer_or_accept_another_job(self):
        self.app.submit(self.body)
        self.assertTrue(self.model.entered.wait(1))
        self.app.close()
        self.model.release.set()
        for _ in range(100):
            if not self.app.running:
                break
            threading.Event().wait(.01)
        self.assertFalse(self.app.running)
        self.assertEqual(self.app.jobs, {})
        with self.assertRaises(ChatModelError):
            self.app.submit(self.body)
        self.assertEqual(self.model.calls, 1)

    def test_thread_start_failure_refunds_known_unsubmitted_work_and_clears_busy(self):
        with patch("bibleprep.chat_server.threading.Thread.start", side_effect=RuntimeError("synthetic start failure")):
            with self.assertRaises(Exception):
                self.app.submit(self.body)
        self.assertFalse(self.app.running)
        self.assertEqual(self.app.accounted, 0)
        self.assertFalse(any(job["status"] == "running" for job in self.app.jobs.values()))
        self.assertEqual(self.model.calls, 0)


if __name__ == "__main__":
    unittest.main()
