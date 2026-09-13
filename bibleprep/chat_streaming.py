"""Default-off compatible-chat streaming for the retained B adapter.

Only cumulative structured answer text crosses the worker pipe. Provider
reasoning, response bodies, identifiers, exceptions, and credentials remain in
the quiet child process. A submitted request is never retried or sent to the
native endpoint as a fallback.
"""
from __future__ import annotations

import contextlib
import json
import math
import multiprocessing
import os
import queue
import secrets
import threading
import time


COMPATIBLE_CHAT_URL = (
    "https://tinker.thinkingmachines.dev/services/tinker-prod/oai/api/v1/chat/completions"
)
MAX_ANSWER_BYTES = 512_000
LOCAL_ERROR_CODES = {
    "invalid_messages", "input_too_long", "runtime_unavailable", "checkpoint_unavailable"
}
MAX_CONCURRENT_STREAMS = 10
MAX_PENDING_REPLIES = 64


def _compatible_result(answer, finish_reason, input_tokens, output_tokens):
    """Build the existing public result schema from structured final content.

    ``native_turn_complete`` is retained for schema compatibility. On this
    explicitly separate transport it means that the provider emitted a normal
    terminal turn, rather than claiming native-TML parse equivalence.
    """
    complete = bool(answer.strip() and finish_reason == "stop")
    warnings = []
    if finish_reason == "length":
        warnings.append("output_limit")
    if not answer.strip():
        warnings.append("no_final_answer")
    elif not complete:
        warnings.append("incomplete_answer")
    return {
        "answer": answer,
        "answer_complete": complete,
        "native_turn_complete": finish_reason == "stop",
        "finish_reason": finish_reason,
        "partial": not complete,
        "usage": {
            "input_tokens": input_tokens,
            # Compatible usage includes answer, reasoning, and protocol costs.
            "output_tokens": output_tokens,
            "estimated_usd": round((input_tokens * 1.87 + output_tokens * 4.68) / 1_000_000, 8),
            "is_invoice": False,
            "price_snapshot_date": "2026-09-06",
        },
        "warnings": warnings,
    }


