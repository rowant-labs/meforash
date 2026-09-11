import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock

from bibleprep import chat_model as chat
from bibleprep import chat_streaming as streaming


SYNTHETIC_SAMPLER = "tinker://synthetic-test/sampler_weights/only-b"


def safe_result(answer="Done."):
    return {
        "answer": answer, "answer_complete": True, "native_turn_complete": True,
        "finish_reason": "stop", "partial": False,
        "usage": {"input_tokens": 10, "output_tokens": 20, "estimated_usd": .0001123,
                  "is_invoice": False, "price_snapshot_date": "2026-09-06"},
        "warnings": [],
    }


class FakeNative:
    @staticmethod
    def encode_ordinary(text):
        return list(text.encode("utf-8"))


class FakeProfile:
    native = FakeNative()

    def __init__(self, input_tokens=10):
        self.input_tokens = input_tokens
        self.calls = []

    def render(self, payload, config):
        self.calls.append((payload, config))
        return list(range(self.input_tokens)), object()


class FakeResponse:
    def __init__(self, lines, status_code=200):
        self.lines = lines
        self.status_code = status_code

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def iter_lines(self):
        yield from self.lines


class FakeStreamFactory:
    def __init__(self, lines, status_code=200):
        self.lines = lines
        self.status_code = status_code
        self.calls = []

    def __call__(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        return FakeResponse(self.lines, self.status_code)


def event(value):
    return "data: " + json.dumps(value)


def config(**changes):
    value = {
        "model": chat.MODEL, "adapter_sampler_path": SYNTHETIC_SAMPLER,
        "max_input_tokens": 24000, "max_output_tokens": 8192,
        "timeout_seconds": 300, "seed": 20260905,
        "reasoning_effort": "medium", "thinking_effort_numeric": 0.7,
        "temperature": 0.0,
    }
    value.update(changes)
    return value


def payload():
    return chat.build_payload([{"role": "user", "content": "Synthetic question"}])


class CompatibleSessionTests(unittest.TestCase):
    def test_structured_content_only_progress_and_usage_accounting(self):
        lines = [
            "event: chat.completion.chunk",
            "id: opaque-ignored-event-id",
            "retry: 1000",
            event({"choices": [{"index": 0, "delta": {
                "role": "assistant", "content": None,
                "reasoning_content": "PRIVATE synthetic reasoning", "tool_calls": None,
                "refusal": None}}]}),
            event({"id": "private-provider-id", "choices": [{"index": 0,
                "delta": {"content": "Visible ", "tool_calls": [], "refusal": None},
                "finish_reason": None}]}),
            event({"choices": [{"index": 0, "delta": {
                "reasoning_content": "PRIVATE more reasoning", "content": "answer."},
                "finish_reason": "stop"}]}),
            event({"choices": [], "usage": {
                "prompt_tokens": 10, "completion_tokens": 30, "total_tokens": 40,
                "prompt_tokens_details": {"cached_tokens": 0}}}),
            "data: [DONE]",
        ]
        factory = FakeStreamFactory(lines)
        ticks = iter([0.0, 0.3])
        session = streaming.CompatibleChatStreamingSession(
            profile=FakeProfile(), stream_factory=factory, clock=lambda: next(ticks))
        updates = []

        result = session(payload(), config(), "synthetic-secret", updates.append)

        self.assertEqual(updates, ["Visible ", "Visible answer."])
        self.assertEqual(result["answer"], "Visible answer.")
        self.assertEqual(result["usage"]["input_tokens"], 10)
        # This is provider total completion usage, including discarded reasoning.
        self.assertEqual(result["usage"]["output_tokens"], 30)
        self.assertTrue(result["answer_complete"])
        self.assertNotIn("PRIVATE", json.dumps(updates) + json.dumps(result))
        self.assertNotIn("private-provider-id", json.dumps(updates) + json.dumps(result))
        self.assertNotIn("synthetic-secret", json.dumps(updates) + json.dumps(result))
        self.assertEqual(len(factory.calls), 1)
        _, request = factory.calls[0]
        body = request["json"]
        self.assertEqual(body["model"], SYNTHETIC_SAMPLER)
        self.assertEqual(body["stream_options"], {"include_usage": True})
        self.assertEqual(body["reasoning_effort"], "medium")
        self.assertEqual(body["temperature"], 0.0)
        self.assertEqual(body["seed"], 20260905)
        self.assertTrue(body["separate_reasoning"])
        self.assertEqual(body["max_tokens"], 8192)

    def test_output_limit_preserves_typed_partial_with_total_completion_cost(self):
        lines = [
            event({"choices": [{"delta": {"content": "Partial"},
                                "finish_reason": "length"}]}),
            event({"choices": [], "usage": {
                "prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30}}),
            "data: [DONE]",
        ]
        session = streaming.CompatibleChatStreamingSession(
            profile=FakeProfile(), stream_factory=FakeStreamFactory(lines))
        result = session(payload(), config(), "secret", lambda value: None)
        self.assertEqual(result["answer"], "Partial")
        self.assertFalse(result["answer_complete"])
        self.assertEqual(result["finish_reason"], "length")
        self.assertEqual(result["warnings"], ["output_limit", "incomplete_answer"])
        self.assertEqual(result["usage"]["output_tokens"], 20)

    def test_missing_or_inconsistent_usage_is_uncertain_and_never_resubmitted(self):
        cases = [
            [event({"choices": [{"delta": {"content": "Answer"},
                                  "finish_reason": "stop"}]}), "data: [DONE]"],
            [event({"choices": [{"delta": {"content": "Answer"},
                                  "finish_reason": "stop"}]}),
             event({"choices": [], "usage": {
                 "prompt_tokens": 9, "completion_tokens": 20, "total_tokens": 29}}),
             "data: [DONE]"],
            [event({"choices": [{"delta": {"content": "Answer"},
                                  "finish_reason": "stop"}]}),
             event({"choices": [], "usage": {
                 "prompt_tokens": 10, "completion_tokens": 2, "total_tokens": 12}}),
             "data: [DONE]"],
        ]
        for lines in cases:
            with self.subTest(lines=lines):
                factory = FakeStreamFactory(lines)
                session = streaming.CompatibleChatStreamingSession(
                    profile=FakeProfile(), stream_factory=factory)
                with self.assertRaises(Exception):
                    session(payload(), config(), "secret", lambda value: None)
                self.assertEqual(len(factory.calls), 1)

    def test_local_input_cap_and_settings_fail_before_http(self):
        factory = FakeStreamFactory([])
        session = streaming.CompatibleChatStreamingSession(
            profile=FakeProfile(input_tokens=11), stream_factory=factory)
        with self.assertRaises(chat.ChatModelError) as raised:
            session(payload(), config(max_input_tokens=10), "secret", lambda value: None)
        self.assertEqual(raised.exception.code, "input_too_long")
        with self.assertRaises(chat.ChatModelError) as raised:
            session(payload(), config(reasoning_effort="high"), "secret", lambda value: None)
        self.assertEqual(raised.exception.code, "runtime_unavailable")
        self.assertEqual(factory.calls, [])

    def test_unsupported_delta_is_not_exposed(self):
        for delta in [
            {"content": "Safe", "tool_calls": [{"private": "value"}]},
            {"role": "user", "content": "Unsafe role"},
            {"content": "Refused", "refusal": "private refusal"},
        ]:
            with self.subTest(delta=delta):
                lines = [event({"choices": [{"delta": delta}]})]
                updates = []
                session = streaming.CompatibleChatStreamingSession(
                    profile=FakeProfile(), stream_factory=FakeStreamFactory(lines))
                with self.assertRaises(Exception):
                    session(payload(), config(), "secret", updates.append)
                self.assertEqual(updates, [])


class FakeProcess:
    def __init__(self):
        self.terminated = False

    def is_alive(self):
        return not self.terminated

    def terminate(self):
        self.terminated = True

    def join(self, timeout=None):
        pass

    def kill(self):
        self.terminated = True


class FakeConnection:
    def __init__(self, replies):
        self.replies = list(replies)
        self.sent = []
        self.closed = False

    def send(self, value):
        self.sent.append(value)

    def poll(self, timeout):
        return bool(self.replies)

    def recv(self):
        return self.replies.pop(0)

    def close(self):
        self.closed = True


class BoundedTransportTests(unittest.TestCase):
    def transport(self, replies):
        transport = streaming.BoundedStreamingTransport()
        transport.process = FakeProcess()
        transport.connection = FakeConnection(replies)
        return transport

    def test_callback_failure_does_not_cancel_duplicate_or_corrupt_terminal(self):
        result = safe_result("First second")
        transport = self.transport([
            {"kind": "progress", "revision": 1, "answer": "First"},
            {"kind": "progress", "revision": 2, "answer": "First second"},
            {"kind": "complete", "revision": 2, "response": result},
        ])
        connection = transport.connection
        callback = MagicMock(side_effect=RuntimeError("browser callback failed"))
        returned = transport(payload(), config(), "secret", on_progress=callback)
        self.assertEqual(returned, result)
        self.assertEqual(callback.call_count, 1)
        self.assertEqual(len(connection.sent), 1)
        self.assertFalse(transport.failed)

    def test_nonmonotonic_progress_or_mismatched_terminal_blocks_transport(self):
        cases = [
            [{"kind": "progress", "revision": 1, "answer": "First"},
             {"kind": "progress", "revision": 2, "answer": "Other"}],
            [{"kind": "progress", "revision": 1, "answer": "First"},
             {"kind": "complete", "revision": 1, "response": safe_result("Different")}],
            [{"kind": "progress", "revision": 1, "answer": "First", "extra": "private"}],
        ]
        for replies in cases:
            with self.subTest(replies=replies):
                transport = self.transport(replies)
                connection = transport.connection
                with self.assertRaises(Exception):
                    transport(payload(), config(), "secret")
                self.assertTrue(transport.failed)
                self.assertTrue(connection.closed)
                self.assertEqual(len(connection.sent), 1)
                with self.assertRaises(Exception):
                    transport(payload(), config(), "secret")
                self.assertEqual(len(connection.sent), 1)

    def test_deadline_closes_worker_and_cannot_resubmit(self):
        transport = self.transport([])
        connection = transport.connection
        with self.assertRaises(TimeoutError):
            transport(payload(), config(timeout_seconds=1), "secret")
        self.assertTrue(transport.failed)
        self.assertTrue(connection.closed)
        self.assertEqual(len(connection.sent), 1)
        with self.assertRaises(Exception):
            transport(payload(), config(timeout_seconds=1), "secret")
        self.assertEqual(len(connection.sent), 1)


class ChatModelStreamingInterfaceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.messages = [{"role": "user", "content": "Question"}]
        self.common = {
            "credential_loader": lambda root: "secret",
            "checkpoint_resolver": lambda root, path: SYNTHETIC_SAMPLER,
        }

    def test_default_native_interface_remains_nonprogressive(self):
        transport = MagicMock(return_value=safe_result())
        model = chat.ChatModel(self.root, transport=transport, **self.common)
        self.addCleanup(model.close)
        callback = MagicMock()
        result = model.generate(self.messages, on_progress=callback)
        self.assertFalse(model.supports_progress)
        self.assertEqual(result["answer"], "Done.")
        callback.assert_not_called()
        self.assertEqual(len(transport.call_args.args), 3)

    def test_explicit_streaming_passes_nonthrowing_callback(self):
        def invoke(payload, config, secret, on_progress=None):
            on_progress("One", 1)
            on_progress("One two", 2)
            return safe_result("One two")

        transport = MagicMock(side_effect=invoke)
        model = chat.ChatModel(
            self.root, transport=transport, streaming=True, **self.common)
        self.addCleanup(model.close)
        updates = []
        result = model.generate(self.messages, on_progress=lambda answer, revision: updates.append(
            (answer, revision)))
        self.assertTrue(model.supports_progress)
        self.assertEqual(updates, [("One", 1), ("One two", 2)])
        self.assertEqual(result["answer"], "One two")
        self.assertEqual(transport.call_count, 1)

    def test_streaming_transport_failure_blocks_without_fallback(self):
        transport = MagicMock(side_effect=RuntimeError("private provider failure body"))
        model = chat.ChatModel(
            self.root, transport=transport, streaming=True, **self.common)
        self.addCleanup(model.close)
        with self.assertRaises(chat.ChatModelError) as raised:
            model.generate(self.messages)
        self.assertEqual(raised.exception.code, "provider_error")
        self.assertNotIn("private provider", str(raised.exception))
        with self.assertRaises(chat.ChatModelError) as raised:
            model.generate(self.messages)
        self.assertEqual(raised.exception.code, "blocked")
        self.assertEqual(transport.call_count, 1)


if __name__ == "__main__":
    unittest.main()
