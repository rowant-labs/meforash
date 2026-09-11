"""Bounded offline and synthetic-transport tests for Candidate G training."""
import copy
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from bibleprep import train_candidate_g as subject
from bibleprep import train_inkling as raw
from bibleprep import train_instruction as v1


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True))


def row(row_id, language="hbo"):
    ids = [200002, 10, 11, 12]
    return {"input_ids": ids, "target_ids": [10, 11, 12, 200006],
            "weights": [0.0, 1.0, 1.0, 1.0], "id": row_id,
            "language": language}


class FakeTransport:
    def __init__(self, output, fail=None):
        self.output, self.fail = output, fail
        self.calls, self.closed = [], False

    def __call__(self, operation, rows, settings):
        self.calls.append(operation)
        assert (self.output / "sequence-reservation.json").is_file()
        assert settings["arm"] == "G" and settings["seed"] == 20260909
        assert settings["adam"]["learning_rate"] == 2e-5
        assert settings["timeout_seconds"] == 600
        assert all(set(item) == {"input_ids", "target_ids", "weights"} for item in rows)
        if operation == self.fail:
            raise RuntimeError("synthetic private failure detail")
        if rows:
            return {"logprobs": [[-1.0] * len(item["weights"]) for item in rows]}
        if operation == "state":
            return {"path": "tinker://synthetic/weights/candidate-g"}
        if operation == "sampler":
            return {"path": "tinker://synthetic/sampler_weights/candidate-g"}
        return {}

    def close(self):
        self.closed = True