class CompatibleChatStreamingSession:
    """Validate one compatible OpenAI-style SSE response without retries."""

    def __init__(self, *, profile=None, stream_factory=None, clock=None,
                 profile_lock=None):
        self.profile = profile
        self.stream_factory = stream_factory
        self.clock = clock or time.monotonic
        self.profile_lock = profile_lock

    def _stream(self, *, headers, body, timeout_seconds):
        if self.stream_factory is not None:
            return self.stream_factory(
                COMPATIBLE_CHAT_URL, headers=headers, json=body, timeout=timeout_seconds
            )
        import httpx
        timeout = httpx.Timeout(timeout_seconds, connect=min(20, timeout_seconds))
        return httpx.stream(
            "POST", COMPATIBLE_CHAT_URL, headers=headers, json=body, timeout=timeout
        )

    @staticmethod
    def _event(raw):
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        if not isinstance(raw, str):
            raise ValueError
        if (not raw or raw.startswith(":")
                or raw.startswith("event:") or raw.startswith("id:")
                or raw.startswith("retry:")):
            return None
        if not raw.startswith("data:"):
            raise ValueError
        data = raw[5:].strip()
        if data == "[DONE]":
            return "done"
        value = json.loads(data)
        if not isinstance(value, dict):
            raise ValueError
        return value

    @staticmethod
    def _usage(value, native_input_tokens, answer_tokens, max_output_tokens):
        if not isinstance(value, dict):
            raise ValueError
        prompt = value.get("prompt_tokens")
        completion = value.get("completion_tokens")
        total = value.get("total_tokens")
        if any(type(item) is not int or item < 0 for item in (prompt, completion, total)):
            raise ValueError
        if (prompt != native_input_tokens or total != prompt + completion
                or completion < answer_tokens or completion > max_output_tokens):
            raise ValueError
        return prompt, completion

    @contextlib.contextmanager
    def _profile_access(self, deadline):
        if self.profile_lock is None:
            yield
            return
        if deadline is None:
            self.profile_lock.acquire()
        else:
            remaining = deadline - time.monotonic()
            if remaining <= 0 or not self.profile_lock.acquire(timeout=remaining):
                raise TimeoutError("streaming renderer deadline")
        try:
            yield
        finally:
            self.profile_lock.release()

    def __call__(self, payload, config, secret, publish, *, deadline=None):
        from bibleprep.chat_model import ChatModelError, ChatNativeProfile, MODEL

        try:
            with self._profile_access(deadline):
                if self.profile is None:
                    try:
                        self.profile = ChatNativeProfile()
                    except ChatModelError:
                        raise
                    except Exception:
                        raise ChatModelError("runtime_unavailable") from None
                native_ids, _ = self.profile.render(payload, config)
        except ChatModelError:
            raise
        except Exception:
            raise ChatModelError("runtime_unavailable") from None
        if len(native_ids) > config["max_input_tokens"]:
            raise ChatModelError("input_too_long")
        if (config.get("model") != MODEL or config.get("reasoning_effort") != "medium"
                or config.get("thinking_effort_numeric") != 0.7
                or config.get("temperature") != 0.0
                or type(config.get("seed")) is not int):
            raise ChatModelError("runtime_unavailable")

        body = {
            "model": config["adapter_sampler_path"],
            "messages": payload["messages"],
            "stream": True,
            "stream_options": {"include_usage": True},
            "max_tokens": config["max_output_tokens"],
            "temperature": 0.0,
            "seed": config["seed"],
            "reasoning_effort": "medium",
            "separate_reasoning": True,
        }
        headers = {"Authorization": "Bearer " + secret, "Accept": "text/event-stream"}
        answer = ""
        finish_reason = None
        usage = None
        done = False
        last_publish_at = float("-inf")
        published = ""
        timeout_seconds = config["timeout_seconds"]
        if deadline is not None:
            timeout_seconds = deadline - time.monotonic()
            if timeout_seconds <= 0:
                raise TimeoutError("streaming request deadline")
        with self._stream(headers=headers, body=body,
                          timeout_seconds=timeout_seconds) as response:
            if response.status_code != 200:
                raise RuntimeError("compatible request failed")
            for raw in response.iter_lines():
                if deadline is not None and time.monotonic() >= deadline:
                    raise TimeoutError("streaming request deadline")
                event = self._event(raw)
                if event is None:
                    continue
                if event == "done":
                    done = True
                    break
                if event.get("usage") is not None:
                    if usage is not None:
                        raise ValueError
                    usage = event["usage"]
                choices = event.get("choices", [])
                if not isinstance(choices, list) or len(choices) > 1:
                    raise ValueError
                for choice in choices:
                    if not isinstance(choice, dict) or choice.get("index", 0) != 0:
                        raise ValueError
                    delta = choice.get("delta", {})
                    if not isinstance(delta, dict):
                        raise ValueError
                    # Reasoning is type-checked only and immediately discarded.
                    for key in delta:
                        if key not in {
                                "content", "reasoning_content", "role", "tool_calls", "refusal"}:
                            raise ValueError
                    if delta.get("reasoning_content") is not None and not isinstance(
                            delta["reasoning_content"], str):
                        raise ValueError
                    if delta.get("role") not in {None, "assistant"}:
                        raise ValueError
                    # The compatible endpoint includes these standard fields on
                    # answer events. Only their explicit empty values are safe;
                    # tools and refusals are not final-answer text.
                    if delta.get("tool_calls") is not None and delta["tool_calls"] != []:
                        raise ValueError
                    if delta.get("refusal") is not None:
                        raise ValueError
                    content = delta.get("content")
                    if content is not None:
                        if not isinstance(content, str) or finish_reason is not None:
                            raise ValueError
                        answer += content
                        if len(answer.encode("utf-8")) > MAX_ANSWER_BYTES:
                            raise ValueError
                        now = self.clock()
                        if answer != published and now - last_publish_at >= 0.25:
                            publish(answer)
                            published, last_publish_at = answer, now
                    terminal = choice.get("finish_reason")
                    if terminal is not None:
                        if finish_reason is not None or terminal not in {"stop", "length"}:
                            raise ValueError
                        finish_reason = terminal

        if not done or finish_reason is None or usage is None:
            raise RuntimeError("incomplete compatible stream")
        if answer != published:
            publish(answer)
            published = answer
        try:
            with self._profile_access(deadline):
                answer_tokens = len(self.profile.native.encode_ordinary(answer))
        except Exception:
            raise RuntimeError("answer tokenization failed") from None
        input_tokens, output_tokens = self._usage(
            usage, len(native_ids), answer_tokens, config["max_output_tokens"]
        )
        return _compatible_result(answer, finish_reason, input_tokens, output_tokens)


