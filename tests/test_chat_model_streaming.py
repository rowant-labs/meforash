import json
from pathlib import Path
import queue
import tempfile
import threading
import unittest
from unittest.mock import MagicMock, patch

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
    def test_concurrent_session_initializes_one_shared_native_profile(self):
        lines = [
            event({"choices": [{"delta": {"content": "Done"},
                                  "finish_reason": "stop"}]}),
            event({"choices": [], "usage": {
                "prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30}}),
            "data: [DONE]",
        ]
        created = []

        class Profile(FakeProfile):
            def __init__(self):
                super().__init__()
                created.append(self)

        session = streaming.CompatibleChatStreamingSession(
            stream_factory=FakeStreamFactory(lines), profile_lock=threading.Lock())
        rendezvous = threading.Barrier(3)
        results = []

        def run():
            rendezvous.wait(1)
            results.append(session(payload(), config(), "secret", lambda value: None))

        workers = [threading.Thread(target=run) for _ in range(2)]
        with patch.object(chat, "ChatNativeProfile", Profile):
            for worker in workers:
                worker.start()
            rendezvous.wait(1)
            for worker in workers:
                worker.join(2)
        self.assertEqual(len(results), 2)
        self.assertEqual(len(created), 1)
        self.assertEqual(len(created[0].calls), 2)

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

    def test_absolute_deadline_stops_stream_kept_alive_by_reasoning_events(self):
        lines = [event({"choices": [{"delta": {
            "reasoning_content": f"PRIVATE heartbeat {index}"}}]})
                 for index in range(3)]
        factory = FakeStreamFactory(lines)
        updates = []
        session = streaming.CompatibleChatStreamingSession(
            profile=FakeProfile(), stream_factory=factory)
        with patch.object(streaming.time, "monotonic",
                          side_effect=[0.0, 0.4, 0.8, 1.0]):
            with self.assertRaises(TimeoutError):
                session(payload(), config(), "secret", updates.append, deadline=1.0)
        self.assertEqual(updates, [])
        self.assertEqual(len(factory.calls), 1)
        self.assertEqual(factory.calls[0][1]["timeout"], 1.0)

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


class FakeBroker:
    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = []
        self.abandoned = []
        self.close_calls = 0

    def healthy(self):
        return True

    def open_request(self, payload, config, secret, *, deadline):
        request_id = "synthetic-request-id"
        self.calls.append((payload, config, secret))
        destination = queue.Queue()
        for reply in self.replies:
            destination.put({"request_id": request_id, **reply})
        return request_id, destination

    def abandon(self, request_id):
        self.abandoned.append(request_id)

    def close(self):
        self.close_calls += 1


class BoundedTransportTests(unittest.TestCase):
    def transport(self, replies):
        broker = FakeBroker(replies)
        return streaming.BoundedStreamingTransport(broker=broker), broker

    def test_callback_failure_does_not_cancel_duplicate_or_corrupt_terminal(self):
        result = safe_result("First second")
        transport, broker = self.transport([
            {"kind": "progress", "revision": 1, "answer": "First"},
            {"kind": "progress", "revision": 2, "answer": "First second"},
            {"kind": "complete", "revision": 2, "response": result},
        ])
        callback = MagicMock(side_effect=RuntimeError("browser callback failed"))
        returned = transport(payload(), config(), "secret", on_progress=callback)
        self.assertEqual(returned, result)
        self.assertEqual(callback.call_count, 1)
        self.assertEqual(len(broker.calls), 1)
        self.assertFalse(transport.failed)

    def test_nonmonotonic_progress_or_mismatched_terminal_blocks_transport(self):
        cases = [
            [{"kind": "progress", "revision": 1, "answer": "First"},
             {"kind": "progress", "revision": 2, "answer": "Other"}],
            [{"kind": "progress", "revision": 1, "answer": "First"},
             {"kind": "complete", "revision": 1, "response": safe_result("Different")}],
            [{"kind": "progress", "revision": 1, "answer": "First", "extra": "private"}],
            [{"request_id": "mismatched-request-id", "kind": "progress",
              "revision": 1, "answer": "First"}],
        ]
        for replies in cases:
            with self.subTest(replies=replies):
                transport, broker = self.transport(replies)
                with self.assertRaises(Exception):
                    transport(payload(), config(), "secret")
                self.assertTrue(transport.failed)
                self.assertTrue(transport.closed)
                self.assertEqual(len(broker.calls), 1)
                with self.assertRaises(Exception):
                    transport(payload(), config(), "secret")
                self.assertEqual(len(broker.calls), 1)

    def test_deadline_closes_worker_and_cannot_resubmit(self):
        transport, broker = self.transport([])
        with self.assertRaises(TimeoutError):
            transport(payload(), config(timeout_seconds=1), "secret")
        self.assertTrue(transport.failed)
        self.assertTrue(transport.closed)
        self.assertEqual(len(broker.calls), 1)
        self.assertEqual(broker.abandoned, ["synthetic-request-id"])
        with self.assertRaises(Exception):
            transport(payload(), config(timeout_seconds=1), "secret")
        self.assertEqual(len(broker.calls), 1)

    def test_default_transports_share_one_ref_counted_broker(self):
        result = safe_result()
        broker = FakeBroker([
            {"kind": "progress", "revision": 1, "answer": "Done."},
            {"kind": "complete", "revision": 1, "response": result},
        ])
        with patch.object(streaming, "_SHARED_BROKER", broker), \
                patch.object(streaming, "_SHARED_REFS", 0), \
                patch.object(streaming, "_SHARED_POISONED", False):
            first = streaming.BoundedStreamingTransport()
            second = streaming.BoundedStreamingTransport()
            self.assertEqual(first(payload(), config(), "one"), result)
            self.assertEqual(second(payload(), config(), "two"), result)
            self.assertIs(first.broker, second.broker)
            first.close()
            self.assertEqual(broker.close_calls, 0)
            second.close()
            self.assertEqual(broker.close_calls, 1)


class FakeAliveProcess:
    def __init__(self):
        self.alive = True

    def is_alive(self):
        return self.alive

    def join(self, timeout=None):
        pass

    def terminate(self):
        self.alive = False

    def kill(self):
        self.alive = False


class DuplexConnection:
    def __init__(self):
        self.incoming = queue.Queue()
        self.sent = []
        self.closed = False

    def recv(self):
        value = self.incoming.get(timeout=2)
        if isinstance(value, BaseException):
            raise value
        return value

    def send(self, value):
        if value is None:
            self.incoming.put(EOFError())
            return
        self.sent.append(value)

    def close(self):
        self.closed = True


class SharedBrokerTests(unittest.TestCase):
    def broker(self, limit=2):
        broker = streaming.SharedStreamingBroker(max_requests=limit)
        broker.process = FakeAliveProcess()
        broker.connection = DuplexConnection()
        broker.reader = threading.Thread(target=broker._read_replies, daemon=True)
        broker.reader.start()
        self.addCleanup(broker.close)
        return broker

    def test_correlated_out_of_order_and_abandoned_terminal_are_isolated(self):
        broker = self.broker()
        deadline = streaming.time.monotonic() + 10
        first_id, first = broker.open_request(
            payload(), config(), "secret-one", deadline=deadline)
        second_id, second = broker.open_request(
            payload(), config(), "secret-two", deadline=deadline)
        broker.abandon(first_id)
        broker.connection.incoming.put(
            {"request_id": second_id, "kind": "progress", "revision": 1,
             "answer": "Second"})
        broker.connection.incoming.put(
            {"request_id": first_id, "kind": "uncertain"})
        broker.connection.incoming.put(
            {"request_id": second_id, "kind": "complete", "revision": 1,
             "response": safe_result("Second")})
        self.assertEqual(second.get(timeout=1)["answer"], "Second")
        self.assertEqual(second.get(timeout=1)["response"]["answer"], "Second")
        self.assertTrue(first.empty())
        self.assertTrue(broker.healthy())

    def test_abandoned_request_keeps_capacity_until_terminal(self):
        broker = self.broker(limit=1)
        deadline = streaming.time.monotonic() + 10
        request_id, _ = broker.open_request(
            payload(), config(), "secret", deadline=deadline)
        broker.abandon(request_id)
        with self.assertRaisesRegex(RuntimeError, "capacity"):
            broker.open_request(payload(), config(), "other", deadline=deadline)
        broker.connection.incoming.put({"request_id": request_id, "kind": "uncertain"})
        for _ in range(100):
            with broker.lock:
                if request_id not in broker.inflight:
                    break
            threading.Event().wait(.005)
        else:
            self.fail("terminal envelope did not release broker capacity")
        next_id, _ = broker.open_request(
            payload(), config(), "other", deadline=deadline)
        self.assertNotEqual(next_id, request_id)

    def test_broker_death_wakes_waiters_and_fails_health(self):
        broker = self.broker()
        process = broker.process
        connection = broker.connection
        _, destination = broker.open_request(
            payload(), config(), "secret", deadline=streaming.time.monotonic() + 10)
        broker.connection.incoming.put(EOFError())
        self.assertEqual(destination.get(timeout=1), {"kind": "broker_failed"})
        self.assertFalse(broker.healthy())
        broker.close()
        self.assertFalse(process.is_alive())
        self.assertTrue(connection.closed)

    def test_slow_consumer_reply_mailbox_is_bounded_and_fails_only_that_call(self):
        destination = queue.Queue(maxsize=2)
        destination.put({"kind": "progress", "answer": "one"})
        destination.put({"kind": "progress", "answer": "two"})
        streaming.SharedStreamingBroker._signal(
            destination, {"kind": "progress", "answer": "three"})
        self.assertEqual(destination.qsize(), 1)
        self.assertEqual(destination.get_nowait(), {"kind": "broker_failed"})


class WorkerMultiplexingTests(unittest.TestCase):
    def test_one_session_handles_parallel_failure_without_stopping_peer(self):
        connection = DuplexConnection()
        entered = threading.Barrier(3)
        release = threading.Event()
        constructed = []

        class Session:
            def __init__(self, **options):
                constructed.append(options["profile_lock"])

            def __call__(self, request_payload, request_config, secret, publish, *, deadline):
                entered.wait(2)
                release.wait(2)
                if secret == "fail":
                    raise RuntimeError("private failure")
                publish("Safe")
                return safe_result("Safe")

        worker = threading.Thread(target=streaming.concurrent_streaming_chat_worker,
                                  args=(connection, 2), daemon=True)
        with patch.object(streaming, "CompatibleChatStreamingSession", Session):
            worker.start()
            connection.incoming.put({"request_id": "request-one-0001", "payload": payload(),
                                     "config": config(), "secret": "fail",
                                     "deadline": streaming.time.monotonic() + 10})
            connection.incoming.put({"request_id": "request-two-0002", "payload": payload(),
                                     "config": config(), "secret": "pass",
                                     "deadline": streaming.time.monotonic() + 10})
            entered.wait(2)
            release.set()
            for _ in range(100):
                terminals = [item for item in connection.sent
                             if item.get("kind") in {"complete", "uncertain"}]
                if len(terminals) == 2:
                    break
                threading.Event().wait(.005)
            connection.incoming.put(None)
            worker.join(1)
        self.assertEqual(len(constructed), 1)
        by_id = {item["request_id"]: item for item in terminals}
        self.assertEqual(by_id["request-one-0001"]["kind"], "uncertain")
        self.assertEqual(by_id["request-two-0002"]["kind"], "complete")
        self.assertEqual(
            [item["answer"] for item in connection.sent
             if item.get("kind") == "progress"], ["Safe"])

    def test_terminal_receipt_means_child_capacity_is_available(self):
        class TerminalGateConnection(DuplexConnection):
            def __init__(self):
                super().__init__()
                self.first_terminal = threading.Event()
                self.release_terminal = threading.Event()
                self.held = False

            def send(self, value):
                if (isinstance(value, dict) and value.get("kind") == "complete"
                        and not self.held):
                    self.held = True
                    self.first_terminal.set()
                    self.release_terminal.wait(2)
                super().send(value)

        connection = TerminalGateConnection()
        second_started = threading.Event()
        call_lock = threading.Lock()
        calls = 0

        class Session:
            def __init__(self, **options):
                pass

            def __call__(self, request_payload, request_config, secret, publish, *, deadline):
                nonlocal calls
                with call_lock:
                    calls += 1
                    if calls == 2:
                        second_started.set()
                return safe_result(secret)

        worker = threading.Thread(target=streaming.concurrent_streaming_chat_worker,
                                  args=(connection, 1), daemon=True)
        deadline = streaming.time.monotonic() + 10
        with patch.object(streaming, "CompatibleChatStreamingSession", Session):
            worker.start()
            connection.incoming.put({"request_id": "turnover-first-01", "payload": payload(),
                                     "config": config(), "secret": "first",
                                     "deadline": deadline})
            self.assertTrue(connection.first_terminal.wait(1))
            connection.incoming.put({"request_id": "turnover-second-2", "payload": payload(),
                                     "config": config(), "secret": "second",
                                     "deadline": deadline})
            self.assertTrue(second_started.wait(1))
            connection.release_terminal.set()
            for _ in range(100):
                if len([item for item in connection.sent
                        if item.get("kind") == "complete"]) == 2:
                    break
                threading.Event().wait(.005)
            connection.incoming.put(None)
            worker.join(1)
        self.assertEqual(calls, 2)
        self.assertFalse(any(item.get("kind") == "uncertain"
                             for item in connection.sent))


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

    def test_idle_streaming_model_reports_broker_failure_before_a_request(self):
        transport = MagicMock()
        transport.healthy.return_value = False
        model = chat.ChatModel(
            self.root, transport=transport, streaming=True, **self.common)
        self.addCleanup(model.close)
        with patch.dict("os.environ", {"TINKER_API_KEY": "synthetic"}):
            status = model.status()
        self.assertFalse(status["ready"])
        self.assertFalse(status["blocked"])
        transport.assert_not_called()


if __name__ == "__main__":
    unittest.main()
