import copy
import json
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from bibleprep import evaluate_instruction_revision as subject
from tests import test_evaluate_instruction_calibration as fixtures


class RevisionEvaluationTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.CalibrationEvaluationTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.root, self.write, self.entry = self.fixture.root, self.fixture.write, self.fixture.entry
        self.write(subject.DATASET, (self.root / "evals/new.jsonl").read_bytes())
        self.cases, _ = subject.ev.load_cases(self.root / subject.DATASET)
        evaluation = {**self.entry(subject.DATASET), "cases": 30, "case_ids": [r["id"] for r in self.cases]}
        self.write(subject.EVALUATION_MANIFEST, {"schema_version": 3,
            "status": "frozen_before_training_and_sampling", "dataset": evaluation})
        self.write("manifests/prepared-v3.json", {"fixture": True})
        self.write("runs/frozen-v3.json", {"fixture": True})
        self.training = {"schema_version": 3, "status": "frozen_training_recipe",
            "experiment_id": "instruction-target-revision-v3", "arm": "F", "parent_arm": "B",
            "planned_nano_usd": 3489455670, "preparation": self.entry("manifests/prepared-v3.json")}
        self.write(subject.TRAINING, self.training)
        software = {}
        for name in subject.REQUIRED_SOFTWARE:
            self.write(name, b"synthetic code identity")
            software[name] = self.fixture.fixture.hash(self.root / name)
        self.write("runs/provider-preflight.json", {"private": "synthetic-availability"})
        self.preflight = {"schema_version": 3, "status": "verified_before_paid_v3_execution",
            "model": subject.MATCHED_SETTINGS["model"], "pricing": {"input_usd_per_million": 1.87,
                "output_usd_per_million": 4.68, "training_usd_per_million": 5.61,
                "rates_rechecked_before_run": True},
            "provider_checkpoint_check": {**self.entry("runs/provider-preflight.json"), "read_only": True,
                "verified_arms": ["B", "E"], "training_and_sampler_checkpoints_present": True,
                "all_checked_checkpoints_unexpired": True, "all_checked_checkpoints_private": True,
                "B_base_model_rank_and_components_match": True}}
        self.write(subject.PREFLIGHT, self.preflight)
        self.review = {"schema_version": 3, "status": "frozen_preoutput_criteria_review_complete",
            "expert_certified": False, "evaluation": self.entry(subject.DATASET),
            "evaluation_manifest": self.entry(subject.EVALUATION_MANIFEST),
            "preparation_manifest": self.training["preparation"], "dataset_freeze": self.entry("runs/frozen-v3.json"),
            "counts": {"cases": 30, "material_prompt_defects": 0},
            "global_scoring_supplement": ["Do not require this fixture note in a model answer."],
            "cases": [{"id": case["id"], "case_sha256": subject.ev.digest(subject._canonical(case)),
                "status": "approved", "scoring_caveats": ["Accept correct equivalents."], "source_urls": []}
                for case in self.cases], "review_receipts": []}
        for n, rows in enumerate((self.review["cases"][:13], self.review["cases"][13:])):
            path = f"runs/pre-output-{n}.json"
            self.write(path, {"status": "approved", "expert_certified": False, "reviewer": f"reviewer-{n}",
                "evaluation_sha256": evaluation["sha256"], "cases": copy.deepcopy(rows)})
            self.review["review_receipts"].append({**self.entry(path), "cases": len(rows), "reviewer": f"reviewer-{n}"})
        self.write(subject.CRITERIA_REVIEW, self.review)
        self.protocol = {"schema_version": 3, "status": "frozen_before_training_and_sampling",
            "experiment_id": "instruction-target-revision-v3", "arms": subject.STATES,
            "evaluation": evaluation, "evaluation_manifest": self.entry(subject.EVALUATION_MANIFEST),
            "training_manifest": self.entry(subject.TRAINING), "criteria_review": self.entry(subject.CRITERIA_REVIEW),
            "preflight": self.entry(subject.PREFLIGHT), "prior_protocol": self.entry(subject.calibration.PROTOCOL),
            "prior_aggregate": self.fixture.protocol["prior_aggregate"], "software_sha256": software,
            "system_prompt_sha256": subject.ev.digest(subject.ev.SYSTEM_PROMPT.encode()),
            "matched_settings": copy.deepcopy(subject.MATCHED_SETTINGS), "budget": copy.deepcopy(subject.BUDGET),
            "sampling_seed_decision": copy.deepcopy(subject.SEED_DECISION),
            "planned_f_checkpoint_file": subject.F_CHECKPOINT, "run_directories": subject.RUN_DIRECTORIES,
            "reference_checkpoints": {}}
        for arm, location in subject.REFERENCE_FILES.items():
            for name in subject.RECEIPT_FILES:
                self.write(str(Path(location).parent / name), (self.fixture.fixture.original.parent / name).read_bytes())
            self.protocol["reference_checkpoints"][arm] = {"checkpoint_file": location,
                "receipt_sha256": {name: self.fixture.fixture.hash(self.root / Path(location).parent / name)
                    for name in subject.RECEIPT_FILES}}
        self.save()
        self.addCleanup(patch.stopall)
        patch.object(subject.ev, "RUNS_ROOT", self.root / "runs").start()
        self.old_verifier = patch.object(subject.previous, "verified_checkpoint",
            return_value=("tinker://synthetic-B", "b" * 64)).start()
        self.e_verifier = patch("bibleprep.train_instruction_calibration.verify_completed_checkpoint",
            return_value=("tinker://synthetic-E", "e" * 64)).start()
        self.f_verifier = Mock(return_value=("tinker://synthetic-F", "f" * 64))
        patch.dict(sys.modules, {"bibleprep.train_instruction_revision":
            SimpleNamespace(verify_completed_checkpoint=self.f_verifier)}).start()

    def save(self):
        self.write(subject.PROTOCOL, self.protocol)

    def save_review(self):
        self.write(subject.CRITERIA_REVIEW, self.review)
        self.protocol["criteria_review"] = self.entry(subject.CRITERIA_REVIEW)
        self.save()

    def config(self, arm="A"):
        config = self.fixture.config()
        config.update(subject.MATCHED_SETTINGS)
        config.update(dataset=str(self.root / subject.DATASET), max_cases=30, budget_usd=1.5,
                      run_dir=str(self.root / subject.RUN_DIRECTORIES[arm]))
        return config

    def test_full_freeze_loads_without_f_checkpoint(self):
        protocol, digest = subject.load_protocol(self.root)
        self.assertEqual(protocol, self.protocol)
        self.assertEqual(len(digest), 64)
        self.assertFalse((self.root / subject.F_CHECKPOINT).exists())
        self.f_verifier.assert_not_called()

    def test_changed_dataset_and_selective_cases_rejected(self):
        config = self.config(); config["max_cases"] = 29
        with self.assertRaises(subject.ev.EvaluationError):
            subject.verified_dataset(config, self.protocol, self.root)
        path = self.root / subject.DATASET; path.write_bytes(path.read_bytes() + b"\n")
        with self.assertRaises(subject.ev.EvaluationError): subject.load_protocol(self.root)

    def test_frozen_seed_budget_and_run_locations_cannot_change(self):
        original = copy.deepcopy(self.protocol)
        for key, value in (("sampling_seed_decision", {}), ("budget", {}),
                           ("run_directories", {}), ("planned_f_checkpoint_file", "runs/other/checkpoints.json"),
                           ("matched_settings", {**subject.MATCHED_SETTINGS, "seed": 20260906})):
            self.protocol = {**original, key: value}; self.save()
            with self.subTest(key=key), self.assertRaises(subject.ev.EvaluationError): subject.load_protocol(self.root)

    def test_changed_software_and_system_prompt_rejected(self):
        self.protocol["system_prompt_sha256"] = "0" * 64; self.save()
        with self.assertRaises(subject.ev.EvaluationError): subject.load_protocol(self.root)
        self.protocol["system_prompt_sha256"] = subject.ev.digest(subject.ev.SYSTEM_PROMPT.encode()); self.save()
        self.write("bibleprep/native_diagnostics_v1.py", b"changed")
        with self.assertRaises(subject.ev.EvaluationError): subject.load_protocol(self.root)

    def test_wrong_training_identity_even_with_updated_file_hash_rejected(self):
        self.training["arm"] = "E"; self.write(subject.TRAINING, self.training)
        self.protocol["training_manifest"] = self.entry(subject.TRAINING); self.save()
        with self.assertRaises(subject.ev.EvaluationError): subject.load_protocol(self.root)

    def test_missing_or_unapproved_review_rejected(self):
        self.review["cases"][0]["status"] = "draft"; self.save_review()
        with self.assertRaises(subject.ev.EvaluationError): subject.load_protocol(self.root)
        self.review["cases"][0]["status"] = "approved"; self.review["cases"].pop(); self.save_review()
        with self.assertRaises(subject.ev.EvaluationError): subject.load_protocol(self.root)

    def test_review_case_hash_and_separate_caveat_bindings(self):
        self.review["cases"][0]["case_sha256"] = "0" * 64; self.save_review()
        with self.assertRaises(subject.ev.EvaluationError): subject.load_protocol(self.root)
        self.review["cases"][0]["case_sha256"] = subject.ev.digest(subject._canonical(self.cases[0]))
        self.review["cases"][0]["scoring_caveats"] = ["New post-output demand."]; self.save_review()
        with self.assertRaises(subject.ev.EvaluationError): subject.load_protocol(self.root)

    def test_changed_separate_review_receipt_rejected(self):
        self.write("runs/pre-output-0.json", {"changed": True})
        with self.assertRaises(subject.ev.EvaluationError): subject.load_protocol(self.root)

    def test_preflight_price_and_private_receipt_changes_rejected(self):
        self.preflight["pricing"]["input_usd_per_million"] = 0.; self.write(subject.PREFLIGHT, self.preflight)
        self.protocol["preflight"] = self.entry(subject.PREFLIGHT); self.save()
        with self.assertRaises(subject.ev.EvaluationError): subject.load_protocol(self.root)
        self.preflight["pricing"]["input_usd_per_million"] = 1.87; self.write(subject.PREFLIGHT, self.preflight)
        self.protocol["preflight"] = self.entry(subject.PREFLIGHT); self.save()
        self.write("runs/provider-preflight.json", {"changed": True})
        with self.assertRaises(subject.ev.EvaluationError): subject.load_protocol(self.root)

    def test_retained_checkpoint_all_four_receipts_and_location_required(self):
        for arm, location in subject.REFERENCE_FILES.items():
            for name in subject.RECEIPT_FILES:
                path = self.root / Path(location).parent / name; before = path.read_bytes()
                path.write_bytes(before + b"\n")
                with self.subTest(arm=arm, file=name), self.assertRaises(subject.ev.EvaluationError):
                    subject.verified_checkpoint(arm, location, self.protocol, self.root)
                path.write_bytes(before)
            self.assertEqual(subject.verified_checkpoint(arm, location, self.protocol, self.root)[1], arm.lower() * 64)
        with self.assertRaises(subject.ev.EvaluationError):
            subject.verified_checkpoint("E", subject.REFERENCE_FILES["B"], self.protocol, self.root)

    def test_f_only_dispatches_completed_receipt_verifier(self):
        with self.assertRaises(subject.ev.EvaluationError):
            subject.verified_checkpoint("F", subject.F_CHECKPOINT, self.protocol, self.root)
        self.write(subject.F_CHECKPOINT, {"synthetic": True})
        self.assertEqual(subject.verified_checkpoint("F", subject.F_CHECKPOINT, self.protocol, self.root)[1], "f" * 64)
        self.f_verifier.assert_called_once_with(self.root, self.root / subject.F_CHECKPOINT)
        self.f_verifier.side_effect = ValueError("Incomplete F")
        with self.assertRaises(ValueError): subject.verified_checkpoint("F", subject.F_CHECKPOINT, self.protocol, self.root)

    def test_base_and_private_input_overrides_rejected(self):
        with self.assertRaises(subject.ev.EvaluationError):
            subject.verified_checkpoint("A", subject.REFERENCE_FILES["B"], self.protocol, self.root)
        for field in subject.PRIVATE_FIELDS | {"resume"}:
            config = self.config(); config[field] = True
            with self.subTest(field=field), self.assertRaises(subject.ev.EvaluationError):
                subject.run(config, "A", root=self.root)

    def test_sampling_settings_and_insufficient_or_excess_budget_stop_before_calls(self):
        for field, value in (("seed", 20260906), ("reasoning_effort", "high"), ("input_price_per_million", 0.),
                             ("output_price_per_million", 0.), ("budget_usd", 1.51), ("budget_usd", .5)):
            config = self.config(); config[field] = value
            with patch.object(subject.comparison, "configure", side_effect=dict), patch.object(subject.ev, "run") as run:
                with self.subTest(field=field, value=value), self.assertRaises(subject.ev.EvaluationError):
                    subject.run(config, "A", root=self.root)
                run.assert_not_called()

    def test_dry_runs_create_no_directory_worker_or_environment_access(self):
        for arm in "ABE":
            checkpoint = subject.REFERENCE_FILES.get(arm)
            with patch.object(subject.comparison, "configure", side_effect=dict), \
                 patch.object(subject.native, "BoundedNativeTransport") as worker, \
                 patch.object(subject.ev, "load_project_environment") as environment, patch.object(subject.ev, "run") as run:
                result = subject.run(self.config(arm), arm, checkpoint, root=self.root)
            self.assertEqual(result["pending_cases"], 30)
            self.assertLess(result["remaining_worst_case_usd"], 1.5)
            self.assertFalse((self.root / subject.RUN_DIRECTORIES[arm]).exists())
            worker.assert_not_called(); environment.assert_not_called(); run.assert_not_called()

    def test_execute_private_output_metadata_and_public_allowlist(self):
        transport = object()
        def execute(config, **kwargs):
            subject.ev.write_json(Path(config["run_dir"]) / "fixture.json", {"private": "synthetic"})
            self.assertFalse(kwargs["resume"])
            self.assertEqual(config["criteria_review_sha256"], self.protocol["criteria_review"]["sha256"])
            self.assertEqual(len(config["revision_protocol_sha256"]), 64)
            self.assertNotIn("calibration_protocol_sha256", config)
            return {"mode": "execute", "completed_cases": 30, "private": "secret", "settings": config}
        with patch.object(subject.comparison, "configure", side_effect=dict), \
             patch.object(subject.ev, "run", side_effect=execute) as run:
            result = subject.run(self.config("B"), "B", subject.REFERENCE_FILES["B"], execute=True,
                                 transport=transport, root=self.root)
        self.assertIs(run.call_args.kwargs["transport"], transport)
        self.assertEqual(result, {"mode": "execute", "completed_cases": 30})
        directory = self.root / subject.RUN_DIRECTORIES["B"]
        self.assertEqual(directory.stat().st_mode & 0o777, 0o700)
        self.assertEqual((directory / "fixture.json").stat().st_mode & 0o777, 0o600)

    def test_failed_execution_cannot_be_retried_or_relocated(self):
        with patch.object(subject.comparison, "configure", side_effect=dict), \
             patch.object(subject.ev, "run", side_effect=RuntimeError("uncertain")) as run:
            with self.assertRaises(RuntimeError): subject.run(self.config(), "A", execute=True, transport=object(), root=self.root)
            with self.assertRaises(subject.ev.EvaluationError): subject.run(self.config(), "A", execute=True, transport=object(), root=self.root)
            config = self.config(); config["run_dir"] += "-retry"
            with self.assertRaises(subject.ev.EvaluationError): subject.run(config, "A", execute=True, transport=object(), root=self.root)
            self.assertEqual(run.call_count, 1)

    def test_native_worker_closed_on_failure(self):
        with patch.object(subject.comparison, "configure", side_effect=dict), \
             patch.object(subject.native, "BoundedNativeTransport") as worker, \
             patch.object(subject.ev, "run", side_effect=RuntimeError("uncertain")):
            with self.assertRaises(RuntimeError): subject.run(self.config(), "A", execute=True, root=self.root)
            worker.return_value.close.assert_called_once()

    def test_payload_excludes_review_and_scoring_supplement(self):
        payload = subject.ev.build_payload(self.cases[-1], self.config())
        text = json.dumps(payload)
        self.assertNotIn("Do not include this criterion", text)
        self.assertNotIn("Accept correct equivalents", text)
        self.assertNotIn("scoring_supplement", text)

    def test_cli_refuses_resume_before_protocol_or_environment_access(self):
        with patch.object(subject, "run") as run:
            with self.assertRaises(SystemExit): subject.main(["--arm", "A", "--resume"])
        run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
