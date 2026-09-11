import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import urllib.error

from bibleprep import evaluate as ev


class BaselineEvaluationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        runs_patch = patch.object(ev, "RUNS_ROOT", self.root / "runs")
        runs_patch.start()
        self.addCleanup(runs_patch.stop)
        self.dataset = self.root / "cases.jsonl"
        self.cases = [self.case("one"), self.case("two")]
        self.save_cases()
        self.config = {
            "dataset": str(self.dataset), "run_dir": str(self.root / "runs" / "run"),
            "base_url": "https://example.invalid/v1", "model": "test-model",
            "model_version": "test-revision", "api_key_env": "EVAL_TEST_SECRET",
            "max_cases": 2, "max_input_tokens": 3000, "max_output_tokens": 100,
            "timeout_seconds": 1, "input_price_per_million": 1.0,
            "output_price_per_million": 1.0, "budget_usd": 0.02,
            "reasoning_effort": None, "evidence_mode": "none",
        }
        self.env = patch.dict(os.environ, {"EVAL_TEST_SECRET": "fake-local-test-secret"})
        self.env.start()
        self.addCleanup(self.env.stop)
        # Unit tests never read credentials from the real checkout.
        local_env_patch = patch.object(ev, "load_project_environment")
        self.local_env_loader = local_env_patch.start()
        self.addCleanup(local_env_patch.stop)

    @staticmethod
    def case(identifier):
        return {"id": identifier, "language": "greek", "category": "grammar",
                "prompt": "Explain the supplied word.", "source_refs": [],
                "expected_behavior": "HIDDEN RUBRIC CANARY", "gold_answer": "HIDDEN GOLD CANARY",
                "human_review_criteria": [{"criterion": "HIDDEN CRITERION CANARY"}],
                "review_status": "unreviewed", "provided_evidence": "VISIBLE EVIDENCE ONLY"}

    def save_cases(self):
        self.dataset.write_text("".join(json.dumps(case) + "\n" for case in self.cases), encoding="utf-8")

    @staticmethod
    def response(payload, config, secret):
        return {"model": "test-revision-returned", "system_fingerprint": "test-fingerprint",
                "choices": [{"message": {"content": "An answer."}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 3000, "completion_tokens": 100,
                          "completion_tokens_details": {"reasoning_tokens": 30}}}

    def events(self):
        return ev.read_events(Path(self.config["run_dir"]) / "events.jsonl")

    def test_payload_allowlist_never_sends_gold_or_review_metadata(self):
        payload = ev.build_payload(self.cases[0], self.config)
        self.assertEqual(payload["messages"][1]["content"], self.cases[0]["prompt"])
        self.assertNotIn("HIDDEN", json.dumps(payload))
        self.assertNotIn("VISIBLE EVIDENCE", json.dumps(payload))
        self.config["evidence_mode"] = "provided"
        payload = ev.build_payload(self.cases[0], self.config)
        self.assertIn("VISIBLE EVIDENCE", json.dumps(payload))
        self.assertNotIn("HIDDEN", json.dumps(payload))

    def test_dry_run_never_reads_key_or_calls_network(self):
        self.config["input_price_per_million"] = None
        self.config["output_price_per_million"] = None
        self.config["budget_usd"] = None
        with patch.object(ev.os, "environ", {}) as environment, patch.object(ev, "send_request") as transport:
            result = ev.run(self.config)
        transport.assert_not_called()
        self.local_env_loader.assert_not_called()
        self.assertEqual(result["mode"], "dry_run")
        self.assertIsNone(result["remaining_worst_case_usd"])
        self.assertEqual(self.events(), [])
        manifest = json.loads((Path(self.config["run_dir"]) / "manifest.json").read_text())
        self.assertEqual(manifest["dataset_sha256"], ev.digest(self.dataset.read_bytes()))

    def test_execution_loads_local_environment_before_reading_key(self):
        os.environ.pop("EVAL_TEST_SECRET")
        self.local_env_loader.side_effect = lambda: os.environ.update(
            {"EVAL_TEST_SECRET": "fixture-loaded-key"}
        )

        def transport(payload, config, secret):
            self.assertEqual(secret, "fixture-loaded-key")
            return self.response(payload, config, secret)

        result = ev.run(self.config, execute=True, transport=transport)
        self.local_env_loader.assert_called_once_with()
        self.assertEqual(result["completed_cases"], 2)

    def test_unknown_or_nonfinite_price_fails_closed(self):
        for bad in (None, float("nan"), float("inf"), -1):
            self.config["input_price_per_million"] = bad
            with self.subTest(price=bad), patch.object(ev, "send_request") as transport:
                with self.assertRaises(ev.EvaluationError):
                    ev.run(self.config, execute=True)
                transport.assert_not_called()

    def test_budget_reserves_next_request_and_stops_before_sending(self):
        self.config["budget_usd"] = 0.005
        with patch.object(ev, "send_request", side_effect=self.response) as transport:
            result = ev.run(self.config, execute=True)
        self.assertEqual(transport.call_count, 1)
        self.assertEqual(result["stop_reason"], "budget_would_be_exceeded")
        self.assertAlmostEqual(result["accounted_cost_usd"], 0.0031)
        self.assertEqual([event["event"] for event in self.events()], ["started", "completed"])

    def test_tiny_budget_sends_no_request(self):
        self.config["budget_usd"] = 0.0001
        with patch.object(ev, "send_request") as transport:
            result = ev.run(self.config, execute=True)
        transport.assert_not_called()
        self.assertEqual(result["accounted_cost_usd"], 0)

    def test_remaining_reservation_tracks_pending_after_actual_execution(self):
        self.config["budget_usd"] = 0.005
        partial = ev.run(self.config, execute=True, transport=self.response)
        self.assertEqual(partial["pending_cases"], 1)
        self.assertAlmostEqual(partial["remaining_worst_case_usd"], partial["per_request_reservation_usd"])
        self.config.update(run_dir=str(self.root / "runs" / "complete"), budget_usd=0.02)
        complete = ev.run(self.config, execute=True, transport=self.response)
        self.assertEqual(complete["pending_cases"], 0)
        self.assertEqual(complete["remaining_worst_case_usd"], 0)

    def test_error_body_and_secret_never_reach_artifacts(self):
        secret = os.environ["EVAL_TEST_SECRET"]
        def failure(*args):
            raise urllib.error.HTTPError("https://example.invalid/" + secret, 401, secret, {}, None)
        result = ev.run(self.config, execute=True, transport=failure)
        self.assertEqual(result["stop_reason"], "uncertain_billing_or_provider_limit_breach")
        serialized = "".join(path.read_text() for path in Path(self.config["run_dir"]).glob("*.json*"))
        self.assertNotIn(secret, serialized)
        self.assertEqual(self.events()[-1]["error"], {"kind": "http_error", "status": 401})
        with self.assertRaises(ev.EvaluationError):
            ev.run(self.config, execute=True, resume=True, transport=self.response)

    def test_success_response_echoed_secret_is_redacted(self):
        def echoed(payload, config, secret):
            result = self.response(payload, config, secret)
            result["choices"][0]["message"]["content"] = "echo " + secret
            result["api_key"] = "another-sensitive-value"
            return result
        ev.run(self.config, execute=True, transport=echoed)
        data = (Path(self.config["run_dir"]) / "events.jsonl").read_text()
        self.assertNotIn(os.environ["EVAL_TEST_SECRET"], data)
        self.assertNotIn("another-sensitive-value", data)
        self.assertIn("[REDACTED]", data)

    def test_resume_dry_run_then_execution_and_completed_run_no_duplicate(self):
        ev.run(self.config)
        with patch.object(ev, "send_request", side_effect=self.response) as transport:
            ev.run(self.config, execute=True, resume=True)
            self.assertEqual(transport.call_count, 2)
        with patch.object(ev, "send_request") as transport:
            result = ev.run(self.config, execute=True, resume=True)
        transport.assert_not_called()
        self.assertEqual(result["pending_cases"], 0)

    def test_resume_refuses_dataset_changes(self):
        ev.run(self.config)
        self.cases[0]["prompt"] = "Changed prompt."
        self.save_cases()
        with self.assertRaises(ev.EvaluationError):
            ev.run(self.config, resume=True)

    def test_pending_request_is_not_retried_after_crash(self):
        ev.run(self.config)
        ev.append_event(Path(self.config["run_dir"]) / "events.jsonl",
                        {"event": "started", "case_id": "one", "reserved_cost_usd": 0.0031})
        with patch.object(ev, "send_request") as transport:
            with self.assertRaises(ev.EvaluationError):
                ev.run(self.config, execute=True, resume=True)
        transport.assert_not_called()

    def test_missing_usage_accounts_reservation_and_stops(self):
        def no_usage(*args):
            return {"choices": [{"message": {"content": "hello"}, "finish_reason": "stop"}]}
        result = ev.run(self.config, execute=True, transport=no_usage)
        self.assertAlmostEqual(result["accounted_cost_usd"], 0.0031)
        self.assertTrue(self.events()[-1]["accounting_uncertain"])
        self.assertEqual(len(self.events()), 2)

    def test_reasoning_is_part_of_output_and_truncation_is_recorded(self):
        def truncated(payload, config, secret):
            result = self.response(payload, config, secret)
            result["choices"][0]["finish_reason"] = "length"
            return result
        ev.run(self.config, execute=True, transport=truncated)
        event = self.events()[1]
        self.assertEqual(event["usage"]["reasoning_tokens"], 30)
        self.assertAlmostEqual(event["accounted_cost_usd"], 0.0031)
        self.assertTrue(event["truncated"])
        self.assertFalse(event["answer_complete"])

    def test_input_estimate_prevents_oversized_prompt_request(self):
        self.config["max_input_tokens"] = 300
        with patch.object(ev, "send_request") as transport:
            with self.assertRaises(ev.EvaluationError):
                ev.run(self.config, execute=True)
        transport.assert_not_called()

    def test_provider_limit_breach_stops_further_requests(self):
        def too_many(payload, config, secret):
            result = self.response(payload, config, secret)
            result["usage"]["completion_tokens"] = 101
            return result
        result = ev.run(self.config, execute=True, transport=too_many)
        self.assertTrue(self.events()[-1]["limit_breach"])
        self.assertEqual(result["pending_cases"], 1)

    def test_url_credentials_plain_http_and_redirect_are_refused(self):
        for url in ("http://example.invalid/v1", "https://name:secret@example.invalid", "https://example.invalid?key=secret"):
            self.config["base_url"] = url
            with self.subTest(url=url), self.assertRaises(ev.EvaluationError):
                ev.run(self.config)
        request = ev.urllib.request.Request("https://example.invalid")
        with self.assertRaises(urllib.error.HTTPError):
            ev.NoRedirect().redirect_request(request, None, 302, "redirect", {}, "https://elsewhere.invalid")

    def test_run_artifacts_cannot_be_written_outside_ignored_runs(self):
        self.config["run_dir"] = str(self.root / "public-docs")
        with self.assertRaises(ev.EvaluationError):
            ev.run(self.config)

    def test_provider_compatible_limit_field_is_explicit(self):
        self.config["output_limit_field"] = "max_tokens"
        payload = ev.build_payload(self.cases[0], self.config)
        self.assertEqual(payload["max_tokens"], 100)
        self.assertNotIn("max_completion_tokens", payload)

    def test_fixture_equality_checks_values_without_claiming_scholarship(self):
        case = {"automatic_checks": [{"id": "copy", "kind": "json_field_equals", "expected_fields": {"id": "a", "witness": None}, "scope": "provided_fixture_only"}]}
        self.assertEqual(ev.check_format(case, '{"id":"a","witness":null}')[0]["status"], "pass")
        self.assertEqual(ev.check_format(case, '{"id":"a"}')[0]["status"], "fail")

    def test_pilot_is_balanced_concrete_and_not_a_scholarly_gold_set(self):
        cases, _ = ev.load_cases(ev.DEFAULT_DATASET)
        self.assertEqual(len(cases), 40)
        self.assertEqual(sum(case["category"] == "translation" for case in cases), 3)
        for language in ("hebrew", "aramaic", "greek"):
            self.assertEqual(sum(case["language"] == language for case in cases), 12)
        self.assertTrue(all(case["source_refs"] and case["prompt"] for case in cases))
        for case in cases:
            if case["review_status"] == "unreviewed":
                self.assertIsNone(case["gold_answer"])
            for check in case["automatic_checks"]:
                self.assertIn(check["scope"], {"format_only", "provided_fixture_only"})
            self.assertTrue(all(criterion["review_status"] == "unreviewed" for criterion in case["human_review_criteria"]))


if __name__ == "__main__":
    unittest.main()
