#!/usr/bin/env python3
"""Dry-run-first probe for a Runpod OpenAI-compatible streaming endpoint."""

from __future__ import annotations

import argparse
import codecs
import concurrent.futures
import datetime as dt
import http.client
import json
import math
import os
import socket
import ssl
import time
from pathlib import Path
from typing import Callable, Iterable, Sequence
from urllib.parse import urlsplit


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RUNS_ROOT = PROJECT_ROOT / "runs"
DEFAULT_TIMEOUT_SECONDS = 180.0
MAX_TIMEOUT_SECONDS = 3600.0
MAX_TOKENS = 2048
REASONING_EFFORT = "low"
USER_AGENT = "Meforash-serving-pilot/1.0"
ALLOWED_CONCURRENCY = (1, 3, 10)

_PARAGRAPH = (
    "Mira put three labeled jars on a shelf. The cedar jar held blue beads, "
    "the maple jar held green beads, and the pine jar was empty."
)
_QUESTIONS = (
    "Which jar held blue beads?",
    "Which jar was empty?",
    "What color were the beads in the maple jar?",
    "How many jars were on the shelf?",
    "List the jars in the order they appear.",
    "Did the pine jar contain green beads? Explain briefly.",
    "Write one sentence comparing the cedar and pine jars.",
    "What item was stored in the cedar jar?",
    "Summarize the paragraph in no more than twenty words.",
    "If one red bead is added to the pine jar, which jar changed?",
)


class ProbeError(ValueError):
    pass


class SSEDecoder:
    """Incrementally decode UTF-8 Server-Sent Events, including multiline data."""

    def __init__(self) -> None:
        self._decoder = codecs.getincrementaldecoder("utf-8")("strict")
        self._buffer = ""
        self._data_lines: list[str] = []

    def _line(self, line: str) -> list[str]:
        if line.endswith("\r"):
            line = line[:-1]
        if line == "":
            if not self._data_lines:
                return []
            data = "\n".join(self._data_lines)
            self._data_lines.clear()
            return [data]
        if line.startswith(":"):
            return []
        field, separator, value = line.partition(":")
        if field == "data":
            if separator and value.startswith(" "):
                value = value[1:]
            self._data_lines.append(value)
        return []

    def feed(self, chunk: bytes) -> list[str]:
        if not isinstance(chunk, bytes):
            raise TypeError("SSE chunks must be bytes")
        self._buffer += self._decoder.decode(chunk)
        events: list[str] = []
        while "\n" in self._buffer:
            line, self._buffer = self._buffer.split("\n", 1)
            events.extend(self._line(line))
        return events

    def close(self) -> list[str]:
        self._buffer += self._decoder.decode(b"", final=True)
        events: list[str] = []
        if self._buffer:
            events.extend(self._line(self._buffer))
            self._buffer = ""
        if self._data_lines:
            events.extend(self._line(""))
        return events


class StreamSummary:
    def __init__(self) -> None:
        self.first_event_seconds: float | None = None
        self.first_content_seconds: float | None = None
        self.final_content_chars = 0
        self.reasoning_chars = 0
        self.has_visible_content = False
        self.finish_reason: str | None = None
        self.usage: dict[str, int] | None = None
        self.done = False

    def accept(self, data: str, elapsed: float) -> None:
        if self.first_event_seconds is None:
            self.first_event_seconds = elapsed
        if data == "[DONE]":
            self.done = True
            return
        value = json.loads(data)
        if not isinstance(value, dict):
            raise ProbeError("invalid_event")
        usage = value.get("usage")
        if usage is not None:
            self.usage = _safe_usage(usage)
        choices = value.get("choices", [])
        if not isinstance(choices, list):
            raise ProbeError("invalid_event")
        for choice in choices:
            if not isinstance(choice, dict):
                raise ProbeError("invalid_event")
            delta = choice.get("delta", {})
            if not isinstance(delta, dict):
                raise ProbeError("invalid_event")
            content = delta.get("content")
            if content is not None:
                if not isinstance(content, str):
                    raise ProbeError("invalid_event")
                if content and self.first_content_seconds is None:
                    self.first_content_seconds = elapsed
                self.final_content_chars += len(content)
                self.has_visible_content = self.has_visible_content or bool(content.strip())
            for field in ("reasoning", "reasoning_content"):
                reasoning = delta.get(field)
                if reasoning is not None:
                    if not isinstance(reasoning, str):
                        raise ProbeError("invalid_event")
                    self.reasoning_chars += len(reasoning)
            finish = choice.get("finish_reason")
            if finish is not None:
                if not isinstance(finish, str) or self.finish_reason is not None:
                    raise ProbeError("invalid_finish_reason")
                self.finish_reason = finish

    def result(self, elapsed: float) -> dict[str, object]:
        base: dict[str, object] = {
            "elapsed_seconds": round(elapsed, 6),
            "first_event_seconds": _rounded(self.first_event_seconds),
            "first_content_seconds": _rounded(self.first_content_seconds),
            "final_content_chars": self.final_content_chars,
            "reasoning_chars": self.reasoning_chars,
            "finish_reason": self.finish_reason,
            "usage": self.usage,
        }
        if not self.done:
            return {"status": "error", "error": "missing_done", **base}
        if self.finish_reason is None:
            return {"status": "error", "error": "missing_finish_reason", **base}
        if not self.has_visible_content:
            return {"status": "error", "error": "no_content", **base}
        status = "complete" if self.finish_reason == "stop" else "incomplete"
        return {"status": status, **base}


