import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from bibleprep import evaluate_candidate_g as g


class Renderer:
    def render(self, payload, config):
        return list(range(len(payload["messages"][-1]["content"]))), None


class Transport:
    def __init__(self, outcome="complete", stop_at=0):
        self.outcome = outcome
        self.stop_at = stop_at
        self.calls = 0
        self.configs = []
        self.closed = 0

    def __call__(self, payload, config, secret):
        index = self.calls
        self.calls += 1
        self.configs.append(copy.deepcopy(config))
        if self.outcome == "uncertain" and index == self.stop_at:
            raise TimeoutError("private synthetic timeout")
        ids, _ = Renderer().render(payload, config)
        prompt_sha = g.diagnostics.token_ids_sha256(ids)
        status = self.outcome if index == self.stop_at else "complete"
        facts = {
            "stop_reason": "output_limit" if status == "partial" else "stop",
            "final_text": "partial answer" if status == "partial" else "complete answer",
            "diagnostic_sha256": "d" * 64,
            "raw_generated_token_ids_sha256": "e" * 64,
            "native_prompt_sha256": prompt_sha,
        }
        sidecars = Path(config["run_dir"]) / "native-sidecars"
        sidecars.mkdir(mode=0o700, exist_ok=True)
        sidecar = sidecars / f"{index:04d}.json"
        sidecar.write_text(json.dumps(facts, sort_keys=True))
        return {
            "model": g.MODEL,
            "usage": {"prompt_tokens": len(ids), "completion_tokens": 2},
            "native_tinker": {"prompt_sha256": prompt_sha},
            "sidecar_path": str(sidecar.relative_to(config["run_dir"])),
            "sidecar_sha256": g.sha(sidecar),
        }

    def close(self):
        self.closed += 1


def normalize(response, run_dir):
    path = Path(run_dir) / response["sidecar_path"]
    if g.sha(path) != response["sidecar_sha256"]:
        raise ValueError("native sidecar changed")
    return json.loads(path.read_text())


class CandidateGEvaluationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "runs/evidence-pilot-v1").mkdir(parents=True)
        (self.root / g.BASELINE).write_text(json.dumps({"system_prompt": "Fixed baseline."}))
        (self.root / "runs/candidate-g-execution-v1/evaluation").mkdir(parents=True)
        (self.root / "runs/candidate-g-execution-v1/training").mkdir(parents=True)
        (self.root / "runs/inkling-original-text-v1").mkdir(parents=True)
        self.protocol_path = self.root / g.PROTOCOL_PATH
        self.questions = self.protocol_path.parent / "questions.json"
        languages = ["hbo"] * 10 + ["grc"] * 8 + ["arc"] * 6 + ["en"] * 6
        groups = ["direct"] * 12 + ["boundary"] * 6 + ["intent"] * 6 + ["general"] * 6
        self.cases = []
        for index, (language, group) in enumerate(zip(languages, groups)):
            general = group == "general"
            self.cases.append({
                "id": f"Q{index:02}", "language": language, "group": group,
                "prompt": "Answer the question.",
                "provided_evidence": "Named original-language source text." if not general else "",
                "rubric": {
                    "required_points": ["Answer the request."],
                    "error_conditions": ["Do not invent material claims."],
                    "acceptable_alternatives": [],
                    "source_support": ["Use the supplied source."] if not general else [],
                },
                "source_refs": [f"source:Book.{index}.1"] if not general else [],
                "chapter_keys": [f"source:Book.{index}"] if not general else [],
                "known_exposure": ["new question; family exposure documented"],
            })
        self.protocol = {
            "status": "frozen_before_training_and_generation", "case_count": 30,
            "slot_count": 60, "sampling": g.SETTINGS,
            "sampling_reserve_nano_usd": g.SAMPLE_RESERVE_NANO,
            "automatic_promotion": False,
            "system_prompt_sha256": hashlib.sha256(b"Fixed baseline.").hexdigest(),
            "immutable_files": [],
        }
        self.training_protocol = self.root / g.TRAINING_PROTOCOL_PATH
        self.training_protocol.write_text(json.dumps({"frozen": True}))
        self.checkpoints = {}
        for arm, relative in (("B", g.B_CHECKPOINT_PATH), ("G", g.G_CHECKPOINT_PATH)):
            path = self.root / relative
            path.write_text(json.dumps({"sampler_path": arm}))
            self.checkpoints[arm] = {"path": relative, "sha256": g.sha(path)}
        self.write_cases()

    def write_cases(self):
        self.questions.write_text(json.dumps({"cases": self.cases}))
        self.protocol["questions"] = {
            "path": str(self.questions.relative_to(self.root)), "sha256": g.sha(self.questions)}
        self.protocol_path.write_text(json.dumps(self.protocol))

    def write_sequence_reservation(self):
        breakdown = {"training": 1000, "fresh_b_g_sampling": g.SAMPLE_RESERVE_NANO}
        value = {
            "schema_version": 1, "event": "candidate_g_full_sequence_reserved",
            "run_id": "fixture-run", "training_protocol_sha256": g.sha(self.training_protocol),
            "evaluation_protocol_sha256": g.sha(self.protocol_path),
            "sequence_cap_nano_usd": 20_000_000_000,
            "breakdown_nano_usd": breakdown,
            "total_reserved_nano_usd": sum(breakdown.values()),
            "headroom_nano_usd": 20_000_000_000 - sum(breakdown.values()),
            "cost_status": "conservative_all_in_reservation_not_invoice",
            "invoice_reconciled": False,
        }
        (self.root / g.SEQUENCE_RESERVATION_PATH).write_text(json.dumps(value))

    def prepared(self):
        return g.prepare(self.root, g.PROTOCOL_PATH, renderer=Renderer())

    def execute(self, outcome="complete", stop_at=0):
        self.write_sequence_reservation()
        prepared = self.prepared()
        transport = Transport(outcome, stop_at)
        checkpoint = lambda path: (json.loads(path.read_text())["sampler_path"], g.sha(path))
        with patch("bibleprep.evaluate_adapter.checkpoint_identity", side_effect=checkpoint), \
                patch.object(g.chat_model, "resolve_b_checkpoint", return_value="B"), \
                patch("bibleprep.train_candidate_g.verify_completed_checkpoint",
                      return_value=("G", self.checkpoints["G"]["sha256"])):
            result = g.collect(
                self.root, g.PROTOCOL_PATH, prepared, self.checkpoints,
                run_dir=g.LIVE_RUN_PATH, execute=True, secret="test-only",
                renderer=Renderer(), transport_factory=lambda arm: transport,
                normalizer=normalize)
        return prepared, result, transport

    def verify(self, prepared):
        checkpoint = lambda path: (json.loads(path.read_text())["sampler_path"], g.sha(path))
        with patch("bibleprep.evaluate_adapter.checkpoint_identity", side_effect=checkpoint), \
                patch.object(g.chat_model, "resolve_b_checkpoint", return_value="B"), \
                patch("bibleprep.train_candidate_g.verify_completed_checkpoint",
                      return_value=("G", self.checkpoints["G"]["sha256"])):
            return g.verify_collection(
                self.root, g.PROTOCOL_PATH, prepared, g.LIVE_RUN_PATH,
                renderer=Renderer(), normalizer=normalize)

    def test_prepare_hides_rubric_balances_order_and_resolves_fixed_path(self):
        result = self.prepared()
        self.assertEqual(len(result["requests"]), 60)
        self.assertEqual([x["arm"] for x in result["requests"][:4]], ["B", "G", "G", "B"])
        for first, second in zip(result["requests"][::2], result["requests"][1::2]):
            self.assertEqual(first["payload"], second["payload"])
            self.assertEqual(first["prompt_token_ids_sha256"], second["prompt_token_ids_sha256"])
            self.assertNotIn("Answer the request", json.dumps(first["payload"]))
        self.assertEqual(result, g.prepare(self.root, self.protocol_path, renderer=Renderer()))
        with self.assertRaisesRegex(ValueError, "fixed"):
            g.prepare(self.root, "runs/alternate.json", renderer=Renderer())

    def test_strict_case_schema_and_general_bible_boundaries(self):
        mutations = [
            lambda c: c[0].update({"extra": True}),
            lambda c: c[0].update({"known_exposure": []}),
            lambda c: c[0].update({"provided_evidence": ""}),
            lambda c: c[-1].update({"provided_evidence": "Bible text"}),
            lambda c: c[-1].update({"source_refs": ["x"]}),
            lambda c: c[0]["rubric"].update({"source_support": []}),
            lambda c: c[0]["rubric"].update({"extra": []}),
        ]
        original = copy.deepcopy(self.cases)
        for mutate in mutations:
            with self.subTest(mutate=mutate):
                self.cases = copy.deepcopy(original)
                mutate(self.cases)
                self.write_cases()
                with self.assertRaises(ValueError):
                    self.prepared()

    def test_changed_question_sampling_and_inventory_rejected(self):
        self.questions.write_text("{}")
        with self.assertRaises(ValueError):
            self.prepared()
        self.cases = copy.deepcopy(self.cases)
        self.write_cases()
        self.protocol["sampling"] = {**g.SETTINGS, "max_output_tokens": 16000}
        self.protocol_path.write_text(json.dumps(self.protocol))
        with self.assertRaises(ValueError):
            self.prepared()

    def test_complete_sixty_verifies_receipts_sidecars_cost_and_budget(self):
        prepared, result, transport = self.execute()
        self.assertEqual(result["status"], "complete")
        self.assertEqual(result["counts"], {"complete": 60})
        self.assertEqual(len(result["results"]), 60)
        self.assertEqual(len(list((self.root / g.LIVE_RUN_PATH / "receipts").iterdir())), 60)
        self.assertTrue(all(c["budget_usd"] == g.TRANSPORT_BUDGET_USD
                            for c in transport.configs))
        self.assertEqual(transport.calls, 60)
        self.assertGreaterEqual(transport.closed, 1)
        self.assertEqual(self.verify(prepared), result)

    def test_partial_output_limit_stops_and_verifies_60_slot_closure(self):
        prepared, result, transport = self.execute("partial", 1)
        self.assertEqual(transport.calls, 2)
        self.assertEqual(result["counts"], {"complete": 1, "partial": 1, "unsubmitted": 58})
        self.assertEqual(result["stop_reason"], "partial")
        self.assertEqual(self.verify(prepared), result)

    def test_uncertain_stops_without_retry_and_retains_reservation(self):
        prepared, result, transport = self.execute("uncertain")
        self.assertEqual(transport.calls, 1)
        self.assertEqual(result["counts"], {"uncertain": 1, "unsubmitted": 59})
        self.assertEqual(result["uncertain_reserved_nano_usd"], g.PER_SLOT_RESERVE_NANO)
        self.assertTrue(result["accounting_uncertain"])
        self.assertEqual(self.verify(prepared), result)

    def test_stale_after_one_stops_before_second_submission(self):
        self.write_sequence_reservation()
        prepared = self.prepared()
        transport = Transport()
        real_prepare = g.prepare
        calls = 0
        def changing_prepare(*args, **kwargs):
            nonlocal calls
            calls += 1
            value = real_prepare(*args, **kwargs)
            if calls >= 3:
                value = copy.deepcopy(value)
                value["settings"]["seed"] += 1
            return value
        checkpoint = lambda path: (json.loads(path.read_text())["sampler_path"], g.sha(path))
        with patch("bibleprep.evaluate_adapter.checkpoint_identity", side_effect=checkpoint), \
                patch.object(g.chat_model, "resolve_b_checkpoint", return_value="B"), \
                patch("bibleprep.train_candidate_g.verify_completed_checkpoint",
                      return_value=("G", self.checkpoints["G"]["sha256"])), \
                patch.object(g, "prepare", side_effect=changing_prepare):
            result = g.collect(self.root, g.PROTOCOL_PATH, prepared, self.checkpoints,
                run_dir=g.LIVE_RUN_PATH, execute=True, secret="test-only",
                renderer=Renderer(), transport_factory=lambda arm: transport,
                normalizer=normalize)
        self.assertEqual(transport.calls, 1)
        self.assertEqual(result["counts"], {"complete": 1, "unsubmitted": 59})
        self.assertEqual(result["stop_reason"], "pre_submission_verification_failed")
        self.assertEqual(self.verify(prepared), result)

    def test_repeat_and_alternate_run_directory_cannot_reserve_again(self):
        prepared, _, _ = self.execute("uncertain")
        with self.assertRaisesRegex(ValueError, "fixed"):
            g.collect(self.root, g.PROTOCOL_PATH, prepared, self.checkpoints,
                      run_dir="runs/alternate", execute=False, renderer=Renderer())
        checkpoint = lambda path: (json.loads(path.read_text())["sampler_path"], g.sha(path))
        with patch("bibleprep.evaluate_adapter.checkpoint_identity", side_effect=checkpoint), \
                patch.object(g.chat_model, "resolve_b_checkpoint", return_value="B"), \
                patch("bibleprep.train_candidate_g.verify_completed_checkpoint",
                      return_value=("G", self.checkpoints["G"]["sha256"])):
            with self.assertRaisesRegex(ValueError, "already"):
                g.collect(self.root, g.PROTOCOL_PATH, prepared, self.checkpoints,
                          run_dir=g.LIVE_RUN_PATH, execute=True, secret="test-only",
                          renderer=Renderer())

    def test_wrong_checkpoint_paths_and_sequence_sampling_budget_rejected(self):
        self.write_sequence_reservation()
        prepared = self.prepared()
        bad = copy.deepcopy(self.checkpoints)
        bad["B"]["path"] = g.G_CHECKPOINT_PATH
        with self.assertRaisesRegex(ValueError, "fixed B and G"):
            g.collect(self.root, g.PROTOCOL_PATH, prepared, bad,
                      run_dir=g.LIVE_RUN_PATH, execute=True, secret="test-only",
                      renderer=Renderer())
        path = self.root / g.SEQUENCE_RESERVATION_PATH
        reservation = json.loads(path.read_text())
        reservation["breakdown_nano_usd"]["fresh_b_g_sampling"] -= 1
        reservation["total_reserved_nano_usd"] -= 1
        path.write_text(json.dumps(reservation))
        checkpoint = lambda p: (json.loads(p.read_text())["sampler_path"], g.sha(p))
        with patch("bibleprep.evaluate_adapter.checkpoint_identity", side_effect=checkpoint), \
                patch.object(g.chat_model, "resolve_b_checkpoint", return_value="B"), \
                patch("bibleprep.train_candidate_g.verify_completed_checkpoint",
                      return_value=("G", self.checkpoints["G"]["sha256"])):
            with self.assertRaisesRegex(ValueError, "sequence reservation"):
                g.collect(self.root, g.PROTOCOL_PATH, prepared, self.checkpoints,
                          run_dir=g.LIVE_RUN_PATH, execute=True, secret="test-only",
                          renderer=Renderer())

    def test_verifier_rejects_native_receipt_event_manifest_and_summary_tamper(self):
        scenarios = ("sidecar", "receipt", "event", "manifest", "summary")
        for scenario in scenarios:
            with self.subTest(scenario=scenario):
                if scenario != scenarios[0]:
                    self.tearDown_fixture()
                prepared, _, _ = self.execute("partial", 1)
                live = self.root / g.LIVE_RUN_PATH
                if scenario == "sidecar":
                    path = live / "native-sidecars/0000.json"
                    path.write_text(path.read_text() + " ")
                elif scenario == "receipt":
                    path = sorted((live / "receipts").iterdir())[0]
                    path.write_text(path.read_text() + " ")
                elif scenario == "event":
                    path = live / "events.jsonl"
                    path.write_text(path.read_text().replace('"reserved_nano_usd":53657600',
                                                             '"reserved_nano_usd":1', 1))
                elif scenario == "manifest":
                    path = live / "manifest.json"
                    value = json.loads(path.read_text()); value["slot_count"] = 59
                    path.write_text(json.dumps(value))
                else:
                    path = live / "collection.json"
                    value = json.loads(path.read_text()); value["status"] = "complete"
                    path.write_text(json.dumps(value))
                with self.assertRaises(ValueError):
                    self.verify(prepared)

    def tearDown_fixture(self):
        self.temp.cleanup()
        self.setUp()


if __name__ == "__main__":
    unittest.main()
