import copy
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch

from bibleprep import train_instruction as instruction
from bibleprep import train_inkling as raw


ROW = {"id": "synthetic", "input_ids": [200002, 10, 11, 12],
       "target_ids": [10, 11, 12, 200006], "weights": [0, 0, 1, 1],
       "prompt_token_count": 3, "processed_token_count": 4, "loss_token_count": 2,
       "chapter_keys": ["synthetic:1"], "language": "hebrew"}


def fake_plan(config, root):
    return {"phase": "instruction", "arm": config.arm, "recipe": {"adam": {}},
            "source_adapter": {"synthetic": "receipt"} if config.arm == "D" else None,
            "recipe_sha256": "synthetic", "planned_nano_usd": 3 * raw.NANO + 12 * raw.TOKEN_NANO,
            "planned_estimated_usd": 3.001, "checkpoint_reserve_nano_usd": 3 * raw.NANO,
            "training_processed_tokens": 4, "training_loss_tokens": 2}, [[ROW]], [ROW]


class FakeTransport:
    def __init__(self, directory, fail=None):
        self.directory, self.fail = directory, fail
        self.calls = []
        self.closed = False

    def __call__(self, operation, rows, settings):
        events = [json.loads(line) for line in (self.directory / "events.jsonl").read_text().splitlines()]
        assert events[-1]["event"] == "operation_reserved"
        assert events[-1]["operation"] == operation
        assert (self.directory.parent / "inkling-training-budget.jsonl").exists()
        self.calls.append(operation)
        if operation == self.fail:
            raise RuntimeError("synthetic secret-bearing provider error must not leak")
        if rows:
            assert all(set(row) == {"input_ids", "target_ids", "weights"} for row in rows)
            assert all(row["input_ids"] == ROW["input_ids"] for row in rows)
            return {"logprobs": [[-99.0, -99.0, -0.5, -1.5] for row in rows]}
        return {"path": "tinker://synthetic/weights/" + operation} if operation in {"state", "sampler"} else {}

    def close(self):
        self.closed = True


def write_json(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj))
    return raw.digest(path.read_bytes())


def fixture(root):
    """A synthetic 100-example corpus tests gates without any source or API call."""
    manifest = {"schema_version": 1, "status": "prepared_not_trained",
                "objective": "reviewed_english_instruction_sft", "review_status": "ai_source_checked",
                "expert_certified": False, "model": raw.MODEL, "thinking_effort_numeric": 0.7,
                "native_start_token_id": 200002, "native_end_token_id": 200006,
                "maximum_input_tokens": 8192, "runtime_versions": {"tinker": raw.SDK_VERSION},
                "split": {"chapter_disjoint": True}, "artifacts": {}}
    names = ("bibleprep/prepare_instruction.py", "bibleprep/train_instruction.py", "bibleprep/train_inkling.py",
             "bibleprep/environment.py", "requirements-training.txt", "requirements-comparison-large.lock.txt")
    for name in names:
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("synthetic fixture")
    manifest["preparation_code_sha256"] = {names[0]: raw.digest((root / names[0]).read_bytes())}
    for split, count in (("train", 90), ("validation", 10)):
        rows = []
        for i in range(count):
            row = copy.deepcopy(ROW)
            row["id"] = split + str(i)
            row["chapter_keys"] = ["synthetic:" + split + str(i)]
            rows.append(row)
        relative = "data/prepared/instruction-v1/" + split + ".jsonl"
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("\n".join(json.dumps(row) for row in rows) + "\n")
        manifest["artifacts"][split] = {"path": relative, "sha256": raw.digest(path.read_bytes()),
                                         "sequences": count, "processed_tokens": 4 * count, "loss_tokens": 2 * count}
    dataset = "runs/instruction-reviewed.jsonl"
    dataset_sha = write_json(root / dataset, {"only": "synthetic training data"})
    manifest["reviewed_dataset"] = {"path": dataset, "sha256": dataset_sha, "examples": 100}
    exclusion = "manifests/synthetic-exclusion.json"
    exclusion_sha = write_json(root / exclusion, {"chapter_keys": ["synthetic:excluded"]})
    manifest["evaluation_exclusion"] = {"path": exclusion, "sha256": exclusion_sha, "overlap_count": 0}
    write_json(root / instruction.MANIFEST, manifest)
    return manifest


