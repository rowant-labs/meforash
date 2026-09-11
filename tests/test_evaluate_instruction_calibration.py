import copy
import json
import unittest
from unittest.mock import patch

from bibleprep import evaluate_instruction_calibration as subject
from tests import test_evaluate_instruction as fixtures


class CalibrationEvaluationTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.FourArmEvaluationTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.root = self.fixture.root
        self.write = self.fixture.write
        self.entry = self.fixture.entry
        data = (self.root / "evals/fresh.jsonl").read_bytes()
        for i in range(24, 30):
            data += fixtures.canonical({"id": f"T{i}", "prompt": "Return the constructed fixture.",
                "language": "english", "category": "general_retention", "source_refs": [],
                "expected_behavior": "Do not include this criterion in the prompt.",
                "review_status": "fixture", "provided_evidence": ""}) + b"\n"
        self.write("evals/new.jsonl", data)
        evaluation = {**self.entry("evals/new.jsonl"), "cases": 30, "case_ids": [f"T{i}" for i in range(30)]}
        self.write("manifests/new-evaluation.json", {"schema_version": 2,
            "status": "frozen_before_training_and_sampling", "dataset": evaluation})
        self.write("manifests/new-training.json", {"fixture": True})
        self.write("reports/prior-aggregate.json", {"fixture": True})
        software = {}
        for name in subject.REQUIRED_SOFTWARE:
            self.write(name, b"synthetic code identity")
            software[name] = self.fixture.hash(self.root / name)
        self.protocol = {"schema_version": 2, "status": "frozen_before_training_and_sampling",
            "experiment_id": "instruction-calibration-v2", "arms": subject.STATES,
            "evaluation": evaluation, "evaluation_manifest": self.entry("manifests/new-evaluation.json"),
            "training_manifest": self.entry("manifests/new-training.json"),
            "prior_protocol": self.entry(subject.previous.PROTOCOL),
            "prior_aggregate": self.entry("reports/prior-aggregate.json"),
            "system_prompt_sha256": subject.ev.digest(subject.ev.SYSTEM_PROMPT.encode()),
            "software_sha256": software,
            "matched_settings": copy.deepcopy(subject.MATCHED_SETTINGS),
            "reference_checkpoints": {}, "budget": copy.deepcopy(subject.BUDGET)}
        for arm, path in (("B", self.fixture.original), ("D", self.fixture.d)):
            self.protocol["reference_checkpoints"][arm] = {
                "checkpoint_file": str(path.relative_to(self.root)),
                "receipt_sha256": {name: self.fixture.hash(path.parent / name)
                    for name in ("checkpoints.json", "summary.json", "plan.json", "events.jsonl")}}
        self.save()

    def save(self):
        self.write(subject.PROTOCOL, self.protocol)

    def config(self):
        config = self.fixture.config()
        config.update(subject.MATCHED_SETTINGS)
        config.update(dataset=str(self.root / "evals/new.jsonl"), max_cases=30, budget_usd=1.5)
        return config

    def test_freeze_and_reference_identities(self):
        protocol, digest = subject.load_protocol(self.root)
        self.assertEqual(protocol, self.protocol)
        self.assertEqual(len(digest), 64)
        for arm, path in (("A", None), ("B", self.fixture.original), ("D", self.fixture.d)):
            identity = subject.verified_checkpoint(arm, path, protocol, self.root)
            self.assertEqual(identity is None, arm == "A")

    def test_changed_dataset_and_partial_selection_rejected(self):
        config = self.config()
        config["max_cases"] = 29
        with self.assertRaises(subject.ev.EvaluationError):
            subject.verified_dataset(config, self.protocol, self.root)
        path = self.root / "evals/new.jsonl"
        path.write_bytes(path.read_bytes() + b"\n")
        with self.assertRaises(subject.ev.EvaluationError):
            subject.verified_dataset(self.config(), self.protocol, self.root)

    def test_changed_software_or_system_prompt_rejected(self):
        for key in ("system_prompt_sha256",):
            self.protocol[key] = "0" * 64
            self.save()
            with self.assertRaises(subject.ev.EvaluationError): subject.load_protocol(self.root)
        self.protocol["system_prompt_sha256"] = subject.ev.digest(subject.ev.SYSTEM_PROMPT.encode())
        self.save()
        self.write("bibleprep/native_diagnostics_v1.py", b"changed")
        with self.assertRaises(subject.ev.EvaluationError): subject.load_protocol(self.root)

    def test_evaluation_manifest_disagreement_rejected(self):
        self.write("manifests/new-evaluation.json", {"schema_version": 2,
            "status": "frozen_before_training_and_sampling", "dataset": {"cases": 29}})
        self.protocol["evaluation_manifest"] = self.entry("manifests/new-evaluation.json")
        self.save()
        with self.assertRaises(subject.ev.EvaluationError): subject.load_protocol(self.root)

    def test_reference_location_and_receipt_changes_rejected(self):
        with self.assertRaises(subject.ev.EvaluationError):
            subject.verified_checkpoint("D", self.fixture.c, self.protocol, self.root)
        path = self.fixture.d.parent / "summary.json"
        path.write_bytes(path.read_bytes() + b"\n")
        with self.assertRaises(subject.ev.EvaluationError):
            subject.verified_checkpoint("D", self.fixture.d, self.protocol, self.root)

    def test_base_adapter_and_unverified_private_inputs_rejected(self):
        with self.assertRaises(subject.ev.EvaluationError):
            subject.verified_checkpoint("A", self.fixture.original, self.protocol, self.root)
        for field in subject.PRIVATE_FIELDS:
            config = self.config(); config[field] = "synthetic"
            with self.assertRaises(subject.ev.EvaluationError):
                subject.run(config, "B", self.fixture.original, root=self.root)

    def test_sampling_changes_and_excess_budget_stop_before_run(self):
        for field, value in (("seed", 10), ("reasoning_effort", "high"), ("budget_usd", 1.51),
                             ("input_price_per_million", 0.), ("output_price_per_million", 0.)):
            config = self.config(); config[field] = value
            with patch.object(subject.comparison, "configure", side_effect=dict), patch.object(subject.ev, "run") as run:
                with self.assertRaises(subject.ev.EvaluationError): subject.run(config, "A", root=self.root)
            run.assert_not_called()

    def test_missing_matched_field_cannot_relax_the_protocol(self):
        del self.protocol["matched_settings"]["seed"]
        self.save()
        with self.assertRaises(subject.ev.EvaluationError): subject.load_protocol(self.root)

    def test_changed_prior_aggregate_or_missing_reference_receipt_rejected(self):
        self.write("reports/prior-aggregate.json", {"changed": True})
        with self.assertRaises(subject.ev.EvaluationError): subject.load_protocol(self.root)
        del self.protocol["reference_checkpoints"]["D"]["receipt_sha256"]["events.jsonl"]
        with self.assertRaises(subject.ev.EvaluationError):
            subject.verified_checkpoint("D", self.fixture.d, self.protocol, self.root)

    def test_dry_planning_does_not_create_a_native_worker(self):
        for arm, path in (("A", None), ("B", self.fixture.original), ("D", self.fixture.d)):
            with patch.object(subject.comparison, "configure", side_effect=dict), \
                 patch.object(subject.native, "BoundedNativeTransport") as worker, \
                 patch.object(subject.ev, "run", return_value={"mode": "dry_run", "secret": "synthetic"}) as run:
                result = subject.run(self.config(), arm, path, root=self.root)
            worker.assert_not_called()
            self.assertEqual(result, {"mode": "dry_run"})
            configured = run.call_args.args[0]
            self.assertEqual(configured["experiment_arm"], arm)
            self.assertEqual("checkpoint_reference_file" in configured, arm != "A")
            self.assertFalse(run.call_args.kwargs["resume"])

    def test_explicit_transport_and_public_allowlist(self):
        transport = object()
        with patch.object(subject.comparison, "configure", side_effect=dict), \
             patch.object(subject.ev, "run", return_value={"mode": "execute", "completed_cases": 30,
                "adapter_sampler_path": "tinker://synthetic", "config": {"private": True}}) as run:
            result = subject.run(self.config(), "B", self.fixture.original, execute=True, transport=transport, root=self.root)
        self.assertIs(run.call_args.kwargs["transport"], transport)
        self.assertEqual(result, {"mode": "execute", "completed_cases": 30})

    def test_payload_never_includes_review_criteria(self):
        _, cases = subject.verified_dataset(self.config(), self.protocol, self.root)
        payload = subject.ev.build_payload(cases[-1], self.config())
        self.assertNotIn("Do not include this criterion", json.dumps(payload))


if __name__ == "__main__":
    unittest.main()
