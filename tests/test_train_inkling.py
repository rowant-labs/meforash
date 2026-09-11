import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import MagicMock, patch

from bibleprep import train_inkling as train


ROW = {"id": "synthetic", "input_ids": [200028, 100, 101],
       "target_ids": [100, 101, 199999], "weights": [0, 1, 1]}


def stalled_worker(connection):
    connection.recv()
    # The parent must terminate this worker at its own deadline.
    import threading
    threading.Event().wait(60)


def fake_plan(config, root):
    return {"phase": config.phase, "recipe": {"adam": {}}, "recipe_sha256": "synthetic",
            "planned_nano_usd": 3 * train.NANO + 9 * train.TOKEN_NANO,
            "planned_estimated_usd": 3.001, "checkpoint_reserve_nano_usd": 3 * train.NANO,
            "training_processed_tokens": 3, "training_loss_tokens": 2}, [[ROW]], [ROW]


class FakeTransport:
    def __init__(self, directory, fail=None):
        self.directory, self.fail = directory, fail
        self.calls = []
        self.closed = False

    def __call__(self, operation, rows, settings):
        # Simulate a provider receiving the operation: its reservation must
        # already be durable in both the complete-run and operation journals.
        events = [json.loads(x) for x in (self.directory / "events.jsonl").read_text().splitlines()]
        assert events[-1]["event"] == "operation_reserved"
        assert events[-1]["operation"] == operation
        assert (self.directory.parent / "inkling-training-budget.jsonl").exists()
        self.calls.append(operation)
        if operation == self.fail:
            raise RuntimeError("synthetic uncertainty")
        if rows:
            self.assert_unmodified(rows)
            return {"logprobs": [[-100.0, -0.5, -1.5] for _ in rows]}
        return {"path": "tinker://synthetic/weights/" + operation} if operation in {"state", "sampler"} else {}

    @staticmethod
    def assert_unmodified(rows):
        assert all(r == ROW for r in rows)

    def close(self):
        self.closed = True


