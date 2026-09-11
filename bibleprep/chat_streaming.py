"""Default-off compatible-chat streaming for the retained B adapter.

Only cumulative structured answer text crosses the worker pipe. Provider
reasoning, response bodies, identifiers, exceptions, and credentials remain in
the quiet child process. A submitted request is never retried or sent to the
native endpoint as a fallback.
"""
from __future__ import annotations

import contextlib
import json
import multiprocessing
import os
import time


COMPATIBLE_CHAT_URL = (
    "https://tinker.thinkingmachines.dev/services/tinker-prod/oai/api/v1/chat/completions"
)
MAX_ANSWER_BYTES = 512_000
LOCAL_ERROR_CODES = {
    "invalid_messages", "input_too_long", "runtime_unavailable", "checkpoint_unavailable"
}


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

    def __init__(self, *, profile=None, stream_factory=None, clock=None):
        self.profile = profile
        self.stream_factory = stream_factory
        self.clock = clock or time.monotonic

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

    def __call__(self, payload, config, secret, publish):
        from bibleprep.chat_model import ChatModelError, ChatNativeProfile, MODEL

        if self.profile is None:
            try:
                self.profile = ChatNativeProfile()
            except ChatModelError:
                raise
            except Exception:
                raise ChatModelError("runtime_unavailable") from None
        try:
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
        with self._stream(headers=headers, body=body,
                          timeout_seconds=config["timeout_seconds"]) as response:
            if response.status_code != 200:
                raise RuntimeError("compatible request failed")
            for raw in response.iter_lines():
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
            answer_tokens = len(self.profile.native.encode_ordinary(answer))
        except Exception:
            raise RuntimeError("answer tokenization failed") from None
        input_tokens, output_tokens = self._usage(
            usage, len(native_ids), answer_tokens, config["max_output_tokens"]
        )
        return _compatible_result(answer, finish_reason, input_tokens, output_tokens)


def streaming_chat_worker(connection):
    """Keep HTTP/SSE details and private reasoning inside a quiet child."""
    os.environ["TINKER_TELEMETRY"] = "0"
    with open(os.devnull, "w") as sink, contextlib.redirect_stdout(sink), contextlib.redirect_stderr(sink):
        session = CompatibleChatStreamingSession()
        try:
            while True:
                request = connection.recv()
                if request is None:
                    break
                revision = 0

                def publish(answer):
                    nonlocal revision
                    revision += 1
                    connection.send({"kind": "progress", "revision": revision, "answer": answer})

                try:
                    response = session(*request, publish)
                    connection.send({
                        "kind": "complete", "revision": revision, "response": response
                    })
                except Exception as exc:
                    from bibleprep.chat_model import ChatModelError
                    if isinstance(exc, ChatModelError) and exc.code in LOCAL_ERROR_CODES:
                        connection.send({"kind": "local_error", "code": exc.code})
                    else:
                        connection.send({"kind": "uncertain"})
                        break
                finally:
                    request = None
                    response = None
        except (EOFError, BrokenPipeError):
            pass
        finally:
            connection.close()


class BoundedStreamingTransport:
    """One spawned worker, one provider submission, one whole-operation deadline."""

    def __init__(self, worker=streaming_chat_worker):
        self.worker = worker
        self.process = self.connection = None
        self.failed = False

    def close(self):
        if self.process is not None:
            if self.process.is_alive():
                self.process.terminate()
                self.process.join(timeout=2)
                if self.process.is_alive():
                    self.process.kill()
                    self.process.join(timeout=2)
            else:
                self.process.join(timeout=0)
            self.process = None
        if self.connection is not None:
            self.connection.close()
            self.connection = None

    @staticmethod
    def _progress(reply, last_revision, last_answer):
        if (not isinstance(reply, dict) or set(reply) != {"kind", "revision", "answer"}
                or reply["kind"] != "progress"
                or type(reply["revision"]) is not int or reply["revision"] <= last_revision
                or not isinstance(reply["answer"], str)
                or not reply["answer"].startswith(last_answer)
                or len(reply["answer"].encode("utf-8")) > MAX_ANSWER_BYTES):
            raise ValueError
        return reply["revision"], reply["answer"]

    def __call__(self, payload, config, secret, on_progress=None):
        if self.failed:
            raise RuntimeError("uncertain streaming operation")
        if self.process is None:
            context = multiprocessing.get_context("spawn")
            self.connection, child = context.Pipe()
            self.process = context.Process(target=self.worker, args=(child,), daemon=True)
            self.process.start()
            child.close()
        deadline = time.monotonic() + config["timeout_seconds"]
        revision, answer = 0, ""
        callback = on_progress
        try:
            self.connection.send((payload, config, secret))
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0 or not self.connection.poll(remaining):
                    raise TimeoutError("streaming request deadline")
                reply = self.connection.recv()
                if isinstance(reply, dict) and reply.get("kind") == "progress":
                    revision, answer = self._progress(reply, revision, answer)
                    if callback is not None:
                        try:
                            callback(answer, revision)
                        except Exception:
                            callback = None
                    continue
                if (isinstance(reply, dict) and set(reply) == {"kind", "code"}
                        and reply["kind"] == "local_error" and reply["code"] in LOCAL_ERROR_CODES):
                    return {"local_error": reply["code"]}
                if (not isinstance(reply, dict)
                        or set(reply) != {"kind", "revision", "response"}
                        or reply["kind"] != "complete"
                        or type(reply["revision"]) is not int or reply["revision"] != revision
                        or not isinstance(reply["response"], dict)
                        or reply["response"].get("answer") != answer):
                    raise RuntimeError("invalid streaming terminal envelope")
                return reply["response"]
        except Exception:
            self.failed = True
            self.close()
            raise