def _rounded(value: float | None) -> float | None:
    return None if value is None else round(value, 6)


def _safe_usage(value: object) -> dict[str, int]:
    if not isinstance(value, dict):
        raise ProbeError("invalid_usage")
    safe: dict[str, int] = {}
    for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
        count = value.get(key)
        if count is not None:
            if type(count) is not int or count < 0:
                raise ProbeError("invalid_usage")
            safe[key] = count
    details = value.get("completion_tokens_details")
    if isinstance(details, dict) and details.get("reasoning_tokens") is not None:
        count = details["reasoning_tokens"]
        if type(count) is not int or count < 0:
            raise ProbeError("invalid_usage")
        safe["reasoning_tokens"] = count
    return safe


def summarize_sse_chunks(
    chunks: Iterable[bytes], *, clock: Callable[[], float] = time.monotonic
) -> dict[str, object]:
    started = clock()
    decoder = SSEDecoder()
    summary = StreamSummary()
    for chunk in chunks:
        for data in decoder.feed(chunk):
            summary.accept(data, clock() - started)
    for data in decoder.close():
        summary.accept(data, clock() - started)
    return summary.result(clock() - started)


def validate_url(value: str) -> str:
    parsed = urlsplit(value)
    if (
        parsed.scheme != "https"
        or parsed.netloc != "api.runpod.ai"
        or not parsed.path.startswith("/")
        or parsed.path == "/"
        or parsed.query
        or parsed.fragment
    ):
        raise ProbeError("URL must be an exact https://api.runpod.ai/... endpoint without a query")
    return value


def validate_timeout(value: object) -> float:
    try:
        timeout = float(value)
    except (TypeError, ValueError) as exc:
        raise ProbeError("timeout must be a finite number from 1 to 3600 seconds") from exc
    if not math.isfinite(timeout) or not 1 <= timeout <= MAX_TIMEOUT_SECONDS:
        raise ProbeError("timeout must be a finite number from 1 to 3600 seconds")
    return timeout


def validate_output(value: str) -> Path:
    path = Path(value)
    if not path.is_absolute():
        path = Path.cwd() / path
    path = path.resolve(strict=False)
    if not path.is_relative_to(RUNS_ROOT.resolve()) or path.suffix != ".json":
        raise ProbeError("output must be a .json file under the ignored runs/ directory")
    return path


def build_prompt(index: int) -> str:
    return f"Read this constructed paragraph and answer briefly.\n\n{_PARAGRAPH}\n\n{_QUESTIONS[index]}"


def build_payload(model: str, index: int) -> dict[str, object]:
    return {
        "model": model,
        "messages": [{"role": "user", "content": build_prompt(index)}],
        "reasoning_effort": REASONING_EFFORT,
        "max_tokens": MAX_TOKENS,
        "stream": True,
        "stream_options": {"include_usage": True},
    }


def _request_one(
    *, url: str, model: str, index: int, api_key: str, timeout_seconds: float
) -> dict[str, object]:
    parsed = urlsplit(validate_url(url))
    payload = json.dumps(build_payload(model, index), separators=(",", ":")).encode("utf-8")
    started = time.monotonic()
    deadline = started + timeout_seconds
    connection = http.client.HTTPSConnection(
        "api.runpod.ai", timeout=timeout_seconds, context=ssl.create_default_context()
    )
    summary = StreamSummary()
    decoder = SSEDecoder()
    try:
        connection.request(
            "POST",
            parsed.path,
            body=payload,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Accept": "text/event-stream",
                "Content-Type": "application/json",
                "User-Agent": USER_AGENT,
            },
        )
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError
        if connection.sock is not None:
            connection.sock.settimeout(remaining)
        response = connection.getresponse()
        if response.status != 200:
            return {
                "request_index": index + 1,
                "status": "error",
                "error": f"http_{response.status}",
                "elapsed_seconds": round(time.monotonic() - started, 6),
            }
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError
            if connection.sock is not None:
                connection.sock.settimeout(remaining)
            # read1 returns currently available stream data instead of waiting
            # for the entire buffer size, which preserves first-event timing.
            chunk = response.read1(4096)
            if not chunk:
                break
            elapsed = time.monotonic() - started
            if elapsed >= timeout_seconds:
                raise TimeoutError
            for data in decoder.feed(chunk):
                summary.accept(data, elapsed)
        elapsed = time.monotonic() - started
        for data in decoder.close():
            summary.accept(data, elapsed)
        return {"request_index": index + 1, **summary.result(elapsed)}
    except (TimeoutError, socket.timeout):
        return {
            "request_index": index + 1,
            "status": "error",
            "error": "deadline_exceeded",
            "elapsed_seconds": round(time.monotonic() - started, 6),
        }
    except (ProbeError, UnicodeError, json.JSONDecodeError):
        return {
            "request_index": index + 1,
            "status": "error",
            "error": "invalid_stream",
            "elapsed_seconds": round(time.monotonic() - started, 6),
        }
    except (OSError, http.client.HTTPException):
        return {
            "request_index": index + 1,
            "status": "error",
            "error": "transport_error",
            "elapsed_seconds": round(time.monotonic() - started, 6),
        }
    finally:
        connection.close()