class TrainingTests(unittest.TestCase):
    def test_worker_deadline_terminates_process_and_forbids_replay(self):
        transport = train.BoundedTrainingTransport(worker=stalled_worker)
        start = time.monotonic()
        try:
            with self.assertRaises(train.TrainingError):
                transport("create", [], {"timeout_seconds": 0.2})
            self.assertTrue(transport.failed)
            self.assertIsNone(transport.process)
            with self.assertRaises(train.TrainingError):
                transport("create", [], {"timeout_seconds": 0.2})
            self.assertLess(time.monotonic() - start, 3)
        finally:
            transport.close()

    def test_native_datum_preserves_the_single_shift_and_binary_mask(self):
        import tinker
        session = train.NativeSession()
        session.types = tinker.types
        session.client = MagicMock()
        session.client.forward_backward.return_value.result.return_value.loss_fn_outputs = [
            {"logprobs": tinker.types.TensorData(data=[-100, -0.5, -1.5], dtype="float32", shape=[3])}]
        session.call("forward_backward", [ROW], {"timeout_seconds": 20})
        datum = session.client.forward_backward.call_args.args[0][0]
        self.assertEqual(datum.model_input.to_ints(), ROW["input_ids"])
        self.assertEqual(datum.loss_fn_inputs["target_tokens"].data, ROW["target_ids"])
        self.assertEqual(datum.loss_fn_inputs["weights"].data, ROW["weights"])

    def test_weighted_nll_excludes_metadata_without_rescaling_targets(self):
        result = train.weighted_nll([ROW], [[-100, -0.5, -1.5]])
        self.assertEqual(result["weighted_nll"], 1)
        self.assertEqual(result["loss_tokens"], 2)
        self.assertEqual(result["processed_tokens"], 3)

    def test_invalid_provider_logprobs_are_rejected(self):
        for values in ([[-1]], [[-1, float("nan"), -1]], [[-1, 0.2, -1]]):
            with self.subTest(values=values), self.assertRaises(train.TrainingError):
                train.weighted_nll([ROW], values)

    def test_cost_reservations_are_combined_and_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "runs").mkdir()
            train.reserve_budget(root, "first", 30 * train.NANO, train.HARD_CAP_NANO)
            with self.assertRaises(train.TrainingError):
                train.reserve_budget(root, "second", 21 * train.NANO, train.HARD_CAP_NANO)
            self.assertEqual(len((root / "runs/inkling-training-budget.jsonl").read_text().splitlines()), 1)

    def test_dry_run_never_loads_credentials_or_creates_worker(self):
        with patch.object(train, "make_plan", side_effect=fake_plan), \
             patch("bibleprep.environment.load_project_environment") as env, \
             patch.object(train, "BoundedTrainingTransport") as worker:
            self.assertEqual(train.run(train.Config())["status"], "dry_run")
        env.assert_not_called()
        worker.assert_not_called()

    def test_complete_run_reserves_before_calls_and_saves_both_checkpoints(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(train, "make_plan", side_effect=fake_plan):
            root = Path(directory)
            output = root / "runs/calibration"
            transport = FakeTransport(output)
            summary = train.run(train.Config(run_dir="runs/calibration"), execute=True, root=root, transport=transport)
            self.assertEqual(summary["status"], "complete")
            self.assertEqual(transport.calls, ["create", "forward", "forward_backward", "optim", "forward", "state", "sampler"])
            self.assertTrue(transport.closed)
            refs = json.loads((output / "checkpoints.json").read_text())
            self.assertTrue(all(value.startswith("tinker://") for value in refs.values()))
            self.assertEqual((output / "checkpoints.json").stat().st_mode & 0o777, 0o600)

    def test_uncertain_backward_never_updates_or_retries(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(train, "make_plan", side_effect=fake_plan):
            root = Path(directory)
            output = root / "runs/uncertain"
            transport = FakeTransport(output, fail="forward_backward")
            with self.assertRaises(train.TrainingError):
                train.run(train.Config(run_dir="runs/uncertain"), execute=True, root=root, transport=transport)
            self.assertEqual(transport.calls, ["create", "forward", "forward_backward"])
            self.assertFalse((output / "checkpoints.json").exists())
            self.assertTrue(transport.closed)
            events = [json.loads(x) for x in (output / "events.jsonl").read_text().splitlines()]
            self.assertEqual(events[-1]["event"], "operation_uncertain")
            self.assertEqual(json.loads((output / "summary.json").read_text())["status"], "stopped_uncertain")
            self.assertEqual(len((root / "runs/inkling-training-budget.jsonl").read_text().splitlines()), 1)

    def test_uncertain_optimizer_is_not_replayed_or_followed_by_checkpoint(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(train, "make_plan", side_effect=fake_plan):
            root = Path(directory)
            transport = FakeTransport(root / "runs/uncertain", fail="optim")
            with self.assertRaises(train.TrainingError):
                train.run(train.Config(run_dir="runs/uncertain"), execute=True, root=root, transport=transport)
            self.assertEqual(transport.calls, ["create", "forward", "forward_backward", "optim"])

    def test_full_run_requires_matching_completed_calibration(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(train, "make_plan", side_effect=fake_plan):
            root = Path(directory)
            output = root / "runs/calibration"
            output.mkdir(parents=True)
            (output / "summary.json").write_text(json.dumps({"status": "complete", "phase": "calibration", "recipe_sha256": "wrong"}))
            transport = FakeTransport(root / "runs/full")
            with self.assertRaises(train.TrainingError):
                train.run(train.Config(phase="full", calibration_run="runs/calibration"), execute=True, root=root, transport=transport)
            self.assertEqual(transport.calls, [])

    def test_sdk_hook_never_resubmits_failed_operation(self):
        import asyncio
        from types import SimpleNamespace
        calls = []
        async def failure():
            calls.append(1)
            raise RuntimeError("synthetic")
        holder = SimpleNamespace(execute_with_retries=lambda: None)
        train.disable_submission_retries(holder)
        with self.assertRaises(RuntimeError):
            asyncio.run(holder.execute_with_retries(failure))
        self.assertEqual(calls, [1])


if __name__ == "__main__":
    unittest.main()
