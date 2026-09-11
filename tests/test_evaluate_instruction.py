import copy
import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from bibleprep import evaluate_instruction as subject


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False,
                      separators=(",", ":")).encode()


class FourArmEvaluationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.write("evals/fresh.jsonl", b"".join(canonical({"id": f"T{i}", "prompt": "Synthetic question.",
            "language": "mixed", "category": "fixture", "source_refs": [],
            "expected_behavior": "Fixture only.", "review_status": "fixture", "provided_evidence": ""}) + b"\n" for i in range(24)))
        dataset = {**self.entry("evals/fresh.jsonl"), "cases": 24, "case_ids": [f"T{i}" for i in range(24)]}
        self.write("manifests/eval.json", {"dataset": dataset})
        self.write("manifests/exclusions.json", {"status": "frozen", "evaluation_sha256": dataset["sha256"]})
        self.original = self.receipt("B", legacy=True)
        original_dir = self.original.parent
        plan = json.loads((original_dir / "plan.json").read_bytes())
        self.write("reports/original.json", {"training": {"development_pass": {
            "provenance": {"plan_sha256": self.hash(original_dir / "plan.json"),
                           "summary_sha256": self.hash(original_dir / "summary.json")},
            **{key: plan[key] for key in ("recipe_sha256", "training_batches", "training_processed_tokens", "training_loss_tokens")}}}})
        manifests = []
        for letter in "abc":
            path = f"runs/previous-{letter}/manifest.json"
            checkpoint = json.loads(self.original.read_bytes())
            self.write(path, {"case_ids": [letter], "dry_run_at_creation": False,
                "settings": {"model": "thinkingmachines/Inkling", "transport": "native_tinker_inkling_adapter",
                    "adapter_sampler_path": checkpoint["sampler_path"],
                    "checkpoint_reference_sha256": self.hash(self.original)}})
            self.write(f"runs/previous-{letter}/events.jsonl", canonical({"event": "completed", "case_id": letter, "answer_complete": True}) + b"\n")
            manifests.append(self.entry(path))
        self.protocol = {"schema_version": 1, "status": "frozen_before_sampling", "arms": subject.STATES,
            "evaluation_manifest": self.entry("manifests/eval.json"),
            "evaluation_exclusions": self.entry("manifests/exclusions.json"),
            "evaluation": dataset, "allowed_datasets": [dataset],
            "matched_settings": {"model": "thinkingmachines/Inkling", "reasoning_effort": "medium",
                "thinking_effort_numeric": .7, "temperature": 0., "seed": 20260905,
                "max_output_tokens": 8192, "max_input_tokens": 6000, "timeout_seconds": 300,
                "evidence_mode": "provided"},
            "original_text_receipt": {"checkpoint_file": str(self.original.relative_to(self.root)),
                "public_report": self.entry("reports/original.json"),
                "events_sha256": self.hash(original_dir / "events.jsonl"),
                "completed_adapter_evaluation_manifests": manifests}}
        self.save_protocol()
        self.source_identity = subject.verified_original(self.original, self.protocol, self.root)[2]
        self.c = self.receipt("C")
        self.d = self.receipt("D", source=self.source_identity)

    def write(self, path, value):
        path = self.root / path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(value if isinstance(value, bytes) else canonical(value))
        return path

    def hash(self, path):
        return subject.ev.digest(Path(path).read_bytes())

    def entry(self, path):
        return {"path": path, "sha256": self.hash(self.root / path)}

    def save_protocol(self):
        self.write(subject.PROTOCOL, self.protocol)

    def receipt(self, arm, source=None, legacy=False):
        directory = f"runs/arm-{arm}"
        recipe = {"model": "thinkingmachines/Inkling", "rank": 8}
        batches = 136 if legacy else 7
        plan = {"run_id": "fixture-" + arm, "phase": "full" if legacy else "instruction", "arm": arm,
            "recipe": recipe, "recipe_sha256": subject.ev.digest(canonical(recipe)),
            "training_batches": batches, "training_processed_tokens": 3280433 if legacy else 1000,
            "training_loss_tokens": 3229825 if legacy else 500., "source_adapter": source,
            "fresh_training_client": True, "fresh_adapter": legacy or arm == "C", "optimizer_restored": False}
        checkpoint = self.write(directory + "/checkpoints.json", {
            "sampler_path": f"tinker://synthetic-{arm}:train:0/sampler_weights/final",
            "training_state_path": f"tinker://synthetic-{arm}:train:0/weights/final"})
        summary = {key: value for key, value in plan.items() if key not in ("recipe", "fresh_training_client", "fresh_adapter")}
        summary.update(status="complete", checkpoint_reference_sha256=self.hash(checkpoint))
        self.write(directory + "/plan.json", plan)
        self.write(directory + "/summary.json", summary)
        operations = ["create"] + [name for _ in range(batches) for name in ("forward_backward", "optim")] + ["state", "sampler"]
        events = []
        for i, operation in enumerate(operations, 1):
            details = {"operation_id": i, "operation": operation, "stage": "fixture", "step": None,
                       "processed_tokens": 0, "reserved_nano_usd": 0}
            events.extend([{"event": "operation_reserved", **details}, {"event": "operation_complete", **details}])
        events.append({"event": "run_complete", **({} if legacy else {"run_id": plan["run_id"]})})
        self.write(directory + "/events.jsonl", b"".join(canonical(event) + b"\n" for event in events))
        return checkpoint

    def config(self):
        return {**self.protocol["matched_settings"], "dataset": str(self.root / "evals/fresh.jsonl"),
            "max_cases": 24, "base_url": subject.native.TINKER_URL,
            "run_dir": str(self.root / "runs/dry-check"), "api_key_env": "SYNTHETIC_KEY",
            "input_price_per_million": 1.87, "output_price_per_million": 4.68, "budget_usd": 2.}

    def verify(self, arm, path):
        return subject.verified_checkpoint(arm, path, protocol=self.protocol, root=self.root)

    def test_all_valid_receipts_and_legacy_B(self):
        self.assertIsNone(self.verify("A", None))
        for arm, path in (("B", self.original), ("C", self.c), ("D", self.d)):
            self.assertEqual(self.verify(arm, path)[1], self.hash(path))

    def test_unchanged_rejects_checkpoint(self):
        with self.assertRaises(subject.ev.EvaluationError):
            self.verify("A", self.c)

    def test_instruction_arm_label_mismatch(self):
        with self.assertRaises(subject.ev.EvaluationError):
            self.verify("D", self.c)

    def test_swapped_checkpoint_bytes_rejected(self):
        self.c.write_bytes(self.d.read_bytes())
        with self.assertRaises(subject.ev.EvaluationError):
            self.verify("C", self.c)

    def test_wrong_source_parent_rejected_even_when_plan_and_summary_match(self):
        for name in ("plan.json", "summary.json"):
            path = self.d.parent / name
            row = json.loads(path.read_bytes())
            row["source_adapter"]["receipt_sha256"]["checkpoints.json"] = "0" * 64
            path.write_bytes(canonical(row))
        with self.assertRaises(subject.ev.EvaluationError):
            self.verify("D", self.d)

    def test_C_cannot_claim_original_source_parent(self):
        for name in ("plan.json", "summary.json"):
            path = self.c.parent / name
            row = json.loads(path.read_bytes()); row["source_adapter"] = self.source_identity
            path.write_bytes(canonical(row))
        with self.assertRaises(subject.ev.EvaluationError):
            self.verify("C", self.c)

    def test_wrong_run_id_and_recipe_fail(self):
        for field, value in (("run_id", "different"), ("recipe_sha256", "0" * 64)):
            path = self.c.parent / "summary.json"; initial = path.read_bytes()
            row = json.loads(initial); row[field] = value; path.write_bytes(canonical(row))
            with self.assertRaises(subject.ev.EvaluationError): self.verify("C", self.c)
            path.write_bytes(initial)

    def test_journal_requires_terminal_matching_run(self):
        path = self.d.parent / "events.jsonl"
        rows = [json.loads(line) for line in path.read_bytes().splitlines()]
        rows[-1]["run_id"] = "different"
        path.write_bytes(b"".join(canonical(row) + b"\n" for row in rows))
        with self.assertRaises(subject.ev.EvaluationError): self.verify("D", self.d)

    def test_journal_uncertain_operation_is_not_completion(self):
        path = self.c.parent / "events.jsonl"
        rows = [json.loads(line) for line in path.read_bytes().splitlines()]
        rows[3]["event"] = "operation_uncertain"
        path.write_bytes(b"".join(canonical(row) + b"\n" for row in rows))
        with self.assertRaises(subject.ev.EvaluationError): self.verify("C", self.c)

    def test_B_checkpoint_hash_must_agree_with_all_previous_runs(self):
        self.original.write_bytes(self.c.read_bytes())
        with self.assertRaises(subject.ev.EvaluationError): self.verify("B", self.original)

    def test_B_summary_is_bound_to_public_provenance(self):
        path = self.original.parent / "summary.json"
        row = json.loads(path.read_bytes()); row["extra"] = "changed"
        path.write_bytes(canonical(row))
        with self.assertRaises(subject.ev.EvaluationError): self.verify("B", self.original)

    def test_private_receipt_cannot_escape_runs(self):
        path = self.write("outside/checkpoints.json", self.c.read_bytes())
        with self.assertRaises(subject.ev.EvaluationError): self.verify("C", path)

    def test_symlinked_summary_rejected(self):
        path = self.c.parent / "summary.json"; data = path.read_bytes(); path.unlink()
        target = self.write("runs/copied-summary.json", data); path.symlink_to(target)
        with self.assertRaises(subject.ev.EvaluationError): self.verify("C", self.c)

    def test_tampered_dataset_rejected_before_transport(self):
        with (self.root / "evals/fresh.jsonl").open("ab") as file: file.write(b"\n")
        with patch.object(subject.native, "BoundedNativeTransport") as worker:
            with self.assertRaises(subject.ev.EvaluationError): subject.run(self.config(), "A", root=self.root)
        worker.assert_not_called()

    def test_unknown_path_and_subset_are_rejected(self):
        config = self.config(); config["max_cases"] = 12
        with self.assertRaises(subject.ev.EvaluationError): subject.verified_dataset(config, self.protocol, self.root)
        config = self.config(); config["dataset"] = str(self.write("evals/copy.jsonl", (self.root / "evals/fresh.jsonl").read_bytes()))
        with self.assertRaises(subject.ev.EvaluationError): subject.verified_dataset(config, self.protocol, self.root)

    def test_changed_settings_fail_before_transport(self):
        config = self.config(); config["seed"] = 1
        with patch.object(subject.comparison, "configure", side_effect=dict), patch.object(subject.native, "BoundedNativeTransport") as worker:
            with self.assertRaises(subject.ev.EvaluationError): subject.run(config, "A", root=self.root)
        worker.assert_not_called()

    def test_routes_workers_and_allowlists_public_output(self):
        for arm, path in (("A", None), ("B", self.original), ("C", self.c), ("D", self.d)):
            with patch.object(subject.comparison, "configure", side_effect=dict), \
                 patch.object(subject.native, "BoundedNativeTransport") as worker, \
                 patch.object(subject.ev, "run", return_value={"mode": "dry_run", "config": {"private": "value"}, "sampler_path": "tinker://synthetic"}) as call:
                result = subject.run(self.config(), arm, path, root=self.root)
            self.assertEqual(result, {"mode": "dry_run"})
            self.assertIs(worker.call_args.kwargs["worker"], subject.comparison.sampling_worker if arm == "A" else subject.adapter.worker)
            actual = call.call_args.args[0]
            self.assertEqual(actual["experiment_arm"], arm)
            self.assertEqual("adapter_sampler_path" in actual, arm != "A")
            self.assertFalse(call.call_args.kwargs["execute"])
            worker.return_value.close.assert_called_once()

    def test_dry_run_never_loads_environment_or_starts_worker(self):
        with patch.object(subject.ev, "RUNS_ROOT", self.root / "runs"), \
             patch.object(subject.ev, "load_project_environment", side_effect=AssertionError("No credentials")) as environment, \
             patch.object(subject.comparison, "configure", side_effect=dict), \
             patch.object(subject.native.multiprocessing, "get_context", side_effect=AssertionError("No worker")) as process:
            result = subject.run(self.config(), "C", self.c, root=self.root)
        self.assertEqual(result["mode"], "dry_run")
        self.assertEqual(result["selected_cases"], 24)
        environment.assert_not_called(); process.assert_not_called()

    def test_main_errors_do_not_print_private_exception(self):
        error = io.StringIO()
        with patch.object(subject, "run", side_effect=ValueError("tinker://synthetic-private-ref")), contextlib.redirect_stderr(error):
            code = subject.main(["--arm", "A", "--dataset", "fixture.jsonl"])
        self.assertEqual(code, 2)
        self.assertNotIn("tinker://", error.getvalue())


if __name__ == "__main__":
    unittest.main()