class CandidateGRunnerTests(unittest.TestCase):
    def test_config_and_weights_only_native_branch_are_exact(self):
        subject.Config().validate()
        for changes in ({"seed": 1}, {"batch_size": 8}, {"learning_rate": 1e-4},
                        {"timeout_seconds": 601}, {"run_dir": "runs/other"},
                        {"sequence_cap_usd": 21}):
            with self.subTest(changes=changes), self.assertRaises(raw.TrainingError):
                subject.Config(**changes).validate()
        session = subject.CandidateGNativeSession()
        session.client, session.source_verified = MagicMock(), True
        settings = {"arm": "G", "seed": 20260909,
                    "adam": {"learning_rate": 2e-5},
                    "source_checkpoint": "tinker://synthetic/weights/B",
                    "timeout_seconds": 600}
        original = copy.deepcopy(settings)
        session.call("load_weights", [], settings)
        self.assertEqual(settings, original)
        session.client.load_state.assert_called_once_with(settings["source_checkpoint"])
        session.client.load_state_with_optimizer.assert_not_called()
        with self.assertRaises(raw.TrainingError):
            session.call("load_weights", [], settings)

    def test_actual_retention_loader_uses_exact_raw12_and_v3_english16(self):
        retained = subject._retention_rows(subject.ROOT)
        self.assertEqual(len(retained["raw"]), 12)
        self.assertEqual(len(retained["legacy"]), 16)
        self.assertEqual([x["id"] for x in retained["raw"]],
                         retained["bindings"]["raw_holdout_ids"])
        self.assertEqual([x["id"] for x in retained["legacy"]],
                         retained["bindings"]["legacy_validation_ids"])
        self.assertIn("instruction-v3", retained["bindings"]["legacy_validation"]["path"])

    def test_preflight_age_is_execution_only_but_expiry_is_current_at_execution(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            snapshot = (subject.ROOT / subject.PRICE_SNAPSHOT).read_bytes()
            snapshot_path = root / subject.PRICE_SNAPSHOT
            snapshot_path.parent.mkdir(parents=True)
            snapshot_path.write_bytes(snapshot)
            metadata = json.loads((subject.ROOT / subject.PREFLIGHT).read_bytes())
            old = datetime.now(timezone.utc) - timedelta(days=2)
            metadata["observed_at_utc"] = old.isoformat()
            for item in metadata["checkpoints"]:
                item["expires_at_utc"] = (datetime.now(timezone.utc) + timedelta(days=2)).isoformat()
            metadata["price"]["snapshot_sha256"] = raw.digest(snapshot)
            write_json(root / subject.PREFLIGHT, metadata)
            subject._preflight(root, require_fresh=False)
            with self.assertRaisesRegex(raw.TrainingError, "within 24 hours"):
                subject._preflight(root, require_fresh=True)
            metadata["observed_at_utc"] = datetime.now(timezone.utc).isoformat()
            metadata["checkpoints"][0]["expires_at_utc"] = (
                datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
            write_json(root / subject.PREFLIGHT, metadata)
            with self.assertRaisesRegex(raw.TrainingError, "remain unexpired"):
                subject._preflight(root, require_fresh=True)

    def test_preparation_manifest_contract_binds_compiler_summary_and_inputs(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            input_path = root / "inputs/review.json"
            input_path.parent.mkdir(parents=True)
            input_path.write_text("review")
            (root / "prepared").mkdir(parents=True)
            (root / "prepared/fake.jsonl").write_bytes(b"x")
            fake_hash = "a" * 64
            settings = {"thinking_effort_numeric": 0.7, "maximum_input_tokens": 8192,
                        "truncation": "forbidden", "reasoning_targets": False,
                        "rejected_guidance_suffix_adopted": False}
            summary = {"artifact_kind": "candidate_g_prepared_dataset_summary_v1",
                       "status": "prepared_offline_not_trained",
                       "counts": {"train": 96, "validation": 24, "new": 104, "rehearsal": 16},
                       "settings": settings, "expert_certified": False,
                       "training_authorized": False,
                       "artifacts": {"train": {"sha256": fake_hash, "rows": 96, "bytes": 1},
                                     "validation": {"sha256": fake_hash, "rows": 24, "bytes": 1}}}
            write_json(root / "prepared/summary.json", summary)
            artifact = {"path": "prepared/fake.jsonl", "sha256": fake_hash, "rows": 96,
                        "processed_tokens": 384, "loss_tokens": 288,
                        "maximum_input_tokens": 4, "language_rows": {"hbo": 96}}
            val = {**artifact, "rows": 24, "processed_tokens": 96, "loss_tokens": 72,
                   "language_rows": {"hbo": 24}}
            manifest = {"schema_version": 1,
                        "artifact_kind": "candidate_g_prepared_dataset_manifest_v1",
                        "status": "prepared_offline_not_trained", "model": subject.MODEL,
                        "artifacts": {"train": artifact, "validation": val},
                        "settings": settings, "tokenizer": {"fixture": "pinned"},
                        "input_files": [{"path": "inputs/review.json",
                                         "sha256": raw.digest(input_path.read_bytes())}],
                        "compiler_summary": {"path": "prepared/summary.json",
                            "sha256": raw.digest((root / "prepared/summary.json").read_bytes())},
                        "counts": summary["counts"], "created_at_utc": "fixture",
                        "expert_certified": False, "model_calls": 0, "training_calls": 0}
            write_json(root / "prepared/manifest.json", manifest)
            fake_rows = [row("x" + str(i)) for i in range(96)]
            with patch.object(subject, "_prepared_rows", side_effect=[fake_rows, fake_rows[:24]]):
                entry, loaded = subject._load_preparation(root, "prepared/manifest.json")
            self.assertEqual(loaded, manifest)
            self.assertEqual(entry["sha256"], raw.digest((root / "prepared/manifest.json").read_bytes()))
            manifest["artifact_kind"] = "wrong"
            write_json(root / "prepared/manifest.json", manifest)
            with self.assertRaises(raw.TrainingError):
                subject._load_preparation(root, "prepared/manifest.json")


class CandidateGExecutionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "runs/candidate-g-execution-v1").mkdir(parents=True)
        self.output = self.root / subject.RUN_DIRECTORY
        languages = ("hbo", "grc", "arc")
        train = [row("T" + str(i), languages[i % 3]) for i in range(96)]
        self.batches = [train[i:i + 16] for i in range(0, 96, 16)]
        self.validation = [row("V" + str(i), languages[i % 3]) for i in range(24)]
        self.raw_holdout = [row("R" + str(i), languages[i % 3]) for i in range(12)]
        self.legacy = [row("L" + str(i), languages[i % 3]) for i in range(16)]
        counts = {"training_sequences": 96, "training_batches": 6,
                  "training_processed_tokens": 384, "training_loss_tokens": 288,
                  "candidate_g_validation_sequences": 24, "candidate_g_two_forward_tokens": 192,
                  "raw_retention_sequences": 12, "raw_two_forward_tokens": 96,
                  "legacy_english_retention_sequences": 16,
                  "legacy_english_two_forward_tokens": 128}
        recipe = {"adam": {"learning_rate": 2e-5}, "validation_ids": [x["id"] for x in self.validation]}
        breakdown = {"training": 384 * raw.TOKEN_NANO,
                     "candidate_g_validation_before_after": 192 * raw.TOKEN_NANO,
                     "raw_12_retention_before_after": 96 * raw.TOKEN_NANO,
                     "legacy_english_16_retention_before_after": 128 * raw.TOKEN_NANO,
                     "checkpoint_and_storage": 3 * raw.NANO,
                     "fresh_b_g_sampling": subject.SAMPLE_RESERVE_NANO,
                     "hosting_probe": subject.HOSTING_PROBE_NANO}
        self.protocol = {"recipe": recipe, "recipe_sha256": raw.digest(raw.encoded(recipe)),
                         "source_adapter": {"fixture": "B"}, "counts": counts,
                         "sequence_order_sha256": "c" * 64, "software_sha256": {},
                         "preflight": {}, "pricing": {}, "evaluation_protocol_path": subject.EVALUATION_PROTOCOL,
                         "budget": {"sequence_cap_nano_usd": subject.SEQUENCE_CAP_NANO,
                                    "breakdown_nano_usd": breakdown,
                                    "total_reserved_nano_usd": sum(breakdown.values()),
                                    "headroom_nano_usd": subject.SEQUENCE_CAP_NANO - sum(breakdown.values()),
                                    "cost_status": "conservative_all_in_reservation_not_invoice"}}
        self.plan = {"schema_version": 1, "phase": "candidate_g_instruction", "arm": "G",
                     "parent_arm": "B", "recipe": recipe, "recipe_sha256": self.protocol["recipe_sha256"],
                     "training_protocol_sha256": "a" * 64, "source_adapter": self.protocol["source_adapter"],
                     "source_checkpoint_file": subject.SOURCE_CHECKPOINT_FILE, "software_sha256": {},
                     "counts": counts, "sequence_order_sha256": self.protocol["sequence_order_sha256"],
                     "fresh_training_client": True, "fresh_adapter": False, "optimizer_restored": False,
                     "checkpoint_ttl_seconds": 2592000, "budget": self.protocol["budget"],
                     "preflight": {}, "pricing": {}, "execution_requires_frozen_evaluation": True}
        self.patches = [
            patch.object(subject, "make_plan", return_value=(self.plan, self.batches, self.validation,
                                                               self.raw_holdout, self.legacy)),
            patch.object(subject, "load_training_protocol", return_value=(self.protocol, "a" * 64)),
            patch.object(subject, "verify_evaluation_freeze", return_value="b" * 64),
            patch.object(subject, "_preflight", return_value={}),
            patch.object(v1, "source_receipt", return_value=(self.protocol["source_adapter"],
                                                              "tinker://synthetic/weights/B")),
        ]
        for item in self.patches:
            item.start()
        self.addCleanup(patch.stopall)

    def execute(self, fail=None):
        transport = FakeTransport(self.output, fail)
        result = subject.run(subject.Config(), execute=True, root=self.root, transport=transport)
        return result, transport

    def test_dry_run_is_offline_and_six_updates_are_durably_reserved(self):
        with patch("bibleprep.environment.load_project_environment") as environment, \
                patch.object(raw, "BoundedTrainingTransport") as native:
            dry = subject.run(subject.Config(), root=self.root)
        self.assertEqual(dry["status"], "dry_run")
        environment.assert_not_called()
        native.assert_not_called()
        result, transport = self.execute()
        self.assertEqual(transport.calls[:7], ["create", "verify_client", "verify_source",
                                               "load_weights", "forward", "forward", "forward"])
        self.assertEqual(transport.calls.count("forward_backward"), 6)
        self.assertEqual(transport.calls.count("optim"), 6)
        self.assertEqual(transport.calls[-5:], ["forward", "forward", "forward", "state", "sampler"])
        self.assertTrue(transport.closed)
        self.assertEqual(result["training_batches"], 6)
        reservation = json.loads((self.output / "sequence-reservation.json").read_bytes())
        self.assertEqual(reservation["total_reserved_nano_usd"],
                         self.protocol["budget"]["total_reserved_nano_usd"])
        self.assertLessEqual(reservation["total_reserved_nano_usd"], 20 * raw.NANO)

    def test_uncertain_operation_is_not_retried_and_completion_verifier_detects_tamper(self):
        with self.assertRaises(raw.TrainingError):
            self.execute("optim")
        events = (self.output / "events.jsonl").read_text()
        self.assertEqual(events.count('"operation":"optim"'), 2)
        self.assertIn("operation_uncertain", events)
        self.assertNotIn("synthetic private failure detail", events)

        # A fresh fixture completes and is then verified against every journal operation.
        self.temp.cleanup()
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "runs/candidate-g-execution-v1").mkdir(parents=True)
        self.output = self.root / subject.RUN_DIRECTORY
        self.execute()
        with patch.object(subject, "verified_rows", return_value=(self.batches, self.validation,
                                                                    self.raw_holdout, self.legacy)):
            sampler, checkpoint_hash = subject.verify_completed_checkpoint(
                self.root, subject.RUN_DIRECTORY + "/checkpoints.json")
            self.assertIn("sampler_weights", sampler)
            self.assertEqual(checkpoint_hash,
                             raw.digest((self.output / "checkpoints.json").read_bytes()))
            journal = self.output / "events.jsonl"
            lines = journal.read_bytes().splitlines()
            journal.write_bytes(b"\n".join(lines[:-2]) + b"\n")
            with self.assertRaises(raw.TrainingError):
                subject.verify_completed_checkpoint(
                    self.root, subject.RUN_DIRECTORY + "/checkpoints.json")


if __name__ == "__main__":
    unittest.main()
