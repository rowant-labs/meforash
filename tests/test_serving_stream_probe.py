import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from tools import serving_stream_probe as probe


class StepClock:
    def __init__(self):
        self.value = 0.0

    def __call__(self):
        self.value += 0.1
        return self.value


class ServingStreamProbeTests(unittest.TestCase):
    def test_multiline_sse_and_fragmented_utf8_are_summarized_without_text(self):
        stream = (
            'data: {"choices":[\n'
            'data: {"delta":{"reasoning_content":"plan"},"finish_reason":null}]}\n\n'
            'data: {"choices":[{"delta":{"content":"café"},"finish_reason":null}]}\n\n'
            'data: {"choices":[{"delta":{},"finish_reason":"stop"}],'
            '"usage":{"prompt_tokens":12,"completion_tokens":7,"total_tokens":19,'
            '"completion_tokens_details":{"reasoning_tokens":2}}}\n\n'
            'data: [DONE]\n\n'
        ).encode("utf-8")
        split = stream.index("é".encode("utf-8")) + 1
        result = probe.summarize_sse_chunks(
            [stream[:17], stream[17:split], stream[split:]], clock=StepClock()
        )

        self.assertEqual(result["status"], "complete")
        self.assertEqual(result["finish_reason"], "stop")
        self.assertEqual(result["final_content_chars"], 4)
        self.assertEqual(result["reasoning_chars"], 4)
        self.assertEqual(result["usage"]["reasoning_tokens"], 2)
        self.assertLess(result["first_event_seconds"], result["first_content_seconds"])
        rendered = json.dumps(result)
        self.assertNotIn("café", rendered)
        self.assertNotIn("plan", rendered)

    def test_terminal_stream_without_visible_content_is_an_error(self):
        result = probe.summarize_sse_chunks(
            [
                b'data: {"choices":[{"delta":{"content":"  "},'
                b'"finish_reason":"stop"}]}\n\ndata: [DONE]\n\n'
            ]
        )

        self.assertEqual(result["status"], "error")
        self.assertEqual(result["error"], "no_content")
        self.assertEqual(result["finish_reason"], "stop")

    def test_done_without_finish_reason_is_an_error(self):
        result = probe.summarize_sse_chunks(
            [b'data: {"choices":[{"delta":{"content":"answer"}}]}\n\ndata: [DONE]\n\n']
        )

        self.assertEqual(result["error"], "missing_finish_reason")

    def test_url_is_restricted_to_exact_runpod_https_host(self):
        allowed = "https://api.runpod.ai/v2/example/openai/v1/chat/completions"
        self.assertEqual(probe.validate_url(allowed), allowed)
        for value in (
            "http://api.runpod.ai/v2/x",
            "https://api.runpod.ai.evil.example/v2/x",
            "https://api.runpod.ai:443/v2/x",
            "https://user@api.runpod.ai/v2/x",
            "https://api.runpod.ai/v2/x?key=secret",
        ):
            with self.subTest(value=value), self.assertRaises(probe.ProbeError):
                probe.validate_url(value)

    def test_payload_has_fixed_streaming_limits_and_constructed_prompt(self):
        payload = probe.build_payload("openai/gpt-oss-20b", 0)

        self.assertTrue(payload["stream"])
        self.assertEqual(payload["stream_options"], {"include_usage": True})
        self.assertEqual(payload["reasoning_effort"], "low")
        self.assertEqual(payload["max_tokens"], 2048)
        self.assertIn("constructed paragraph", payload["messages"][0]["content"])

    def test_dry_run_writes_private_plan_without_reading_key_or_network(self):
        with tempfile.TemporaryDirectory(dir=probe.RUNS_ROOT) as directory:
            output = Path(directory) / "dry-run.json"
            stdout = io.StringIO()
            with (
                patch.dict(os.environ, {}, clear=True),
                patch.object(probe, "load_api_key", side_effect=AssertionError("key read")),
                patch.object(probe, "run_probe", side_effect=AssertionError("network")),
                redirect_stdout(stdout),
            ):
                result = probe.main(
                    [
                        "--url", "https://api.runpod.ai/v2/test/openai/v1/chat/completions",
                        "--model", "openai/gpt-oss-20b",
                        "--concurrency", "3",
                        "--output", str(output),
                    ]
                )

            report = json.loads(output.read_text())
            self.assertEqual(result, 0)
            self.assertEqual(report["mode"], "dry_run")
            self.assertEqual(report["request_count"], 3)
            self.assertEqual(report["results"], [])
            self.assertNotIn("key", output.read_text().lower())
            self.assertIn("Dry run only", stdout.getvalue())

    def test_execute_uses_exact_bounded_count_and_never_reports_key(self):
        with tempfile.TemporaryDirectory(dir=probe.RUNS_ROOT) as directory:
            output = Path(directory) / "execute.json"
            fake_results = [{"request_index": number, "status": "complete"} for number in range(1, 4)]
            with (
                patch.dict(os.environ, {"RUNPOD_API_KEY": "private-test-key"}, clear=True),
                patch.object(probe, "run_probe", return_value=fake_results) as runner,
                redirect_stdout(io.StringIO()),
            ):
                probe.main(
                    [
                        "--url", "https://api.runpod.ai/v2/test/openai/v1/chat/completions",
                        "--model", "model-test",
                        "--concurrency", "3",
                        "--output", str(output),
                        "--execute",
                    ]
                )

            runner.assert_called_once_with(
                url="https://api.runpod.ai/v2/test/openai/v1/chat/completions",
                model="model-test",
                concurrency=3,
                api_key="private-test-key",
                timeout_seconds=180.0,
            )
            rendered = output.read_text()
            self.assertNotIn("private-test-key", rendered)
            self.assertEqual(len(json.loads(rendered)["results"]), 3)

    def test_existing_output_is_rejected_before_any_request(self):
        with tempfile.TemporaryDirectory(dir=probe.RUNS_ROOT) as directory:
            output = Path(directory) / "existing.json"
            output.write_text("preserve me\n")
            with (
                patch.dict(os.environ, {"RUNPOD_API_KEY": "private-test-key"}, clear=True),
                patch.object(probe, "run_probe") as runner,
                patch.object(probe, "load_api_key") as key_loader,
                patch("sys.stderr", new=io.StringIO()),
                self.assertRaises(SystemExit),
            ):
                probe.main(
                    [
                        "--url", "https://api.runpod.ai/v2/test/openai/v1/chat/completions",
                        "--model", "model-test",
                        "--concurrency", "1",
                        "--output", str(output),
                        "--execute",
                    ]
                )

            key_loader.assert_not_called()
            runner.assert_not_called()
            self.assertEqual(output.read_text(), "preserve me\n")

    def test_request_sets_user_agent_and_remaining_header_deadline(self):
        event = (
            b'data: {"choices":[{"delta":{"content":"answer"},'
            b'"finish_reason":"stop"}]}\n\ndata: [DONE]\n\n'
        )

        class Socket:
            def __init__(self):
                self.timeouts = []

            def settimeout(self, value):
                self.timeouts.append(value)

        class Response:
            status = 200

            def __init__(self):
                self.chunks = iter((event, b""))

            def read1(self, _size):
                return next(self.chunks)

        class Connection:
            def __init__(self):
                self.sock = Socket()
                self.headers = None
                self.closed = False

            def request(self, _method, _path, *, body, headers):
                self.body = body
                self.headers = headers

            def getresponse(self):
                self.header_timeout = self.sock.timeouts[-1]
                return Response()

            def close(self):
                self.closed = True

        connection = Connection()
        timestamps = iter((100.0, 102.0, 103.0, 104.0, 105.0, 106.0, 107.0))
        with (
            patch.object(probe.http.client, "HTTPSConnection", return_value=connection),
            patch.object(probe.ssl, "create_default_context"),
            patch.object(probe.time, "monotonic", side_effect=lambda: next(timestamps)),
        ):
            result = probe._request_one(
                url="https://api.runpod.ai/v2/test/openai/v1/chat/completions",
                model="model-test",
                index=0,
                api_key="private-test-key",
                timeout_seconds=10,
            )

        self.assertEqual(result["status"], "complete")
        self.assertEqual(connection.headers["User-Agent"], "Meforash-serving-pilot/1.0")
        self.assertEqual(connection.header_timeout, 8.0)
        self.assertTrue(connection.closed)

    def test_timeout_must_be_finite_and_bounded(self):
        for value in ("nan", "inf", 0, 3601):
            with self.subTest(value=value), self.assertRaises(probe.ProbeError):
                probe.validate_timeout(value)


if __name__ == "__main__":
    unittest.main()
