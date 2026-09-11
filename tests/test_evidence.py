"""Mechanical evidence checks must not promote research drafts to authority."""
import copy
import json
from pathlib import Path
import tempfile
import unittest

from bibleprep.evidence import ROOT, PLAN, audit_directory, confined_path, snapshot_index, strict_load, validate_record


def decision(value="pending"):
    return {"decision": value, "basis": "Constructed test; no release decision.",
            "reviewer": None, "reviewed_on": None}


def fixture():
    return {
        "schema_version": 1, "id": "SYNTHETIC01", "kind": "textual_dossier", "status": "draft",
        "biblical_anchor_languages": ["greek"], "source_languages": ["english"],
        "chapter_keys": ["sblgnt:Mark.1"], "source_reference_systems": ["synthetic test"],
        "mapped_references": [], "mapping_citation_ids": [],
        "summary": "Constructed validator fixture, not biblical evidence.",
        "citations": [{"id": "C1", "source_id": "synthetic-source", "kind": "edition",
                       "author_or_institution": "Synthetic fixture", "title": "Synthetic source",
                       "locator": "synthetic line 1", "url": "https://example.org/synthetic",
                       "publication_date": None, "accessed_on": "2026-09-07",
                       "pinned_version": None, "content_sha256": None}],
        "readings": [{"id": "R1", "entity_type": "modern_edition", "stable_entity_id": "synthetic-edition",
                      "edition_or_transcription": "Constructed fixture", "hand": None,
                      "original_representation": "synthetic wording", "english_rendering": None,
                      "rendering_author": None, "attestation": "present", "citation_ids": ["C1"],
                      "encoding_notes": ["No historical witness represented."]}],
        "dates": {k: [] for k in ("narrated_setting", "proposed_composition", "physical_witness", "modern_edition")},
        "claims": [{"id": "Q1", "text": "The synthetic fixture has wording.", "kind": "observation",
                    "supporting_citation_ids": ["C1"], "contrary_citation_ids": [], "alternative_claim_ids": [],
                    "assessment": "supported", "attributed_position": None, "limitations": ["Synthetic test only."]}],
        "coverage_limits": ["Not evidence."],
        "rights_by_component": [{"source_id": "synthetic-source", "component": "source_text",
                                 "observed_license": None, "rights_url": None, "rights_notice_sha256": None,
                                 "attribution": "Constructed fixture", "change_notice": "Test material only.",
                                 **{k: decision() for k in ("research_access", "app_display", "redistribution", "training", "adapter_release")}}],
        "review": {"author_id": "synthetic-author", "reviewer_id": None, "reviewer_role": None,
                   "qualifications": None, "perspective_and_conflicts": ["Synthetic test fixture."],
                   "status": "draft", "reviewed_on": None, "record_content_sha256": None,
                   "adjudication": None, "unresolved_issues": ["No review performed."]},
    }


class EvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.schema = strict_load(ROOT / PLAN)["record_schema"]

    def check(self, record):
        return validate_record(record, self.schema)

    def test_valid_draft_still_has_no_release_approval(self):
        result = self.check(fixture())
        self.assertEqual(result["errors"], [])
        self.assertFalse(result["release_ready"])
        self.assertTrue(result["research_gaps"])

    def test_dangling_citations_alternatives_and_duplicate_ids(self):
        record = fixture()
        record["claims"][0]["supporting_citation_ids"] = ["missing"]
        record["claims"][0]["alternative_claim_ids"] = ["missing-claim"]
        record["citations"].append(copy.deepcopy(record["citations"][0]))
        errors = self.check(record)["errors"]
        self.assertIn("claim_support:unresolved_reference", errors)
        self.assertIn("claim_alternative:unresolved_reference", errors)
        self.assertIn("citations:duplicate_id", errors)

    def test_missing_rights_cannot_be_hidden_by_valid_schema(self):
        record = fixture(); record["rights_by_component"] = []
        self.assertIn("rights:source_without_component_decision", self.check(record)["errors"])

    def test_edition_comparison_is_not_manuscript_attestation(self):
        record = fixture(); record["readings"][0]["entity_type"] = "manuscript"
        self.assertIn("reading:manuscript_attestation_from_editions_only", self.check(record)["errors"])
        notice = copy.deepcopy(record["citations"][0]); notice.update(id="C2", kind="rights_notice")
        record["citations"].append(notice); record["readings"][0]["citation_ids"].append("C2")
        self.assertIn("reading:manuscript_attestation_from_editions_only", self.check(record)["errors"])

    def test_unavailable_text_cannot_acquire_wording(self):
        for status in ("absent", "unpreserved", "unchecked"):
            with self.subTest(status=status):
                record = fixture(); record["readings"][0]["attestation"] = status
                self.assertIn("reading:unavailable_text_has_supplied_wording", self.check(record)["errors"])

    def test_translations_need_attribution(self):
        record = fixture(); record["readings"][0]["english_rendering"] = "Synthetic rendering"
        self.assertIn("reading:unattributed_translation", self.check(record)["errors"])

    def test_bce_range_direction_and_no_year_zero(self):
        record = fixture()
        date = {"earliest": {"era": "BCE", "year": 500}, "latest": {"era": "BCE", "year": 400},
                "display_label": "Synthetic 500–400 BCE", "method": "Synthetic check", "citation_ids": ["C1"],
                "uncertainty": "Not an actual date claim."}
        record["dates"]["physical_witness"] = [date]
        self.assertEqual(self.check(record)["errors"], [])
        date["earliest"], date["latest"] = date["latest"], date["earliest"]
        self.assertIn("date:reversed_range", self.check(record)["errors"])
        date["earliest"]["year"] = 0
        self.assertTrue(any(x.startswith("schema:") for x in self.check(record)["errors"]))

    def test_unsupported_claims_and_dates_fail(self):
        record = fixture(); record["claims"][0]["supporting_citation_ids"] = []
        self.assertIn("claim:supported_without_citation", self.check(record)["errors"])
        record = fixture(); record["claims"][0]["kind"] = "historical_inference"
        record["claims"][0]["limitations"] = []
        self.assertIn("claim:inference_without_limits", self.check(record)["errors"])

    def test_draft_pipeline_rejects_promotions_and_self_review(self):
        record = fixture(); record["status"] = "approved_for_app"
        record["review"].update(status="approved", reviewer_id="synthetic-author")
        record["rights_by_component"][0]["training"] = decision("approved")
        errors = self.check(record)["errors"]
        self.assertIn("record:this_pipeline_accepts_drafts_only", errors)
        self.assertIn("review:this_pipeline_does_not_certify_approval", errors)
        self.assertIn("review:author_cannot_review_own_record", errors)
        self.assertIn("rights:draft_cannot_approve_training", errors)

    def test_strict_json_rejects_duplicates_and_nonfinite_values(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "fixture.json"
            for invalid in ('{"a":1,"a":2}', '{"a":NaN}'):
                path.write_text(invalid)
                with self.assertRaises(ValueError): strict_load(path)

    def test_pack_is_private_and_duplicate_records_fail(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); (root / "manifests").mkdir()
            (root / PLAN).write_text(json.dumps({"record_schema": self.schema}))
            drafts = root / "data/evidence/drafts/v1"; drafts.mkdir(parents=True)
            (drafts / "first.json").write_text(json.dumps(fixture()))
            result = audit_directory(root)
            self.assertEqual(result["status"], "drafts_valid")
            self.assertEqual(result["app_approved"], 0)
            (drafts / "duplicate.json").write_text(json.dumps(fixture()))
            self.assertEqual(audit_directory(root)["status"], "drafts_invalid")
            with self.assertRaises(ValueError): audit_directory(root, root / "manifests")

    def test_symlink_roots_and_ancestors_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            parent = Path(directory); root = parent / "project"; root.mkdir()
            outside = parent / "outside"; outside.mkdir(); (outside / "canary.txt").write_text("synthetic fixture")
            (root / "data").mkdir(); (root / "data/raw").symlink_to(outside, target_is_directory=True)
            with self.assertRaises(ValueError): snapshot_index(root)
            (root / "data/evidence").symlink_to(outside, target_is_directory=True)
            with self.assertRaises(ValueError): audit_directory(root)
            (root / "runs").symlink_to(outside, target_is_directory=True)
            with self.assertRaises(ValueError): confined_path(root, root / "runs/receipt.json", ("runs",))
            with self.assertRaises(ValueError): confined_path(root, root / "runs/../public.json", ("runs",))


if __name__ == "__main__":
    unittest.main()
