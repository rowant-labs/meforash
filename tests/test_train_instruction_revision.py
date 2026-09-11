import copy
import json
from pathlib import Path
import random
import shutil
import tempfile
from unittest import TestCase
from unittest.mock import MagicMock, patch

from bibleprep import train_instruction_revision as subject
from bibleprep import train_instruction as v1
from bibleprep import train_inkling as raw


ROW = {"input_ids": [200002, 10, 11, 12], "target_ids": [10, 11, 12, 200006],
       "weights": [0.0, 0.0, 1.0, 1.0], "language": "hbo"}


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value))


def public_fixture(root):
    protocol = subject.build_training_protocol(subject.ROOT)
    for name in [subject.v2.MANIFEST, v1.MANIFEST, subject.preparation.PREPARATION_MANIFEST, *protocol["software_sha256"]]:
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(subject.ROOT / name, path)
    write(root / subject.MANIFEST, protocol)
    return protocol


def frozen_evaluation(root):
    data = root / "evals/instruction-target-revision-v3.jsonl"
    data.parent.mkdir(parents=True, exist_ok=True)
    # Deliberately not JSON: the trainer hashes bytes without parsing questions.
    data.write_text("Synthetic evaluation bytes must not be parsed by the trainer.")
    dataset = {"path": data.relative_to(root).as_posix(), "sha256": raw.digest(data.read_bytes()),
               "cases": 30, "case_ids": ["synthetic-" + str(i) for i in range(30)]}
    metadata = root / "manifests/instruction-target-revision-evaluation-v3.json"
    write(metadata, {"schema_version": 3, "status": "frozen_before_training_and_sampling", "dataset": dataset})
    experiment = {"schema_version": 3, "status": "frozen_before_training_and_sampling",
                  "experiment_id": "instruction-target-revision-v3",
                  "arms": {"F": "original_text_then_revised_instruction_lr_0.00002"}, "evaluation": dataset,
                  "evaluation_manifest": {"path": metadata.relative_to(root).as_posix(), "sha256": raw.digest(metadata.read_bytes())},
                  "training_manifest": {"path": subject.MANIFEST, "sha256": raw.digest((root / subject.MANIFEST).read_bytes())}}
    review = root / "manifests/instruction-target-revision-criteria-review-v3.json"
    review.write_text("Synthetic review bytes must not be parsed by the trainer.")
    experiment["criteria_review"] = {"path": review.relative_to(root).as_posix(), "sha256": raw.digest(review.read_bytes())}
    experiment["budget"] = dict(subject.EXPERIMENT_BUDGET)
    write(root / subject.EXPERIMENT, experiment)
    return experiment


class FakeTransport:
    def __init__(self, root, output, fail=None):
        self.root, self.output, self.fail = root, output, fail
        self.calls = []
        self.closed = False

    def __call__(self, operation, rows, settings):
        self.calls.append(operation)
        ledger = [json.loads(line) for line in (self.root / "runs/inkling-training-budget.jsonl").read_text().splitlines()]
        assert ledger[-1]["amount_nano_usd"] == subject.PLANNED_NANO
        events = [json.loads(line) for line in (self.output / "events.jsonl").read_text().splitlines()]
        assert events[-1]["event"] == "operation_reserved" and events[-1]["operation"] == operation
        assert settings["arm"] == "F" and settings["adam"]["learning_rate"] == 2e-5
        assert settings["timeout_seconds"] == 600 and settings["checkpoint_ttl_seconds"] == 2592000
        assert all(set(row) == {"input_ids", "target_ids", "weights"} for row in rows)
        assert all(row["target_ids"] == ROW["target_ids"] and row["weights"] == ROW["weights"] for row in rows)
        if operation == self.fail:
            raise RuntimeError("SYNTHETIC PRIVATE PROVIDER FAILURE")
        if rows:
            return {"logprobs": [[-99, -99, -.5, -1.5] for _ in rows]}
        if operation in {"state", "sampler"}:
            folder = "weights" if operation == "state" else "sampler_weights"
            return {"path": "tinker://synthetic/" + folder + "/revision"}
        return {}

    def close(self):
        self.closed = True