def run_probe(
    *, url: str, model: str, concurrency: int, api_key: str, timeout_seconds: float
) -> list[dict[str, object]]:
    with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as pool:
        futures = [
            pool.submit(
                _request_one,
                url=url,
                model=model,
                index=index,
                api_key=api_key,
                timeout_seconds=timeout_seconds,
            )
            for index in range(concurrency)
        ]
        return [future.result() for future in futures]


def _dotenv_key(path: Path) -> str | None:
    if path.is_symlink() or (path.exists() and not path.is_file()):
        raise ProbeError("dotenv path must be a regular local file")
    if not path.exists():
        return None
    try:
        from dotenv import dotenv_values
    except ImportError as exc:
        raise ProbeError("python-dotenv is required when --dotenv is used") from exc
    values = dotenv_values(path, interpolate=False, encoding="utf-8")
    value = values.get("RUNPOD_API_KEY")
    return value if isinstance(value, str) and value else None


def load_api_key(dotenv_path: Path | None) -> str:
    value = os.environ.get("RUNPOD_API_KEY")
    if not value and dotenv_path is not None:
        value = _dotenv_key(dotenv_path)
    if not value:
        raise ProbeError("RUNPOD_API_KEY is required with --execute")
    return value


def ensure_output_available(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        raise ProbeError(f"output already exists: {path}")


def reserve_output(path: Path) -> None:
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError as exc:
        raise ProbeError(f"output already exists: {path}") from exc
    os.close(descriptor)


def write_report(path: Path, report: dict[str, object]) -> None:
    path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", required=True, help="Exact api.runpod.ai chat-completions URL")
    parser.add_argument("--model", required=True, help="Model identifier sent to the endpoint")
    parser.add_argument("--concurrency", type=int, choices=ALLOWED_CONCURRENCY, required=True)
    parser.add_argument("--output", required=True, help="New private JSON report under runs/")
    parser.add_argument("--timeout", type=str, default=str(int(DEFAULT_TIMEOUT_SECONDS)),
                        help="Absolute per-request deadline in seconds (default: 180; max: 3600)")
    parser.add_argument("--execute", action="store_true",
                        help="Make the bounded requests; omission performs a dry run")
    parser.add_argument("--dotenv", nargs="?", const=str(PROJECT_ROOT / ".env"),
                        help="Optionally read RUNPOD_API_KEY from PATH (default PATH: project .env)")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        url = validate_url(args.url)
        timeout = validate_timeout(args.timeout)
        output = validate_output(args.output)
        # Reject an existing receipt before credentials or paid requests are used.
        ensure_output_available(output)
        report: dict[str, object] = {
            "schema_version": 1,
            "created_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
            "mode": "execute" if args.execute else "dry_run",
            "url": url,
            "model": args.model,
            "concurrency": args.concurrency,
            "request_count": args.concurrency,
            "timeout_seconds": timeout,
            "request": {
                "reasoning_effort": REASONING_EFFORT,
                "max_tokens": MAX_TOKENS,
                "stream": True,
            },
        }
        if args.execute:
            dotenv_path = Path(args.dotenv).expanduser() if args.dotenv else None
            key = load_api_key(dotenv_path)
            # Reserve atomically before starting requests so concurrent probes
            # cannot spend against the same receipt path.
            reserve_output(output)
            report["results"] = run_probe(
                url=url,
                model=args.model,
                concurrency=args.concurrency,
                api_key=key,
                timeout_seconds=timeout,
            )
        else:
            reserve_output(output)
            report["results"] = []
        write_report(output, report)
    except ProbeError as exc:
        parser.error(str(exc))
    print(f"{'Executed' if args.execute else 'Dry run only'}; report: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