def concurrent_streaming_chat_worker(connection, max_requests=MAX_CONCURRENT_STREAMS):
    """Multiplex HTTP streams while one quiet child owns the native profile."""
    os.environ["TINKER_TELEMETRY"] = "0"
    with open(os.devnull, "w") as sink, contextlib.redirect_stdout(sink), \
            contextlib.redirect_stderr(sink):
        send_lock = threading.Lock()
        profile_lock = threading.Lock()
        capacity = threading.BoundedSemaphore(max_requests)
        session = CompatibleChatStreamingSession(profile_lock=profile_lock)

        def send(value):
            with send_lock:
                connection.send(value)

        def handle(request):
            request_id = request["request_id"]
            revision = 0
            response = None
            terminal = None

            def publish(answer):
                nonlocal revision
                revision += 1
                send({"request_id": request_id, "kind": "progress",
                      "revision": revision, "answer": answer})

            try:
                response = session(
                    request["payload"], request["config"], request["secret"], publish,
                    deadline=request["deadline"])
                terminal = {"request_id": request_id, "kind": "complete",
                            "revision": revision, "response": response}
            except Exception as exc:
                from bibleprep.chat_model import ChatModelError
                if isinstance(exc, ChatModelError) and exc.code in LOCAL_ERROR_CODES:
                    terminal = {"request_id": request_id, "kind": "local_error",
                                "code": exc.code}
                else:
                    terminal = {"request_id": request_id, "kind": "uncertain"}
            finally:
                request = None
                response = None
                capacity.release()
            send(terminal)

        try:
            while True:
                request = connection.recv()
                if request is None:
                    break
                if (not isinstance(request, dict)
                        or set(request) != {"request_id", "payload", "config", "secret", "deadline"}
                        or not isinstance(request["request_id"], str)
                        or not 16 <= len(request["request_id"]) <= 64
                        or type(request["deadline"]) not in (int, float)
                        or not math.isfinite(request["deadline"])):
                    break
                if request["deadline"] <= time.monotonic():
                    send({"request_id": request["request_id"], "kind": "local_error",
                          "code": "runtime_unavailable"})
                    request = None
                    continue
                if not capacity.acquire(blocking=False):
                    send({"request_id": request["request_id"], "kind": "uncertain"})
                    request = None
                    continue
                worker = threading.Thread(target=handle, args=(request,), daemon=True)
                try:
                    worker.start()
                except Exception:
                    capacity.release()
                    send({"request_id": request["request_id"], "kind": "uncertain"})
                request = None
        except (EOFError, BrokenPipeError):
            pass
        finally:
            connection.close()


# Historical name retained for direct imports; the implementation is concurrent.
streaming_chat_worker = concurrent_streaming_chat_worker


