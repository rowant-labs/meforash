import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from bibleprep import evaluate_adapter as adapter


class AdapterEvaluationTests(unittest.TestCase):
    def test_cli_defaults_match_frozen_baseline_dataset(self):
        with patch.object(adapter, "run", return_value={}) as run, patch("builtins.print"):
            self.assertEqual(adapter.main(["--checkpoint-file", "synthetic.json"]), 0)
        config = run.call_args.args[0]
        self.assertEqual(Path(config["dataset"]).name, "comparison-large-v1.jsonl")
        self.assertEqual(config["max_cases"], 24)
        self.assertEqual(config["evidence_mode"], "provided")
        self.assertEqual(config["seed"], 20260905)
        self.assertEqual(config["reasoning_effort"], "medium")

    def test_checkpoint_is_read_only_from_private_runs(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            inside = root / "runs"
            inside.mkdir()
            checkpoint = inside / "checkpoints.json"
            checkpoint.write_text(json.dumps({"sampler_path": "tinker://synthetic:train:0/sampler_weights/test"}))
            with patch.object(adapter.ev, "RUNS_ROOT", inside):
                self.assertEqual(adapter.checkpoint_identity(checkpoint)[0], "tinker://synthetic:train:0/sampler_weights/test")
                outside = root / "outside.json"
                outside.write_bytes(checkpoint.read_bytes())
                with self.assertRaises(adapter.ev.EvaluationError):
                    adapter.checkpoint_identity(outside)
                link = inside / "link.json"
                link.symlink_to(checkpoint)
                with self.assertRaises(adapter.ev.EvaluationError):
                    adapter.checkpoint_identity(link)

    def test_adapter_sampler_receives_checkpoint_not_base_only(self):
        config = {"model": "thinkingmachines/Inkling", "timeout_seconds": 240,
                  "adapter_sampler_path": "tinker://synthetic/sampler_weights/test"}
        service = MagicMock()
        service.create_sampling_client.return_value.get_base_model.return_value = config["model"]
        with patch("tinker.ServiceClient", return_value=service), \
             patch.object(adapter.comparison, "load_pinned_tokenizer"), \
             patch.object(adapter.comparison, "TmlProfile"):
            adapter.AdapterTransport().initialize(config, "synthetic-test-key")
        kwargs = service.create_sampling_client.call_args.kwargs
        self.assertEqual(kwargs["model_path"], config["adapter_sampler_path"])
        self.assertNotIn("base_model", kwargs)

    def test_wrong_checkpoint_base_is_rejected(self):
        service = MagicMock()
        service.create_sampling_client.return_value.get_base_model.return_value = "wrong/base"
        with patch("tinker.ServiceClient", return_value=service), \
             patch.object(adapter.comparison, "load_pinned_tokenizer"), \
             patch.object(adapter.comparison, "TmlProfile"):
            with self.assertRaises(adapter.ev.EvaluationError):
                adapter.AdapterTransport().initialize(
                    {"model": "thinkingmachines/Inkling", "timeout_seconds": 240,
                     "adapter_sampler_path": "tinker://synthetic/sampler_weights/test"}, "synthetic-test-key")


if __name__ == "__main__":
    unittest.main()
