"""Constructed offline tests for Candidate G receipt masking and review gates."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from bibleprep import candidate_g_review as review
from bibleprep import evaluate_candidate_g as collection_impl
from bibleprep import guidance_collection
from bibleprep import train_inkling as raw


def digest(text):
    return hashlib.sha256(text.encode()).hexdigest()


class Renderer:
    def render(self, payload, settings):
        material = review.canonical_bytes({"payload": payload, "settings": settings})
        return list(material[:80]), {}


class CandidateGReviewTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.run_dir = self.root / collection_impl.LIVE_RUN_PATH
        layout = ([('hbo', 'direct')] * 5 + [('grc', 'direct')] * 4
                  + [('arc', 'direct')] * 3 + [('hbo', 'boundary')] * 3
                  + [('grc', 'boundary')] * 2 + [('arc', 'boundary')]
                  + [('hbo', 'intent')] * 2 + [('grc', 'intent')] * 2
                  + [('arc', 'intent')] * 2 + [('en', 'general')] * 6)
        self.cases = []
        for index, (language, group) in enumerate(layout):
            case_id = f"Q{index:02d}"
            general = group == "general"
            evidence = "" if general else f"Constructed {language} source evidence."
            case = {
                "id": case_id, "language": language, "group": group,
                "prompt": f"Constructed prompt {index}?",
                "provided_evidence": evidence,
                "rubric": {
                    "required_points": ["Answer the constructed request."],
                    "acceptable_alternatives": [],
                    "error_conditions": ["Do not invent a material claim."],
                    "source_support": [] if general else ["Constructed source support."],
                },
                "source_refs": [] if general else [f"source:{case_id}"],
                "chapter_keys": [] if general else [f"book:{index + 1}"],
                "known_exposure": ["Constructed fixture; no exposure claim."],
            }
            self.cases.append(case)
        self.renderer = Renderer()
        self._build_frozen_fixture()
        self.seed = bytes(range(32))

    def _write(self, relative, value):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(review.canonical_bytes(value) + b"\n")
        return path

    def _entry(self, relative):
        return {"path": relative, "sha256": review.file_sha256(self.root / relative)}

    def _build_frozen_fixture(self):
        baseline = self._write(collection_impl.BASELINE,
                               {"system_prompt": "Fixed baseline."})
        questions_rel = "runs/candidate-g-execution-v1/evaluation/constructed-questions.json"
        self._write(questions_rel, {"cases": self.cases})
        protocol = {
            "status": "frozen_before_training_and_generation",
            "case_count": 30, "slot_count": 60,
            "sampling": dict(collection_impl.SETTINGS),
            "sampling_reserve_nano_usd": collection_impl.SAMPLE_RESERVE_NANO,
            "automatic_promotion": False,
            "system_prompt_sha256": digest("Fixed baseline."),
            "questions": self._entry(questions_rel),
            "immutable_files": [self._entry(collection_impl.BASELINE)],
        }
        self.protocol_path = self._write(collection_impl.PROTOCOL_PATH, protocol)
        self.prepared = collection_impl.prepare(
            self.root, self.protocol_path, renderer=self.renderer)
        self.requests = self.prepared["requests"]
        self._write(collection_impl.TRAINING_PROTOCOL_PATH, {"constructed": True})
        training_sha = review.file_sha256(self.root / collection_impl.TRAINING_PROTOCOL_PATH)
        sequence = {
            "event": "candidate_g_full_sequence_reserved", "run_id": "constructed-run",
            "training_protocol_sha256": training_sha,
            "evaluation_protocol_sha256": self.prepared["protocol_sha256"],
            "breakdown_nano_usd": {"fresh_b_g_sampling":
                                    collection_impl.SAMPLE_RESERVE_NANO},
            "total_reserved_nano_usd": collection_impl.SAMPLE_RESERVE_NANO,
            "invoice_reconciled": False,
        }
        self._write(collection_impl.SEQUENCE_RESERVATION_PATH, sequence)
        sequence_binding = collection_impl._sequence_reservation(
            self.root, self.prepared["protocol_sha256"])
        reservation = {
            "schema_version": 1, "event": "candidate_g_sampling_phase_reserved",
            "run_path": collection_impl.LIVE_RUN_PATH,
            "sampling_reserved_nano_usd": collection_impl.SAMPLE_RESERVE_NANO,
            "transport_budget_usd": "3.219456",
            "protocol_sha256": self.prepared["protocol_sha256"],
            "prepared_sha256": collection_impl._digest(self.prepared),
            "sequence_reservation": sequence_binding,
            "automatic_retry": False, "resume_supported": False,
            "invoice_reconciled": False,
        }
        self._write(collection_impl.SAMPLING_RESERVATION_PATH, reservation)
        b_path = self._write(collection_impl.B_CHECKPOINT_PATH, {"checkpoint": "B"})
        g_path = self._write(collection_impl.G_CHECKPOINT_PATH, {"checkpoint": "G"})
        checkpoints = {"B": self._entry(str(b_path.relative_to(self.root))),
                       "G": self._entry(str(g_path.relative_to(self.root)))}
        self.run_dir.mkdir(parents=True)
        (self.run_dir / "receipts").mkdir()
        (self.run_dir / "events.jsonl").write_bytes(b"")
        manifest = {
            "schema_version": 1,
            "artifact_kind": "candidate_g_native_collection_manifest_v1",
            "protocol_sha256": self.prepared["protocol_sha256"],
            "prepared_sha256": collection_impl._digest(self.prepared),
            "slot_count": 60, "checkpoint_files": checkpoints,
            "sequence_reservation": sequence_binding,
            "sampling_reservation_sha256": review.file_sha256(
                self.root / collection_impl.SAMPLING_RESERVATION_PATH),
            "sampling_reserved_nano_usd": collection_impl.SAMPLE_RESERVE_NANO,
            "transport_budget_usd": "3.219456", "automatic_retry": False,
            "resume_supported": False,
        }
        self._write(str((self.run_dir / "manifest.json").relative_to(self.root)), manifest)

    @staticmethod
    def normalizer(response, _run_dir):
        return response["constructed_normalized"]

    def response(self, request, text, stop="stop"):
        raw_hash = digest("raw-" + request["slot_id"])
        diagnostic_hash = digest("diagnostic-" + request["slot_id"])
        return {
            "model": "thinkingmachines/Inkling",
            "usage": {"prompt_tokens": request["exact_input_tokens"],
                      "completion_tokens": 5},
            "native_tinker": {"prompt_sha256": request[
                "prompt_token_ids_sha256"]},
            "constructed_normalized": {
                "stop_reason": stop, "final_text": text,
                "diagnostic_sha256": diagnostic_hash,
                "raw_generated_token_ids_sha256": raw_hash,
                "native_prompt_sha256": request["prompt_token_ids_sha256"],
            },
        }

    def collection(self, terminal=None):
        for path in (self.run_dir / "receipts").iterdir():
            path.unlink()
        (self.run_dir / "events.jsonl").write_bytes(b"")
        results, stopped = [], False
        events = []
        for index, request in enumerate(self.requests):
            if stopped:
                results.append(collection_impl._result(request, "unsubmitted"))
                continue
            events.append({"event": "submitted", "slot_id": request["slot_id"],
                           "request_sha256": collection_impl._digest(request),
                           "reserved_nano_usd": collection_impl.PER_SLOT_RESERVE_NANO})
            if terminal == "uncertain" and index == 0:
                receipt = {"schema_version": 1,
                           "artifact_kind": "candidate_g_uncertain_response_receipt_v1",
                           "prepared_sha256": collection_impl._digest(self.prepared),
                           "request": request,
                           "request_sha256": collection_impl._digest(request),
                           "response_received": False, "response": None,
                           "exception_type": "TimeoutError"}
                rel = "receipts/" + request["slot_id"] + "-uncertain.json"
                path = self._write(str((self.run_dir / rel).relative_to(self.root)), receipt)
                receipt_sha = review.file_sha256(path)
                events.append({"event": "uncertain", "slot_id": request["slot_id"],
                               "status": "uncertain", "receipt_path": rel,
                               "receipt_sha256": receipt_sha})
                results.append(collection_impl._result(
                    request, "uncertain", receipt_sha256=receipt_sha))
                stopped = True
                continue
            partial = terminal == "partial" and index == 0
            text = "Constructed partial answer." if partial else (
                "Constructed complete answer for " + request["slot_id"] + ".")
            response = self.response(request, text, "output_limit" if partial else "stop")
            facts = guidance_collection._validated_normalized(
                response, self.normalizer(response, self.run_dir), request)
            receipt = {"schema_version": 1,
                       "artifact_kind": "candidate_g_response_receipt_v1",
                       "prepared_sha256": collection_impl._digest(self.prepared),
                       "request": request,
                       "request_sha256": collection_impl._digest(request),
                       "response": response, "normalized": facts}
            rel = "receipts/" + request["slot_id"] + ".json"
            path = self._write(str((self.run_dir / rel).relative_to(self.root)), receipt)
            receipt_sha = review.file_sha256(path)
            result = collection_impl._result(
                request, facts["status"], facts=facts, receipt_sha256=receipt_sha)
            results.append(result)
            events.append({"event": "result", "slot_id": request["slot_id"],
                           "status": facts["status"], "receipt_path": rel,
                           "receipt_sha256": receipt_sha})
            if partial:
                stopped = True
        with (self.run_dir / "events.jsonl").open("wb") as handle:
            for event in events:
                handle.write(review.canonical_bytes(event) + b"\n")
        result = collection_impl._summary(self.prepared, results, terminal)
        self._write(str((self.run_dir / "collection.json").relative_to(self.root)), result)
        return result

    def packets(self, collection):
        with mock.patch.object(collection_impl, "_verify_checkpoints", return_value={}):
            return review.export_masked_packets(
                self.root, self.cases, self.prepared, collection, self.run_dir,
                self.seed, renderer=self.renderer, normalize_response=self.normalizer)

    def integrate(self, collection, individual, ir, pairs, pr, private_map, **kwargs):
        with mock.patch.object(collection_impl, "_verify_checkpoints", return_value={}):
            return review.integrate_reviews(
                self.root, self.cases, self.prepared, collection, self.run_dir,
                self.seed, individual, ir, pairs, pr, private_map,
                individual_review_sha256=review.canonical_sha256(ir),
                pair_review_sha256=review.canonical_sha256(pr), renderer=self.renderer,
                normalize_response=self.normalizer, **kwargs)

    def individual_review(self, packet):
        assessments = []
        for row in packet["candidates"]:
            common = {"candidate_id": row["candidate_id"],
                      "answer_sha256": row["answer_sha256"],
                      "receipt_sha256": row["receipt_sha256"]}
            if row["reviewable"]:
                common.update({field: False for field in review.FINDING_FIELDS})
                common.update(general_semantically_correct=(
                    True if row["group"] == "general" else None),
                    specific_rationale="Constructed review only.",
                    evidence_refs=["constructed:answer"])
            else:
                common.update({field: None for field in review.FINDING_FIELDS})
                common.update(general_semantically_correct=None,
                              specific_rationale="No returned answer; no semantic grade.",
                              evidence_refs=[])
            assessments.append(common)
        return {
            "schema_version": 1,
            "artifact_kind": "frozen_candidate_g_individual_review_v1",
            "review_id": "constructed-individual", "packet_sha256": review.canonical_sha256(packet),
            "reviewer_kind": "ai", "reviewer_role": "Constructed individual reviewer",
            "conflicts": ["Constructed same-project fixture."],
            "expert_certified": False, "mapping_accessed": False,
            "assessments": assessments,
            "limitations": ["Constructed data only."],
        }

    def pair_review(self, packet):
        return {
            "schema_version": 1,
            "artifact_kind": "frozen_candidate_g_pair_review_v1",
            "review_id": "constructed-pair", "packet_sha256": review.canonical_sha256(packet),
            "reviewer_kind": "ai", "reviewer_role": "Constructed pair reviewer",
            "conflicts": ["Constructed same-project fixture."],
            "expert_certified": False, "mapping_accessed": False,
            "assessments": [{
                "pair_id": row["pair_id"],
                "left_answer_sha256": row["left"]["answer_sha256"],
                "right_answer_sha256": row["right"]["answer_sha256"],
                "preference": "tie" if row["pair_complete"] else "unavailable",
                "rationale": "Constructed comparison only.",
                "evidence_refs": ["constructed:left", "constructed:right"],
            } for row in packet["pairs"]],
            "limitations": ["Constructed data only."],
        }

    def test_complete_export_masks_all_arm_transport_and_checkpoint_hints(self):
        collection = self.collection()
        individual, pairs, private_map = self.packets(collection)
        self.assertEqual(len(individual["candidates"]), 60)
        self.assertEqual(len(pairs["pairs"]), 30)
        public = json.dumps([individual, pairs], ensure_ascii=False)
        for forbidden in ('"arm"', 'elapsed_seconds', 'checkpoint_files',
                          'adapter_sampler_path'):
            self.assertNotIn(forbidden, public)
        self.assertEqual({x["arm"] for x in private_map["candidates"]}, {'B', 'G'})
        self.assertEqual({x["left"]["arm"] for x in private_map["pairs"]}, {'B', 'G'})
        self.assertTrue(all(x["rubric"]["required_points"]
                            for x in individual["candidates"]))

    def test_collector_reverification_and_supplied_summary_equality_are_required(self):
        collection = self.collection()
        bad = copy.deepcopy(collection)
        bad["results"][0]["receipt_sha256"] = "0" * 64
        with self.assertRaisesRegex(review.CandidateGReviewError, "Supplied collection"):
            self.packets(bad)
        receipt = next((self.run_dir / "receipts").iterdir())
        saved = json.loads(receipt.read_text())
        saved["response"]["native_tinker"]["prompt_sha256"] = "0" * 64
        receipt.write_bytes(review.canonical_bytes(saved) + b"\n")
        with mock.patch.object(collection_impl, "_verify_checkpoints", return_value={}):
            with self.assertRaisesRegex(review.CandidateGReviewError, "does not reverify"):
                review.export_masked_packets(
                    self.root, self.cases, self.prepared, collection, self.run_dir,
                    self.seed, renderer=self.renderer, normalize_response=self.normalizer)

    def test_changed_prepared_and_review_metadata_fail_against_frozen_questions(self):
        collection = self.collection()
        bad_prepared = copy.deepcopy(self.prepared)
        bad_prepared["requests"][0]["payload"]["messages"][1]["content"] += " changed"
        with mock.patch.object(collection_impl, "_verify_checkpoints", return_value={}):
            with self.assertRaisesRegex(review.CandidateGReviewError, "Prepared payload"):
                review.export_masked_packets(
                    self.root, self.cases, bad_prepared, collection, self.run_dir,
                    self.seed, renderer=self.renderer, normalize_response=self.normalizer)
        bad_cases = copy.deepcopy(self.cases)
        bad_cases[0]["rubric"]["required_points"] = ["Changed after freeze."]
        with self.assertRaisesRegex(review.CandidateGReviewError, "frozen questions"):
            review.export_masked_packets(
                self.root, bad_cases, self.prepared, collection, self.run_dir,
                self.seed, renderer=self.renderer, normalize_response=self.normalizer)

    def test_partial_is_reviewable_and_missing_has_null_semantic_grade(self):
        collection = self.collection("partial")
        individual, pairs, _ = self.packets(collection)
        partial = next(x for x in individual["candidates"] if x["answer_status"] == "partial")
        self.assertTrue(partial["reviewable"])
        self.assertIsNotNone(partial["answer_text"])
        self.assertEqual(sum(not x["reviewable"] for x in individual["candidates"]), 59)
        individual_review = self.individual_review(individual)
        review.freeze_individual_review(individual, individual_review)
        pair_review = self.pair_review(pairs)
        review.freeze_pair_review(pairs, pair_review)
        missing = next(x for x in individual_review["assessments"]
                       if x["answer_sha256"] is None)
        self.assertTrue(all(missing[field] is None for field in review.FINDING_FIELDS))
        self.assertEqual(missing["evidence_refs"], [])

    def test_uncertain_response_is_not_semantically_reviewed(self):
        collection = self.collection("uncertain")
        individual, _, _ = self.packets(collection)
        uncertain = next(x for x in individual["candidates"]
                         if x["answer_status"] == "uncertain")
        self.assertFalse(uncertain["reviewable"])
        self.assertIsNone(uncertain["answer_text"])

    def test_freeze_and_private_map_regeneration_reject_changes(self):
        collection = self.collection()
        individual, pairs, private_map = self.packets(collection)
        ir, pr = self.individual_review(individual), self.pair_review(pairs)
        review.freeze_individual_review(individual, ir)
        review.freeze_pair_review(pairs, pr)
        bad = copy.deepcopy(private_map)
        bad["pairs"][0]["left"]["arm"] = 'G' if (
            bad["pairs"][0]["left"]["arm"] == 'B') else 'B'
        with self.assertRaisesRegex(review.CandidateGReviewError, "Private map"):
            self.integrate(collection, individual, ir, pairs, pr, bad)

    def test_integration_reports_counts_pending_retention_and_never_promotes(self):
        collection = self.collection()
        individual, pairs, private_map = self.packets(collection)
        ir, pr = self.individual_review(individual), self.pair_review(pairs)
        result = self.integrate(collection, individual, ir, pairs, pr, private_map)
        self.assertEqual(result["status_counts"], {'B': {'complete': 30},
                                                   'G': {'complete': 30}})
        self.assertEqual(result["preferences"]["bible"], {'tie': 24})
        self.assertEqual(result["retention_gate"]["status"], "pending")
        self.assertFalse(result["combined_gate"]["passed"])
        self.assertEqual(result["recommendation"], "retain_B")
        self.assertFalse(result["automatic_promotion"])

    def test_retention_is_derived_from_verified_fixed_training_receipts(self):
        collection = self.collection()
        individual, pairs, private_map = self.packets(collection)
        ir, pr = self.individual_review(individual), self.pair_review(pairs)
        training = self.root / review.training_impl.RUN_DIRECTORY
        training.mkdir(parents=True, exist_ok=True)
        (training / "checkpoints.json").write_text("{}")
        (training / "events.jsonl").write_text("{}\n")
        def metric(value, languages):
            return {"weighted_nll": value,
                    "by_language": {language: {"weighted_nll": value}
                                    for language in languages}}
        summary = {
            "baseline_raw_12_retention": metric(1.0, ["hbo", "grc"]),
            "end_raw_12_retention": metric(1.05, ["hbo", "grc"]),
            "baseline_legacy_english_16_retention": metric(
                1.0, ["hbo", "grc", "arc"]),
            "end_legacy_english_16_retention": metric(
                1.1, ["hbo", "grc", "arc"]),
        }
        (training / "summary.json").write_text(json.dumps(summary))
        receipt = {name + "_file_sha256": review.file_sha256(training / (name + suffix))
                   for name, suffix in (("checkpoint", "s.json"),
                                        ("summary", ".json"),
                                        ("events", ".jsonl"))}
        def verified(_root, relative):
            self.assertEqual(relative, str(
                (training / "checkpoints.json").relative_to(self.root)))
            return "synthetic-sampler", receipt["checkpoint_file_sha256"]
        with mock.patch.object(review.training_impl, "verify_completed_checkpoint",
                               side_effect=verified):
            result = self.integrate(
                collection, individual, ir, pairs, pr, private_map,
                retention_receipt=receipt)
        self.assertEqual(result["retention_gate"]["status"], "complete")
        self.assertTrue(result["retention_gate"]["passed"])
        summary["end_legacy_english_16_retention"]["by_language"].pop("arc")
        (training / "summary.json").write_text(json.dumps(summary))
        receipt["summary_file_sha256"] = review.file_sha256(training / "summary.json")
        with mock.patch.object(review.training_impl, "verify_completed_checkpoint",
                               side_effect=verified):
            with self.assertRaisesRegex(review.CandidateGReviewError, "languages"):
                self.integrate(collection, individual, ir, pairs, pr, private_map,
                               retention_receipt=receipt)


if __name__ == '__main__':
    unittest.main()