class SharedStreamingBroker:
    """Correlate bounded calls through one spawned quiet renderer process."""

    def __init__(self, worker=concurrent_streaming_chat_worker,
                 max_requests=MAX_CONCURRENT_STREAMS):
        self.worker = worker
        self.max_requests = max_requests
        self.process = self.connection = self.reader = None
        self.lock = threading.Lock()
        self.send_lock = threading.Lock()
        self.inflight = {}
        self.failed = False
        self.closed = False

    def _start(self):
        with self.lock:
            if self.closed or self.failed:
                raise RuntimeError("streaming broker unavailable")
            if self.process is not None:
                return
            context = multiprocessing.get_context("spawn")
            connection, child = context.Pipe()
            process = context.Process(
                target=self.worker, args=(child, self.max_requests), daemon=True)
            try:
                process.start()
            except Exception:
                connection.close()
                child.close()
                self.failed = True
                raise
            child.close()
            self.connection, self.process = connection, process
            self.reader = threading.Thread(
                target=self._read_replies, daemon=True, name="meforash-stream-router")
            self.reader.start()

    def healthy(self):
        with self.lock:
            if self.closed or self.failed:
                return False
            return self.process is None or self.process.is_alive()

    def _fail(self):
        with self.lock:
            if self.failed:
                return
            self.failed = True
            waiting = [entry["queue"] for entry in self.inflight.values()
                       if entry["queue"] is not None]
        for destination in waiting:
            self._signal(destination, {"kind": "broker_failed"})
        _poison_shared_broker(self)

    @staticmethod
    def _signal(destination, value):
        try:
            destination.put_nowait(value)
        except queue.Full:
            try:
                while True:
                    destination.get_nowait()
            except queue.Empty:
                pass
            destination.put_nowait({"kind": "broker_failed"})

    def _read_replies(self):
        try:
            while True:
                reply = self.connection.recv()
                if (not isinstance(reply, dict)
                        or not isinstance(reply.get("request_id"), str)):
                    raise ValueError
                request_id = reply["request_id"]
                with self.lock:
                    entry = self.inflight.get(request_id)
                    if entry is None:
                        raise ValueError
                    destination = entry["queue"]
                    terminal = reply.get("kind") in {"complete", "local_error", "uncertain"}
                    if terminal:
                        del self.inflight[request_id]
                if destination is not None:
                    self._signal(destination, reply)
        except (EOFError, BrokenPipeError, OSError, ValueError):
            if not self.closed:
                self._fail()

    def open_request(self, payload, config, secret, *, deadline):
        self._start()
        if deadline <= time.monotonic():
            raise TimeoutError("streaming request deadline")
        request_id = secrets.token_urlsafe(18)
        destination = queue.Queue(maxsize=MAX_PENDING_REPLIES)
        with self.lock:
            if self.closed or self.failed or len(self.inflight) >= self.max_requests:
                raise RuntimeError("streaming broker capacity unavailable")
            self.inflight[request_id] = {"queue": destination}
        try:
            remaining = deadline - time.monotonic()
            if remaining <= 0 or not self.send_lock.acquire(timeout=remaining):
                raise TimeoutError("streaming request deadline")
            try:
                if deadline <= time.monotonic():
                    raise TimeoutError("streaming request deadline")
                self.connection.send({"request_id": request_id, "payload": payload,
                                      "config": config, "secret": secret,
                                      "deadline": deadline})
            finally:
                self.send_lock.release()
        except TimeoutError:
            with self.lock:
                self.inflight.pop(request_id, None)
            raise
        except Exception:
            with self.lock:
                self.inflight.pop(request_id, None)
            self._fail()
            raise
        return request_id, destination

    def abandon(self, request_id):
        """Discard delivery while retaining capacity until the child terminates it."""
        with self.lock:
            entry = self.inflight.get(request_id)
            if entry is not None:
                entry["queue"] = None

    def close(self):
        with self.lock:
            if self.closed:
                return
            self.closed = True
            connection, process, reader = self.connection, self.process, self.reader
            waiting = [entry["queue"] for entry in self.inflight.values()
                       if entry["queue"] is not None]
        for destination in waiting:
            self._signal(destination, {"kind": "broker_failed"})
        if connection is not None:
            try:
                with self.send_lock:
                    connection.send(None)
            except Exception:
                pass
        if process is not None:
            process.join(timeout=2)
            if process.is_alive():
                process.terminate()
                process.join(timeout=2)
            if process.is_alive():
                process.kill()
                process.join(timeout=2)
        if connection is not None:
            connection.close()
        if reader is not None and reader is not threading.current_thread():
            reader.join(timeout=1)


_SHARED_LOCK = threading.Lock()
_SHARED_BROKER = None
_SHARED_REFS = 0
_SHARED_POISONED = False