class InstructionTests(unittest.TestCase):
    def test_dry_run_never_loads_credentials_or_constructs_transport(self):
        with patch.object(instruction, "make_plan", side_effect=fake_plan), \
             patch("bibleprep.environment.load_project_environment") as environment, \
             patch.object(raw, "BoundedTrainingTransport") as transport:
            self.assertEqual(instruction.run(instruction.Config())["status"], "dry_run")
        environment.assert_not_called()
        transport.assert_not_called()

    def test_native_weights_only_load_never_restores_optimizer_and_cannot_repeat(self):
        session = instruction.InstructionNativeSession()
        session.client = MagicMock()
        session.source_verified = True
        settings = {"arm": "D", "source_checkpoint": "tinker://synthetic/weights/full", "timeout_seconds": 20}
        session.call("load_weights", [], settings)
        session.client.load_state.assert_called_once_with(settings["source_checkpoint"])
        session.client.load_state_with_optimizer.assert_not_called()
        session.client.optim_step.assert_not_called()
        with self.assertRaises(raw.TrainingError):
            session.call("load_weights", [], settings)

    def test_d_cannot_train_without_loading_or_load_without_inspection(self):
        for operation in ("forward_backward", "load_weights", "optim"):
            session = instruction.InstructionNativeSession()
            session.client = MagicMock()
            with self.subTest(operation=operation), self.assertRaises(raw.TrainingError):
                session.call(operation, [ROW], {"arm": "D"})
            self.assertEqual(session.client.mock_calls, [])

    def test_source_configuration_mismatch_stops_before_load(self):
        session = instruction.InstructionNativeSession()
        session.client = MagicMock()
        session.service = MagicMock()
        response = SimpleNamespace(base_model=raw.MODEL, is_lora=True, lora_rank=32,
                                   train_mlp=True, train_attn=True, train_unembed=True)
        session.service.create_rest_client.return_value.get_weights_info_by_tinker_path.return_value.result.return_value = response
        with self.assertRaises(raw.TrainingError):
            session.call("verify_source", [], {"arm": "D", "source_checkpoint": "tinker://synthetic/weights/full", "timeout_seconds": 20})
        session.client.load_state.assert_not_called()

    def test_native_datum_preserves_shift_and_assistant_mask(self):
        import tinker
        session = instruction.InstructionNativeSession()
        session.client, session.types, session.ready = MagicMock(), tinker.types, True
        session.client.forward_backward.return_value.result.return_value.loss_fn_outputs = [
            {"logprobs": tinker.types.TensorData(data=[-99, -99, -.5, -1.5], dtype="float32", shape=[4])}]
        session.call("forward_backward", [ROW], {"timeout_seconds": 20})
        datum = session.client.forward_backward.call_args.args[0][0]
        self.assertEqual(datum.model_input.to_ints(), ROW["input_ids"])
        self.assertEqual(datum.loss_fn_inputs["target_tokens"].data, ROW["target_ids"])
        self.assertEqual(datum.loss_fn_inputs["weights"].data, ROW["weights"])

    def test_fresh_c_and_loaded_d_have_matched_operations_after_initialization(self):
        with tempfile.TemporaryDirectory() as directory, \
             patch.object(instruction, "make_plan", side_effect=fake_plan), \
             patch.object(instruction, "source_receipt", return_value=({"synthetic": "receipt"}, "tinker://synthetic/weights/full")):
            root = Path(directory)
            operation_lists = {}
            for arm in ("C", "D"):
                output = root / ("runs/instruction-" + arm)
                transport = FakeTransport(output)
                summary = instruction.run(instruction.Config(arm=arm, run_dir=str(output)), execute=True, root=root, transport=transport)
                self.assertEqual(summary["status"], "complete")
                self.assertEqual(summary["phase"], "instruction")
                self.assertEqual(summary["arm"], arm)
                self.assertFalse(summary["optimizer_restored"])
                self.assertEqual(summary["baseline_sft_validation"]["by_language"]["hebrew"]["weighted_nll"], 1)
                self.assertEqual((output / "checkpoints.json").stat().st_mode & 0o777, 0o600)
                self.assertEqual(summary["checkpoint_reference_sha256"], raw.digest((output / "checkpoints.json").read_bytes()))
                self.assertTrue(transport.closed)
                operation_lists[arm] = transport.calls
            self.assertEqual(operation_lists["C"], ["create", "verify_client", "forward", "forward_backward", "optim", "forward", "state", "sampler"])
            self.assertEqual(operation_lists["D"], operation_lists["C"][:2] + ["verify_source", "load_weights"] + operation_lists["C"][2:])

    def test_existing_budget_stops_before_any_provider_or_credential_call(self):
        with tempfile.TemporaryDirectory() as directory, \
             patch.object(instruction, "make_plan", side_effect=fake_plan), \
             patch("bibleprep.environment.load_project_environment") as environment:
            root = Path(directory)
            (root / "runs").mkdir()
            raw.reserve_budget(root, "previous", 48 * raw.NANO, raw.HARD_CAP_NANO)
            transport = FakeTransport(root / "runs/new")
            with self.assertRaises(raw.TrainingError):
                instruction.run(instruction.Config(run_dir="runs/new"), execute=True, root=root, transport=transport)
            self.assertEqual(transport.calls, [])
            environment.assert_not_called()
            self.assertEqual(instruction.reserved_budget(root), 48 * raw.NANO)

    def test_uncertain_load_backward_and_optimizer_are_never_retried(self):
        for failure in ("load_weights", "forward_backward", "optim"):
            with self.subTest(failure=failure), tempfile.TemporaryDirectory() as directory, \
                 patch.object(instruction, "make_plan", side_effect=fake_plan), \
                 patch.object(instruction, "source_receipt", return_value=({"synthetic": "receipt"}, "tinker://synthetic/weights/full")):
                root = Path(directory)
                output = root / "runs/uncertain"
                transport = FakeTransport(output, fail=failure)
                with self.assertRaisesRegex(raw.TrainingError, "reserved costs remain"):
                    instruction.run(instruction.Config(arm="D", run_dir="runs/uncertain"), execute=True, root=root, transport=transport)
                self.assertEqual(transport.calls[-1], failure)
                self.assertEqual(transport.calls.count(failure), 1)
                self.assertNotIn("state", transport.calls)
                self.assertTrue(transport.closed)
                self.assertGreater(instruction.reserved_budget(root), 3 * raw.NANO)
                self.assertEqual(json.loads((output / "summary.json").read_text())["status"], "stopped_uncertain")
                self.assertNotIn("secret-bearing", (output / "events.jsonl").read_text())

    def test_preparation_gates_and_matched_plan(self):
        verifier = MagicMock()
        with tempfile.TemporaryDirectory() as directory, \
             patch.dict("sys.modules", {"bibleprep.prepare_instruction": SimpleNamespace(verify_prepared=verifier)}):
            root = Path(directory)
            fixture(root)
            c, batches_c, holdout_c = instruction.make_plan(instruction.Config(), root)
            with patch.object(instruction, "source_receipt", return_value=({"synthetic": "receipt"}, "tinker://synthetic/weights/full")):
                d, batches_d, holdout_d = instruction.make_plan(instruction.Config(arm="D"), root)
            self.assertEqual(c["recipe_sha256"], d["recipe_sha256"])
            self.assertEqual(c["sequence_order_sha256"], d["sequence_order_sha256"])
            self.assertEqual(batches_c, batches_d)
            self.assertEqual(holdout_c, holdout_d)
            self.assertLess(c["pair_planned_estimated_usd"], 15)
            self.assertEqual(c["training_sequences"], 90)
            self.assertEqual(verifier.call_count, 2)

    def test_damaged_checksum_unreviewed_state_and_overlap_fail_closed(self):
        for damage in ("checksum", "review", "mask", "shift", "overlap", "verifier"):
            verifier = MagicMock(side_effect=ValueError("unreviewed") if damage == "verifier" else None)
            with self.subTest(damage=damage), tempfile.TemporaryDirectory() as directory, \
                 patch.dict("sys.modules", {"bibleprep.prepare_instruction": SimpleNamespace(verify_prepared=verifier)}):
                root = Path(directory)
                manifest = fixture(root)
                entry = manifest["artifacts"]["train"]
                path = root / entry["path"]
                if damage == "checksum":
                    path.write_text(path.read_text() + " ")
                elif damage == "review":
                    manifest["review_status"] = "draft"
                elif damage in {"mask", "shift", "overlap"}:
                    rows = [json.loads(line) for line in path.read_text().splitlines()]
                    if damage == "mask":
                        rows[0]["weights"] = [0, 1, 0, 1]
                    if damage == "shift":
                        rows[0]["target_ids"][0] = 999
                    if damage == "overlap":
                        rows[0]["chapter_keys"] = ["synthetic:excluded"]
                    path.write_text("\n".join(json.dumps(row) for row in rows) + "\n")
                    entry["sha256"] = raw.digest(path.read_bytes())
                write_json(root / instruction.MANIFEST, manifest)
                with self.assertRaises(raw.TrainingError):
                    instruction.make_plan(instruction.Config(), root)

    def test_source_receipt_rejects_sampler_only_or_wrong_completed_run(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / "runs/source"
            write_json(output / "plan.json", {"recipe": {}, "phase": "full"})
            write_json(output / "summary.json", {"status": "complete", "phase": "full"})
            write_json(output / "checkpoints.json", {"sampler_path": "tinker://synthetic/sampler_weights/only"})
            (output / "events.jsonl").write_text('{"event":"run_complete"}\n')
            with self.assertRaises(raw.TrainingError):
                instruction.source_receipt(instruction.Config(arm="D", source_checkpoint_file="runs/source/checkpoints.json"), root)
            with self.assertRaises(raw.TrainingError):
                instruction.source_receipt(instruction.Config(arm="D", source_checkpoint_file="checkpoints.json"), root)


if __name__ == "__main__":
    unittest.main()
