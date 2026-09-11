import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from bibleprep import evaluate as ev
from bibleprep import summarize_adaptation as old
from bibleprep import summarize_instruction as report
from tests import test_evaluate_instruction as fixtures

canonical = fixtures.canonical


class InstructionSummaryTests(unittest.TestCase):
    def setUp(self):
        fixture = fixtures.FourArmEvaluationTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        self.fixture = fixture
        self.root = fixture.root
        self.write = fixture.write
        self.protocol = fixture.protocol
        self.cases = [json.loads(line) for line in (self.root / "evals/fresh.jsonl").read_bytes().splitlines()]
        for case in self.cases:
            case["prompt"] = "PRIVATE QUESTION CANARY"
            case["expected_behavior"] = "PRIVATE CRITERION CANARY"
        self.write("evals/fresh.jsonl", b"".join(canonical(case) + b"\n" for case in self.cases))
        dataset = {**fixture.entry("evals/fresh.jsonl"), "cases": 24, "case_ids": [case["id"] for case in self.cases]}
        self.write("manifests/eval.json", {"dataset": dataset})
        self.write("manifests/exclusions.json", {"status": "frozen", "evaluation_sha256": dataset["sha256"]})
        self.protocol.update(evaluation=dataset, allowed_datasets=[dataset],
                             evaluation_manifest=fixture.entry("manifests/eval.json"),
                             evaluation_exclusions=fixture.entry("manifests/exclusions.json"))
        fixture.save_protocol()
        artifacts = {}
        for name, counts in (("train", (104, 1000, 500)), ("validation", (16, 200, 100))):
            path = f"data/prepared/instruction-v1/{name}.jsonl"
            self.write(path, b"PRIVATE PREPARED TOKENS CANARY\n")
            artifacts[name] = {**fixture.entry(path), **dict(zip(("sequences", "processed_tokens", "loss_tokens"), counts))}
        path = "runs/reviewed-input.jsonl"
        self.write(path, b"PRIVATE REVIEWED DATA CANARY\n")
        self.preparation = {"schema_version": 1, "status": "prepared_not_trained", "model": report.raw.MODEL,
            "review_status": "ai_source_checked", "expert_certified": False, "thinking_effort_numeric": .7,
            "split": {"chapter_disjoint": True}, "artifacts": artifacts,
            "reviewed_dataset": {**fixture.entry(path), "examples": 120},
            "evaluation_exclusion": {"evaluation_sha256": dataset["sha256"]}}
        self.write(report.PREPARATION, self.preparation)
        self.training_dirs = {}
        for arm, source in (("C", None), ("D", fixture.source_identity)):
            self.training_dirs[arm] = self.make_training(arm, source)
        self.settings = {key: "synthetic" for key in old.SAMPLING_KEYS}
        self.settings.update(self.protocol["matched_settings"])
        self.settings.update(model_version="provider_revision_unpinned", output_limit_field="max_completion_tokens",
            renderer_profile="tml_v0", renderer="official_tml_renderers", hf_chat_template_used=False,
            tokenizer_sha256="1" * 64, chat_template_sha256="2" * 64, comparison_manifest_sha256="3" * 64,
            input_price_per_million=1.87, output_price_per_million=4.68,
            private_note="PRIVATE SETTINGS CANARY", private_path="/Users/PRIVATE/account")
        for arm in "ABCD":
            self.make_eval(arm)

    def metric(self, processed, tokens, nll, groups=False):
        value = {"processed_tokens": processed, "loss_tokens": float(tokens),
                 "weighted_nll": nll, "weighted_loss_sum": tokens * nll}
        value["by_language"] = ({language: {"processed_tokens": processed // 2, "loss_tokens": float(tokens // 2),
                                          "weighted_nll": nll, "weighted_loss_sum": tokens * nll / 2}
                                for language in ("hbo", "grc")} if groups else {"grc": dict(value)})
        return value

    def make_training(self, arm, source):
        directory = f"runs/inkling-instruction-{arm.lower()}-v1"
        recipe = {"model": report.raw.MODEL, "manifest_sha256": self.fixture.hash(self.root / report.PREPARATION),
                  "rank": 8, "epochs": 1, "batch_size": 16, "seed": 20260906,
                  "train_mlp": True, "train_attn": True, "train_unembed": True,
                  "thinking_effort_numeric": .7, "optimizer_initialization": "fresh",
                  "loss_fn": "cross_entropy", "optimization_loss_reduction": "sum",
                  "adam": {"learning_rate": 1e-4, "beta1": .9, "beta2": .95, "eps": 1e-8,
                           "weight_decay": 0., "grad_clip_norm": 0.}}
        compute = 1400 * report.raw.TOKEN_NANO
        plan = {"run_id": "PRIVATE TRAIN RUN " + arm, "phase": "instruction", "arm": arm,
                "recipe": recipe, "recipe_sha256": ev.digest(canonical(recipe)),
                "sequence_order_sha256": "4" * 64, "software_sha256": {"PRIVATE_PATH": "5" * 64},
                "training_sequences": 104, "training_processed_tokens": 1000, "training_loss_tokens": 500,
                "training_batches": 7, "holdout_sequences": 16, "two_holdout_forward_tokens": 400,
                "fresh_training_client": True, "fresh_adapter": arm == "C", "optimizer_restored": False,
                "source_adapter": source, "compute_reserve_nano_usd": compute,
                "checkpoint_reserve_nano_usd": 3_000_000_000, "planned_nano_usd": compute + 3_000_000_000,
                "planned_estimated_usd": (compute + 3_000_000_000) / 1e9, "checkpoint_ttl_seconds": 2592000}
        checkpoint = self.write(directory + "/checkpoints.json", {
            "sampler_path": f"tinker://PRIVATE-{arm}:train:0/sampler_weights/final",
            "training_state_path": f"tinker://PRIVATE-{arm}:train:0/weights/final"})
        before, after = self.metric(200, 100, .5, True), self.metric(200, 100, .4, True)
        summary = {"status": "complete", "phase": "instruction", "arm": arm, "run_id": plan["run_id"],
                   "recipe_sha256": plan["recipe_sha256"], "checkpoint_reference_sha256": self.fixture.hash(checkpoint),
                   "source_adapter": source, "optimizer_restored": False, "training_batches": 7,
                   "training_processed_tokens": 1000, "training_loss_tokens": 500,
                   "baseline_sft_validation": before, "end_sft_validation": after, "training_weighted_nll": .3}
        operations = [("create", "", None, None), ("verify_client", "", None, None)]
        if arm == "D":
            operations.extend([("verify_source", "", None, None), ("load_weights", "", None, None)])
        operations.append(("forward", "baseline_sft_validation", None, before))
        for step in range(1, 8):
            met = self.metric(142 if step < 7 else 148, 72 if step < 7 else 68, .3)
            operations.extend([("forward_backward", "instruction_training", step, met), ("optim", "instruction_training", step, None)])
        operations.extend([("forward", "end_sft_validation", None, after), ("state", "checkpoint", None, None), ("sampler", "checkpoint", None, None)])
        events = []
        for i, (op, stage, step, met) in enumerate(operations, 1):
            details = {"operation_id": i, "operation": op, "stage": stage, "step": step,
                       "processed_tokens": met["processed_tokens"] if met else 0, "reserved_nano_usd": 0}
            events.extend([{"event": "operation_reserved", **details}, {"event": "operation_complete", **details, "metrics": met}])
        events.append({"event": "run_complete", "run_id": plan["run_id"]})
        self.write(directory + "/plan.json", plan)
        self.write(directory + "/summary.json", summary)
        self.write(directory + "/events.jsonl", b"".join(canonical(event) + b"\n" for event in events))
        return self.root / directory

    def save_eval_manifest(self, arm, manifest):
        identity = {key: manifest[key] for key in ("dataset_sha256", "system_prompt_sha256", "settings", "case_ids", "schema_version")}
        manifest["fingerprint"] = ev.digest(ev.json_bytes(identity))
        self.write(f"runs/instruction-eval-{arm.lower()}-v1/manifest.json", manifest)

    def make_eval(self, arm):
        settings = copy.deepcopy(self.settings)
        settings.update(experiment_arm=arm, model_state=report.four.STATES[arm],
                        instruction_protocol_sha256=self.fixture.hash(self.root / report.four.PROTOCOL),
                        transport="native_tinker_comparison" if arm == "A" else "native_tinker_inkling_adapter")
        if arm != "A":
            path = self.fixture.original if arm == "B" else self.training_dirs[arm] / "checkpoints.json"
            checkpoint = json.loads(path.read_bytes())
            settings.update(adapter_sampler_path=checkpoint["sampler_path"], checkpoint_reference_sha256=self.fixture.hash(path))
        manifest = {"dataset_sha256": self.protocol["evaluation"]["sha256"],
                    "system_prompt_sha256": ev.digest(ev.SYSTEM_PROMPT.encode()), "settings": settings,
                    "case_ids": [case["id"] for case in self.cases], "schema_version": 1, "dry_run_at_creation": False}
        self.save_eval_manifest(arm, manifest)
        events = []
        for i, case in enumerate(self.cases):
            events.extend([{"event": "started", "case_id": case["id"], "reserved_cost_usd": .1},
                           {"event": "completed", "case_id": case["id"], "accounted_cost_usd": .001123,
                            "elapsed_seconds": 10 + i, "answer_complete": True, "finish_reason": "stop", "truncated": False,
                            "usage": {"input_tokens": 100, "output_tokens": 200}, "accounting_uncertain": False,
                            "raw_response_redacted": {"provider_private_id": "PRIVATE PROVIDER CANARY",
                                "choices": [{"message": {"content": "PRIVATE ANSWER CANARY " + arm}, "finish_reason": "stop"}],
                                "usage": {"prompt_tokens": 100, "completion_tokens": 200},
                                "native_tinker": {"prompt_sha256": ev.digest(case["id"].encode()), "analysis_content_tokens": None}}}])
        self.write_events(arm, events)

    def events(self, arm):
        return [json.loads(line) for line in (self.root / f"runs/instruction-eval-{arm.lower()}-v1/events.jsonl").read_bytes().splitlines()]

    def write_events(self, arm, events):
        self.write(f"runs/instruction-eval-{arm.lower()}-v1/events.jsonl", b"".join(canonical(event) + b"\n" for event in events))

    def test_complete_safe_aggregate_has_real_totals_without_guessing_channels(self):
        with patch.object(ev, "load_cases", side_effect=AssertionError("Normal report must not parse questions")), \
             patch.object(ev, "load_project_environment") as environment, patch.object(ev, "send_request") as network:
            result = report.summarize(self.root)
        environment.assert_not_called(); network.assert_not_called()
        self.assertEqual(result["status"], "complete")
        self.assertEqual(result["comparison_validation"]["returned_four_arm_prompt_groups_verified"], 24)
        self.assertEqual(result["english_evaluation"]["D"]["counts"]["complete_answers"], 24)
        self.assertEqual(result["english_evaluation"]["D"]["tokens"], {"input": 2400, "output": 4800, "analysis_content": None, "final_content": None})
        self.assertEqual(result["english_evaluation"]["D"]["latency_seconds"]["median"], 21.5)
        self.assertAlmostEqual(result["training"]["D"]["validation_nll_change"], -.1)
        self.assertEqual(result["training"]["C"]["baseline_sft_validation"]["by_language"]["hebrew"]["loss_tokens"], 50)
        self.assertAlmostEqual(result["cost"]["selected_scope_estimated_or_reserved_usd"], 6.123516)
        serialized = json.dumps(result)
        # Match the private case ID as a JSON string; UTC timestamps contain T0.
        for canary in ("PRIVATE", "tinker://", "/Users/", str(self.root), '"T0"', "sampler_path"):
            self.assertNotIn(canary, serialized)

    def test_missing_response_tail_and_output_limit_are_incomplete(self):
        events = self.events("D")
        events[-1]["answer_complete"] = False
        events[-1]["finish_reason"] = "length"
        events[-1]["truncated"] = True
        events[-1]["raw_response_redacted"]["choices"][0]["finish_reason"] = "length"
        self.write_events("D", events)
        result = report.summarize(self.root)
        self.assertEqual(result["status"], "complete_with_incomplete_answers")
        self.assertTrue(result["execution_complete"])
        self.assertFalse(result["partial"])
        self.assertEqual(result["english_evaluation"]["D"]["counts"]["incomplete_answers"], 1)
        self.write_events("D", events[:-1])
        path = self.root / "runs/instruction-eval-d-v1/events.jsonl"
        path.write_bytes(path.read_bytes() + b'{"unfinished":')
        result = report.summarize(self.root)
        self.assertTrue(result["partial"])
        self.assertEqual(result["english_evaluation"]["D"]["counts"]["unresolved"], 1)

    def test_changed_dataset_hash_and_prompt_tokens_fail(self):
        path = self.root / "evals/fresh.jsonl"; before = path.read_bytes()
        path.write_bytes(before + b"\n")
        with self.assertRaises(ev.EvaluationError): report.summarize(self.root)
        path.write_bytes(before)
        events = self.events("C"); events[1]["raw_response_redacted"]["native_tinker"]["prompt_sha256"] = "9" * 64
        self.write_events("C", events)
        with self.assertRaisesRegex(ev.EvaluationError, "different prompt tokens"): report.summarize(self.root)

    def test_changed_settings_arm_or_checkpoint_fail_even_with_rehashed_manifest(self):
        path = self.root / "runs/instruction-eval-c-v1/manifest.json"
        original = json.loads(path.read_bytes())
        for key, value in (("seed", 1), ("experiment_arm", "D"), ("adapter_sampler_path", "tinker://OTHER/sampler_weights/test"), ("thinking_effort_numeric", .9)):
            manifest = copy.deepcopy(original); manifest["settings"][key] = value
            self.save_eval_manifest("C", manifest)
            with self.subTest(key=key), self.assertRaises(ev.EvaluationError): report.summarize(self.root)
        self.save_eval_manifest("C", original)
        manifest = copy.deepcopy(original); manifest["system_prompt_sha256"] = "7" * 64
        self.save_eval_manifest("C", manifest)
        with self.assertRaisesRegex(ev.EvaluationError, "system prompt"): report.summarize(self.root)

    def test_instruction_order_recipe_and_validation_metric_corruption_fail(self):
        path = self.training_dirs["D"] / "plan.json"; before = path.read_bytes()
        plan = json.loads(before); plan["sequence_order_sha256"] = "9" * 64; path.write_bytes(canonical(plan))
        with self.assertRaisesRegex(ev.EvaluationError, "identical instruction recipe"): report.summarize(self.root)
        path.write_bytes(before)
        path = self.training_dirs["D"] / "summary.json"
        summary = json.loads(path.read_bytes()); summary["end_sft_validation"]["by_language"]["hbo"]["weighted_loss_sum"] += 1
        path.write_bytes(canonical(summary))
        with self.assertRaises(ev.EvaluationError): report.summarize(self.root)

    def test_validation_summary_must_match_journal(self):
        path = self.training_dirs["C"] / "summary.json"
        summary = json.loads(path.read_bytes()); summary["end_sft_validation"] = self.metric(200, 100, .3, True)
        path.write_bytes(canonical(summary))
        with self.assertRaisesRegex(ev.EvaluationError, "forward journal"): report.summarize(self.root)

    def test_missing_usage_remains_unknown_and_uncertain(self):
        events = self.events("A"); events[1]["usage"] = None; events[1]["accounted_cost_usd"] = .1
        self.write_events("A", events)
        result = report.summarize(self.root)
        self.assertEqual(result["status"], "complete_with_errors")
        self.assertEqual(result["english_evaluation"]["A"]["counts"]["missing_usage"], 1)
        self.assertAlmostEqual(result["english_evaluation"]["A"]["cost"]["uncertain_accounted_or_reserved_usd"], .1)

    def test_no_training_receipt_cannot_back_a_completed_adapter_eval(self):
        (self.training_dirs["C"] / "summary.json").unlink()
        with self.assertRaisesRegex(ev.EvaluationError, "completed, verified"): report.summarize(self.root)
        directory = self.root / "runs/instruction-eval-c-v1"
        for path in directory.iterdir(): path.unlink()
        result = report.summarize(self.root)
        self.assertEqual(result["status"], "incomplete")
        self.assertEqual(result["training"]["C"]["status"], "in_progress")
        self.assertEqual(result["english_evaluation"]["C"]["counts"]["not_started"], 24)

    def test_private_review_requires_all_96_and_omits_operational_metadata(self):
        result, snapshots, dataset = report.collect(self.root)
        result["status"] = "incomplete"
        with self.assertRaises(ev.EvaluationError): report.prepare_review(result, snapshots, dataset, self.root)
        self.assertFalse((self.root / report.REVIEW).exists())
        result["status"] = "complete"
        count = report.prepare_review(result, snapshots, dataset, self.root)
        self.assertEqual(count["answers"], 96)
        directory = self.root / report.REVIEW
        content = (directory / "cases.jsonl").read_text()
        self.assertIn("PRIVATE QUESTION CANARY", content)
        self.assertIn("PRIVATE CRITERION CANARY", content)
        self.assertIn("PRIVATE ANSWER CANARY", content)
        for unwanted in ("PRIVATE PROVIDER CANARY", "tinker://", "input_tokens", "elapsed_seconds", "model_state", "instruction_only"):
            self.assertNotIn(unwanted, content)
        rows = [json.loads(line) for line in content.splitlines()]
        self.assertEqual(len(rows), 24)
        self.assertTrue(all(set(answer["candidate"] for answer in row["answers"]) == set("WXYZ") for row in rows))
        self.assertEqual((directory / "private-label-key.json").stat().st_mode & 0o777, 0o600)

    def test_actual_checkpoint_reference_swap_is_rejected(self):
        source = self.training_dirs["D"] / "checkpoints.json"
        (self.training_dirs["C"] / "checkpoints.json").write_bytes(source.read_bytes())
        with self.assertRaises(ev.EvaluationError): report.summarize(self.root)

    def test_three_truncated_candidates_including_empty_and_long_final_are_retained(self):
        events = self.events("D")
        long_answer = "Retain every character. " * 2000
        for index, answer in ((1, ""), (3, "A partial answer"), (5, long_answer)):
            events[index]["answer_complete"] = False
            events[index]["finish_reason"] = "length"
            events[index]["truncated"] = True
            events[index]["raw_response_redacted"]["choices"][0].update(
                message={"content": answer}, finish_reason="length")
        self.write_events("D", events)
        result, snapshots, dataset = report.collect(self.root)
        self.assertEqual(result["status"], "complete_with_incomplete_answers")
        self.assertTrue(result["execution_complete"])
        self.assertFalse(result["partial"])
        self.assertEqual(result["english_evaluation"]["D"]["counts"]["complete_answers"], 21)
        report.prepare_review(result, snapshots, dataset, self.root)
        directory = self.root / report.REVIEW
        rows = [json.loads(line) for line in (directory / "cases.jsonl").read_bytes().splitlines()]
        candidates = [answer for row in rows for answer in row["answers"]]
        self.assertEqual(len(candidates), 96)
        truncated = [answer for answer in candidates if not answer["answer_complete"]]
        self.assertEqual(len(truncated), 3)
        self.assertEqual({answer["finish_reason"] for answer in truncated}, {"length"})
        self.assertEqual({answer["output_tokens"] for answer in truncated}, {200})
        self.assertEqual({answer["answer"] for answer in truncated}, {"", "A partial answer", long_answer})


if __name__ == "__main__":
    unittest.main()