def _poison_shared_broker(broker):
    global _SHARED_POISONED
    with _SHARED_LOCK:
        if _SHARED_BROKER is broker:
            _SHARED_POISONED = True


def shared_streaming_ready():
    with _SHARED_LOCK:
        broker = _SHARED_BROKER
        poisoned = _SHARED_POISONED
    return not poisoned and (broker is None or broker.healthy())


def _acquire_shared_broker():
    global _SHARED_BROKER, _SHARED_REFS
    with _SHARED_LOCK:
        if _SHARED_POISONED:
            raise RuntimeError("streaming broker requires process restart")
        if _SHARED_BROKER is None:
            _SHARED_BROKER = SharedStreamingBroker()
        _SHARED_REFS += 1
        return _SHARED_BROKER


def _release_shared_broker(broker):
    global _SHARED_BROKER, _SHARED_REFS
    close = False
    with _SHARED_LOCK:
        if _SHARED_BROKER is broker:
            _SHARED_REFS -= 1
            if _SHARED_REFS == 0:
                _SHARED_BROKER = None
                close = True
    if close:
        broker.close()


class BoundedStreamingTransport:
    """One correlated stream on a shared worker, with an end-to-end deadline."""

    def __init__(self, broker=None):
        self.broker = broker
        self._shared = broker is None
        self._acquired = broker is not None
        self.failed = False
        self.closed = False
        self.lock = threading.Lock()

    def healthy(self):
        broker_ready = (shared_streaming_ready() if self.broker is None
                        else self.broker.healthy())
        return not self.failed and not self.closed and broker_ready

    def close(self):
        with self.lock:
            if self.closed:
                return
            self.closed = True
            broker = self.broker
            shared = self._shared and self._acquired
        if shared:
            _release_shared_broker(broker)

    @staticmethod
    def _progress(reply, request_id, last_revision, last_answer):
        if (not isinstance(reply, dict)
                or set(reply) != {"request_id", "kind", "revision", "answer"}
                or reply["request_id"] != request_id or reply["kind"] != "progress"
                or type(reply["revision"]) is not int or reply["revision"] <= last_revision
                or not isinstance(reply["answer"], str)
                or not reply["answer"].startswith(last_answer)
                or len(reply["answer"].encode("utf-8")) > MAX_ANSWER_BYTES):
            raise ValueError
        return reply["revision"], reply["answer"]

    def __call__(self, payload, config, secret, on_progress=None):
        deadline = time.monotonic() + config["timeout_seconds"]
        with self.lock:
            if self.failed or self.closed:
                raise RuntimeError("uncertain streaming operation")
            if not self._acquired:
                self.broker = _acquire_shared_broker()
                self._acquired = True
            broker = self.broker
        request_id = None
        revision, answer = 0, ""
        callback = on_progress
        try:
            request_id, replies = broker.open_request(
                payload, config, secret, deadline=deadline)
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError("streaming request deadline")
                try:
                    reply = replies.get(timeout=remaining)
                except queue.Empty:
                    raise TimeoutError("streaming request deadline") from None
                if isinstance(reply, dict) and reply.get("kind") == "progress":
                    revision, answer = self._progress(
                        reply, request_id, revision, answer)
                    if callback is not None:
                        try:
                            callback(answer, revision)
                        except Exception:
                            callback = None
                    continue
                if (isinstance(reply, dict)
                        and set(reply) == {"request_id", "kind", "code"}
                        and reply["request_id"] == request_id
                        and reply["kind"] == "local_error"
                        and reply["code"] in LOCAL_ERROR_CODES):
                    return {"local_error": reply["code"]}
                if (not isinstance(reply, dict)
                        or set(reply) != {"request_id", "kind", "revision", "response"}
                        or reply["request_id"] != request_id or reply["kind"] != "complete"
                        or type(reply["revision"]) is not int or reply["revision"] != revision
                        or not isinstance(reply["response"], dict)
                        or reply["response"].get("answer") != answer):
                    raise RuntimeError("invalid streaming terminal envelope")
                return reply["response"]
        except Exception:
            if request_id is not None:
                broker.abandon(request_id)
            self.failed = True
            self.close()
            raise