class RevisionTests(TestCase):
    def test_F_fixes_E_recipe_B_parent_and_single_run_directory(self):
        subject.Config().validate()
        for changes in ({"arm": "D"}, {"learning_rate": 1e-4}, {"batch_size": 8},
                        {"seed": 1}, {"checkpoint_reserve_usd": 2}, {"checkpoint_ttl_seconds": 1},
                        {"max_cost_usd": 51}, {"timeout_seconds": 3600},
                        {"run_dir": "runs/duplicate-f"}, {"source_checkpoint_file": "runs/inkling-instruction-e-v2/checkpoints.json"}):
            with self.subTest(changes=changes), self.assertRaises(raw.TrainingError):
                subject.Config(**changes).validate()

    def test_protocol_rejects_other_recipe_changes_even_with_updated_recipe_hash(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            protocol = public_fixture(root)
            subject.load_training_protocol(root)
            protocol["recipe"]["adam"]["weight_decay"] = .1
            protocol["recipe_sha256"] = raw.digest(raw.encoded(protocol["recipe"]))
            write(root / subject.MANIFEST, protocol)
            with self.assertRaises(raw.TrainingError):
                subject.load_training_protocol(root)

    def test_planner_changes_only_preparation_and_reuses_verified_v3_rows(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            protocol = public_fixture(root)
            batches, holdout = [[copy.deepcopy(ROW)]], [copy.deepcopy(ROW)]
            with patch.object(subject, "verified_rows", return_value=(batches, holdout)) as verification, \
                    patch.object(v1, "source_receipt", return_value=(protocol["source_adapter"], "private-reference")):
                plan, actual_batches, actual_holdout = subject.make_plan(subject.Config(), root)
            verification.assert_called_once_with(root, protocol)
            expected = copy.deepcopy(protocol["reference_recipe"])
            expected["manifest_sha256"] = subject.PREPARATION_SHA256
            self.assertEqual(plan["recipe"], expected)
            self.assertEqual(expected["adam"]["learning_rate"], 2e-5)
            self.assertIs(actual_batches, batches)
            self.assertIs(actual_holdout, holdout)
            with patch.object(subject, "verified_rows", return_value=(batches, holdout)), \
                    patch.object(v1, "source_receipt", return_value=({"wrong": "E parent"}, "unused")), self.assertRaises(raw.TrainingError):
                subject.make_plan(subject.Config(), root)

    def test_revised_source_review_failure_prevents_any_planning_or_reservation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            protocol = public_fixture(root)
            with patch.object(subject.preparation, "verify_prepared", side_effect=ValueError("Changed approved source target")) as verify, \
                    patch.object(v1, "source_receipt") as parent, self.assertRaises(raw.TrainingError):
                subject.make_plan(subject.Config(), root)
            verify.assert_called_once()
            parent.assert_not_called()
            self.assertFalse((root / "runs").exists())

    def test_exact_order_counts_and_validation_ids_are_verified(self):
        protocol = subject.build_training_protocol(subject.ROOT)
        manifest = json.loads((subject.ROOT / subject.preparation.PREPARATION_MANIFEST).read_bytes())
        rows = {split: [json.loads(line) for line in (subject.ROOT / entry["path"]).read_bytes().splitlines()]
                for split, entry in manifest["artifacts"].items()}
        with patch.object(subject.preparation, "verify_prepared", return_value=rows):
            batches, holdout = subject.verified_rows(subject.ROOT, protocol)
            self.assertEqual(len(batches), 7)
            self.assertEqual(len(holdout), 16)
            for altered in (dict(protocol, counts={**protocol["counts"], "training_loss_tokens": 1}),
                            dict(protocol, recipe={**protocol["recipe"], "validation_ids": ["wrong"]})):
                with self.assertRaises(raw.TrainingError):
                    subject.verified_rows(subject.ROOT, altered)
            rows["train"][0]["id"] = "changed_order"
            with self.assertRaises(raw.TrainingError):
                subject.verified_rows(subject.ROOT, protocol)

    def test_instruction_receipt_is_not_accepted_as_F_original_text_parent(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            parent = root / "runs/synthetic-d"
            write(parent / "plan.json", {"phase": "instruction", "arm": "D", "recipe": {}})
            write(parent / "summary.json", {"status": "complete", "phase": "instruction", "arm": "D"})
            write(parent / "checkpoints.json", {"training_state_path": "tinker://synthetic/weights/d"})
            (parent / "events.jsonl").write_text(json.dumps({"event": "run_complete"}) + "\n")
            with self.assertRaises(raw.TrainingError):
                v1.source_receipt(subject.Config(source_checkpoint_file="runs/synthetic-d/checkpoints.json"), root)

    def test_freeze_gate_hashes_evaluation_without_parsing_questions(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            public_fixture(root)
            frozen_evaluation(root)
            self.assertEqual(len(subject.verify_evaluation_freeze(root)), 64)
            (root / "evals/instruction-target-revision-v3.jsonl").write_text("Changed evaluation bytes")
            with self.assertRaises(raw.TrainingError):
                subject.verify_evaluation_freeze(root)

    def test_freeze_gate_rejects_wrong_training_manifest_and_unfrozen_evaluation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            public_fixture(root)
            experiment = frozen_evaluation(root)
            for field, value in (("status", "draft"), ("training_manifest", {"path": subject.MANIFEST, "sha256": "0" * 64}),
                                 ("budget", {**subject.EXPERIMENT_BUDGET, "incremental_experiment_cap_usd": 20}),
                                 ("budget", {**subject.EXPERIMENT_BUDGET, "per_arm_sampling_cap_usd": 2}),
                                 ("criteria_review", {"path": "manifests/instruction-target-revision-criteria-review-v3.json", "sha256": "0" * 64})):
                changed = {**experiment, field: value}
                write(root / subject.EXPERIMENT, changed)
                with self.assertRaises(raw.TrainingError):
                    subject.verify_evaluation_freeze(root)

    def test_weights_only_initialization_preserves_caller_settings_and_rejects_repeat(self):
        session = subject.RevisionNativeSession()
        session.client, session.source_verified = MagicMock(), True
        settings = {"arm": "F", "adam": {"learning_rate": 2e-5},
                    "source_checkpoint": "tinker://synthetic/weights/original", "timeout_seconds": 600}
        before = copy.deepcopy(settings)
        session.call("load_weights", [], settings)
        self.assertEqual(settings, before)
        session.client.load_state.assert_called_once_with(settings["source_checkpoint"])
        session.client.load_state_with_optimizer.assert_not_called()
        with self.assertRaises(raw.TrainingError):
            session.call("load_weights", [], settings)

    def test_no_training_before_verified_B_weights_load(self):
        for operation in ("forward", "forward_backward", "optim", "load_weights"):
            session = subject.RevisionNativeSession()
            session.client = MagicMock()
            with self.subTest(operation=operation), self.assertRaises(raw.TrainingError):
                session.call(operation, [], {"arm": "F", "adam": {"learning_rate": 2e-5}})
            self.assertEqual(session.client.mock_calls, [])


class RunTests(TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.output = self.root / "runs/inkling-instruction-f-v3"
        self.train = [{**copy.deepcopy(ROW), "id": "T" + str(i)} for i in range(104)]
        self.holdout = [{**copy.deepcopy(ROW), "id": "V" + str(i)} for i in range(16)]
        self.selected = sorted(self.train, key=lambda row: row["id"])
        random.Random(20260906).shuffle(self.selected)
        self.order = raw.digest(raw.encoded([row["id"] for row in self.selected]))
        self.batches = [self.selected[i:i + 16] for i in range(0, 104, 16)]
        self.protocol = subject.build_training_protocol(subject.ROOT)
        self.protocol["counts"] = {"training_sequences": 104, "training_batches": 7,
                                  "training_processed_tokens": 416, "training_loss_tokens": 208,
                                  "holdout_sequences": 16, "two_holdout_forward_tokens": 128}
        self.protocol["source_adapter"] = {"synthetic": "parent B receipt"}
        self.protocol["software_sha256"] = {}
        self.plan = {"schema_version": 3, "phase": "instruction_revision", "arm": "F", "parent_arm": "B",
                     "recipe": self.protocol["recipe"], "recipe_sha256": self.protocol["recipe_sha256"],
                     "source_adapter": self.protocol["source_adapter"], "source_checkpoint_file": subject.SOURCE_CHECKPOINT_FILE,
                     "software_sha256": {}, "sequence_order_sha256": self.order, "training_protocol_sha256": "a" * 64,
                     "fresh_adapter": False, "fresh_training_client": True, "optimizer_restored": False,
                     "checkpoint_ttl_seconds": 2592000, "checkpoint_reserve_nano_usd": 3 * raw.NANO,
                     "planned_nano_usd": subject.PLANNED_NANO, "planned_estimated_usd": 3.48945567,
                     **self.protocol["counts"]}
        self.addCleanup(patch.stopall)
        patch.object(subject, "make_plan", return_value=(self.plan, self.batches, self.holdout)).start()
        patch.object(subject, "verify_evaluation_freeze", return_value="b" * 64).start()
        patch.object(v1, "source_receipt", return_value=(self.protocol["source_adapter"], "tinker://synthetic/weights/original")).start()
        patch.object(subject, "ORDER_SHA256", self.order).start()
        self.config = subject.Config(run_dir="runs/inkling-instruction-f-v3")

    def execute(self, fail=None):
        transport = FakeTransport(self.root, self.output, fail)
        result = subject.run(self.config, execute=True, root=self.root, transport=transport)
        return result, transport

    def test_dry_run_never_loads_environment_checks_gate_or_creates_transport(self):
        with patch("bibleprep.environment.load_project_environment") as environment, patch.object(raw, "BoundedTrainingTransport") as native:
            result = subject.run(self.config, root=self.root)
        self.assertEqual(result["status"], "dry_run")
        environment.assert_not_called()
        native.assert_not_called()
        subject.verify_evaluation_freeze.assert_not_called()
        self.assertFalse((self.root / "runs").exists())

    def test_unfrozen_evaluation_stops_before_reservation_and_environment(self):
        with patch.object(subject, "verify_evaluation_freeze", side_effect=raw.TrainingError("not frozen")), \
                patch("bibleprep.environment.load_project_environment") as environment:
            with self.assertRaises(raw.TrainingError):
                subject.run(self.config, execute=True, root=self.root)
        environment.assert_not_called()
        self.assertFalse((self.root / "runs").exists())

    def test_seven_updates_reserve_before_calls_and_preserve_shifted_arrays(self):
        (self.root / "runs").mkdir()
        raw.reserve_budget(self.root, "synthetic-prior", 35435232840, raw.HARD_CAP_NANO)
        summary, transport = self.execute()
        self.assertEqual(transport.calls[:5], ["create", "verify_client", "verify_source", "load_weights", "forward"])
        self.assertEqual(transport.calls.count("forward_backward"), 7)
        self.assertEqual(transport.calls.count("optim"), 7)
        self.assertEqual(transport.calls[-3:], ["forward", "state", "sampler"])
        self.assertTrue(transport.closed)
        self.assertEqual(summary["combined_reserved_estimated_usd"], 38.92468851)
        self.assertEqual(summary["end_sft_validation"]["by_language"]["hbo"]["weighted_nll"], 1)
        self.assertEqual((self.output / "checkpoints.json").stat().st_mode & 0o777, 0o600)

    def test_exhausted_shared_budget_stops_before_transport_or_environment(self):
        (self.root / "runs").mkdir()
        raw.reserve_budget(self.root, "synthetic-prior", 48 * raw.NANO, raw.HARD_CAP_NANO)
        transport = FakeTransport(self.root, self.output)
        with patch("bibleprep.environment.load_project_environment") as environment, self.assertRaises(raw.TrainingError):
            subject.run(self.config, execute=True, root=self.root, transport=transport)
        self.assertEqual(transport.calls, [])
        environment.assert_not_called()

    def test_uncertain_update_stops_without_retry_and_retains_full_reservation(self):
        transport = FakeTransport(self.root, self.output, "optim")
        with self.assertRaises(raw.TrainingError):
            subject.run(self.config, execute=True, root=self.root, transport=transport)
        self.assertEqual(transport.calls.count("optim"), 1)
        self.assertNotIn("state", transport.calls)
        self.assertEqual(v1.reserved_budget(self.root), subject.PLANNED_NANO)
        self.assertTrue(transport.closed)
        self.assertEqual(json.loads((self.output / "summary.json").read_text())["status"], "stopped_uncertain")
        self.assertNotIn("SYNTHETIC PRIVATE PROVIDER FAILURE", (self.output / "events.jsonl").read_text())
        calls = list(transport.calls)
        with self.assertRaises(FileExistsError):
            subject.run(self.config, execute=True, root=self.root, transport=transport)
        self.assertEqual(transport.calls, calls)
        self.assertEqual(v1.reserved_budget(self.root), subject.PLANNED_NANO)

    def test_checkpoint_verifier_binds_parent_order_and_entire_journal(self):
        self.execute()
        with patch.object(subject, "load_training_protocol", return_value=(self.protocol, "a" * 64)), \
                patch.object(v1, "checked_file", return_value=b"{}"), \
                patch.object(subject, "verified_rows", return_value=(self.batches, self.holdout)):
            sampler, digest = subject.verify_completed_checkpoint(self.root, self.output / "checkpoints.json")
            self.assertEqual(sampler, "tinker://synthetic/sampler_weights/revision")
            self.assertEqual(digest, raw.digest((self.output / "checkpoints.json").read_bytes()))
            journal = self.output / "events.jsonl"
            saved = journal.read_bytes()
            entries = [json.loads(line) for line in saved.splitlines()]
            # Remove one completed optimizer operation without losing the terminal receipt.
            index = next(i for i, event in enumerate(entries) if event.get("operation") == "optim" and event["event"] == "operation_complete")
            del entries[index]
            journal.write_text("\n".join(json.dumps(event) for event in entries) + "\n")
            with self.assertRaises(raw.TrainingError):
                subject.verify_completed_checkpoint(self.root, self.output / "checkpoints.json")
            journal.write_bytes(saved)
            with patch.object(v1, "source_receipt", return_value=({"synthetic": "wrong D parent"}, "unused")), self.assertRaises(raw.TrainingError):
                subject.verify_completed_checkpoint(self.root, self.output / "checkpoints.json")
