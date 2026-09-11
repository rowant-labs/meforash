"""Constructed tests for the private, model-free evidence review export."""
import copy
import json
from pathlib import Path
import tempfile
import unittest

from bibleprep.evidence import PLAN, ROOT, sha256, strict_load
from bibleprep.evidence_review import (
    _anchor,
    build_review_export,
    derive_gap_queue,
    render_html,
    validate_reference_mapping,
    write_export,
)


def decision(value="pending"):
    return {"decision": value, "basis": "Constructed test; no release decision.",
            "reviewer": None, "reviewed_on": None}


def record_fixture():
    return {
        "schema_version": 1, "id": "SYNTHETIC01", "kind": "textual_dossier", "status": "draft",
        "biblical_anchor_languages": ["greek"], "source_languages": ["english"],
        "chapter_keys": ["Mark.1"], "source_reference_systems": ["constructed"],
        "mapped_references": ["No witness equivalence asserted."], "mapping_citation_ids": ["C1"],
        "summary": "Escaping check <script>alert('unsafe')</script> & review.",
        "citations": [{"id": "C1", "source_id": "sblgnt", "kind": "edition",
                       "author_or_institution": "Constructed fixture", "title": "Synthetic <edition>",
                       "locator": "line 1 & line 2", "url": "https://example.org/source?a=1&b=2",
                       "publication_date": None, "accessed_on": "2026-09-07",
                       "pinned_version": None, "content_sha256": None}],
        "readings": [{"id": "R1", "entity_type": "manuscript", "stable_entity_id": "synthetic:R1",
                      "edition_or_transcription": "Constructed", "hand": None,
                      "original_representation": None, "english_rendering": None, "rendering_author": None,
                      "attestation": "unchecked", "citation_ids": ["C1"],
                      "encoding_notes": ["No historical witness represented."]}],
        "dates": {key: [] for key in
                  ("narrated_setting", "proposed_composition", "physical_witness", "modern_edition")},
        "claims": [{"id": "Q1", "text": "A constructed uncertain claim.", "kind": "observation",
                    "supporting_citation_ids": ["C1"], "contrary_citation_ids": [],
                    "alternative_claim_ids": [], "assessment": "uncertain", "attributed_position": None,
                    "limitations": ["Constructed test only."]}],
        "coverage_limits": ["Not evidence."],
        "rights_by_component": [{"source_id": "sblgnt", "component": "source_text",
                                 "observed_license": None, "rights_url": None,
                                 "rights_notice_sha256": None, "attribution": "Constructed fixture",
                                 "change_notice": "Test material only.",
                                 **{use: decision() for use in
                                    ("research_access", "app_display", "redistribution", "training", "adapter_release")}}],
        "review": {"author_id": "synthetic-author", "reviewer_id": None, "reviewer_role": None,
                   "qualifications": None, "perspective_and_conflicts": ["Constructed fixture."],
                   "status": "draft", "reviewed_on": None, "record_content_sha256": None,
                   "adjudication": None, "unresolved_issues": ["Specialist review is pending."]},
    }


def mapping_fixture(record_hash):
    return {
        "schema_version": 1, "id": "evidence-reference-map-v1",
        "status": "reviewed_engineering_coordinate_mapping", "scope": "Constructed test.",
        "review": {"review_type": "ai_engineering_coordinate_check",
                   "reviewer_role": "AI development assistant", "reviewed_on": "2026-09-07",
                   "specialist_certification": False},
        "entries": [{"record_id": "SYNTHETIC01", "record_sha256": record_hash,
                     "original_chapter_key": "Mark.1", "normalized_chapter_key": "bible:Mark.1",
                     "source_id": "sblgnt", "edition": "SBLGNT",
                     "edition_coordinate": "sblgnt:Mark.1", "mapping_citation_ids": ["C1"],
                     "note": "Explicit constructed coordinate mapping."}],
        "limitations": ["Constructed test; no specialist certification."],
    }


class EvidenceReviewTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        (self.root / "manifests").mkdir()
        (self.root / "data/evidence/drafts/v1").mkdir(parents=True)
        (self.root / "data/raw").mkdir(parents=True)
        schema = strict_load(ROOT / PLAN)["record_schema"]
        (self.root / PLAN).write_text(json.dumps({"record_schema": schema}), encoding="utf-8")
        self.record = record_fixture()
        self.write_pack()

    def tearDown(self):
        self.temporary.cleanup()

    def write_pack(self):
        draft = self.root / "data/evidence/drafts/v1/SYNTHETIC01.json"
        markdown = draft.with_suffix(".md")
        draft.write_text(json.dumps(self.record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        markdown.write_text("# Constructed review companion\n", encoding="utf-8")
        inventory = {"schema_version": 1, "id": "evidence-first-pack-v1", "record_count": 1,
                     "records": [{"id": "SYNTHETIC01", "draft_json_sha256": sha256(draft),
                                  "readable_markdown_sha256": sha256(markdown)}]}
        (self.root / "manifests/evidence-first-pack-v1.json").write_text(
            json.dumps(inventory, indent=2) + "\n", encoding="utf-8")
        mapping = mapping_fixture(sha256(draft))
        (self.root / "manifests/evidence-reference-map-v1.json").write_text(
            json.dumps(mapping, indent=2) + "\n", encoding="utf-8")

    def build(self):
        return build_review_export(self.root)

    def test_complete_export_is_deterministic_traceable_and_html_escaped(self):
        first = self.build()
        second = self.build()
        self.assertEqual(first, second)
        self.assertEqual(first["record_count"], 1)
        self.assertEqual([item["id"] for item in first["records"]], ["SYNTHETIC01"])
        self.assertEqual(first["records"][0]["reference_mapping"][0]["edition_coordinate"],
                         "sblgnt:Mark.1")
        categories = {item["reason_category"] for item in first["gap_queue"]}
        self.assertTrue({"missing_source_bytes", "missing_immutable_version", "unchecked_attestation", "scholarly_judgment",
                         "missing_date_assertion", "use_restriction", "record_review"} <= categories)
        rendered = render_html(first)
        self.assertNotIn("<script>alert", rendered)
        self.assertIn("&lt;script&gt;alert", rendered)
        self.assertIn(f'href="#{_anchor("SYNTHETIC01", "citation", "C1")}"', rendered)
        self.assertEqual(first["app_approved"], 0)
        self.assertEqual(first["training_approved"], 0)

    def test_cross_reference_errors_stop_export(self):
        self.record["claims"][0]["supporting_citation_ids"] = ["missing"]
        self.write_pack()
        with self.assertRaisesRegex(ValueError, "Draft validation failed"):
            self.build()

    def test_null_and_unavailable_source_hashes_remain_distinct_gaps(self):
        audit = {"SYNTHETIC01": {"claimed_hashes_without_local_bytes": []}}
        gaps = derive_gap_queue([self.record], audit)
        source = [item for item in gaps if item["reason_category"] == "missing_source_bytes"]
        self.assertEqual(len(source), 1)
        self.assertIn("no content_sha256", source[0]["reason"])
        record = copy.deepcopy(self.record)
        record["citations"][0]["content_sha256"] = "a" * 64
        audit["SYNTHETIC01"]["claimed_hashes_without_local_bytes"] = ["C1"]
        gaps = derive_gap_queue([record], audit)
        source = [item for item in gaps if item["reason_category"] == "missing_source_bytes"]
        self.assertEqual(len(source), 1)
        self.assertIn("matching local source bytes were not found", source[0]["reason"])

    def test_unknown_and_conflicting_rights_never_promote(self):
        export = self.build()
        rights_gap = next(item for item in export["gap_queue"] if item["reason_category"] == "use_restriction")
        self.assertIn("observed license is unknown", rights_gap["reason"])
        self.assertEqual(rights_gap["uses"]["app_display"]["decision"], "pending")
        self.record["rights_by_component"].append(copy.deepcopy(self.record["rights_by_component"][0]))
        self.record["rights_by_component"][1]["observed_license"] = "Conflicting constructed notice"
        self.write_pack()
        with self.assertRaisesRegex(ValueError, "Draft validation failed"):
            self.build()

    def test_mapping_rejects_ambiguity_missing_coverage_and_hash_drift(self):
        draft_hash = sha256(self.root / "data/evidence/drafts/v1/SYNTHETIC01.json")
        mapping = mapping_fixture(draft_hash)
        records = [self.record]
        hashes = {"SYNTHETIC01": draft_hash}
        mapping["entries"].append(copy.deepcopy(mapping["entries"][0]))
        with self.assertRaisesRegex(ValueError, "Ambiguous reference mapping"):
            validate_reference_mapping(mapping, records, hashes)
        mapping = mapping_fixture(draft_hash); mapping["entries"] = []
        with self.assertRaisesRegex(ValueError, "coverage differs"):
            validate_reference_mapping(mapping, records, hashes)
        mapping = mapping_fixture("0" * 64)
        with self.assertRaisesRegex(ValueError, "hash mismatch"):
            validate_reference_mapping(mapping, records, hashes)
        for field, value in (("normalized_chapter_key", "bible:Luke.1"),
                             ("edition_coordinate", "sblgnt:Luke.1"),
                             ("edition", "OSHB/WLC")):
            with self.subTest(field=field):
                mapping = mapping_fixture(draft_hash)
                mapping["entries"][0][field] = value
                with self.assertRaisesRegex(ValueError, "Inconsistent v1 source/edition"):
                    validate_reference_mapping(mapping, records, hashes)

    def test_html_anchors_preserve_case_and_punctuation_identity(self):
        anchors = {_anchor("R", "claim", value) for value in ("A_B", "A-B", "a-b", "A.B")}
        self.assertEqual(len(anchors), 4)

    def test_custom_mapping_path_is_reported_with_its_actual_hash(self):
        default = self.root / "manifests/evidence-reference-map-v1.json"
        custom = self.root / "manifests/custom-reference-map.json"
        custom.write_bytes(default.read_bytes())
        export = build_review_export(self.root, mapping_path=custom)
        self.assertEqual(export["reference_mapping"]["path"], "manifests/custom-reference-map.json")
        self.assertEqual(export["reference_mapping"]["sha256"], sha256(custom))

    def test_confirmed_absence_is_not_reported_as_unchecked(self):
        record = copy.deepcopy(self.record)
        record["readings"][0]["attestation"] = "absent"
        audit = {"SYNTHETIC01": {"claimed_hashes_without_local_bytes": []}}
        categories = {item["reason_category"] for item in derive_gap_queue([record], audit)}
        self.assertIn("confirmed_absence", categories)
        self.assertNotIn("unchecked_attestation", categories)

    def test_output_is_private_confined_exclusive_and_read_only_by_default(self):
        export = self.build()
        receipt = write_export(export, self.root / "runs/review-v1", self.root)
        self.assertEqual(receipt["output_directory"], "runs/review-v1")
        self.assertTrue((self.root / "runs/review-v1/review.json").is_file())
        self.assertTrue((self.root / "runs/review-v1/index.html").is_file())
        with self.assertRaises(FileExistsError):
            write_export(export, self.root / "runs/review-v1", self.root)
        with self.assertRaises(ValueError):
            write_export(export, self.root.parent / "outside-review", self.root)

    def test_symlink_output_and_mapping_paths_are_rejected(self):
        outside = self.root.parent / (self.root.name + "-outside")
        outside.mkdir()
        self.addCleanup(lambda: outside.rmdir())
        (self.root / "runs").symlink_to(outside, target_is_directory=True)
        with self.assertRaises(ValueError):
            write_export(self.build(), self.root / "runs/review-v1", self.root)
        real_mapping = self.root / "manifests/evidence-reference-map-v1.json"
        saved = real_mapping.read_text(encoding="utf-8")
        real_mapping.unlink()
        target = outside / "mapping.json"; target.write_text(saved, encoding="utf-8")
        self.addCleanup(lambda: target.unlink())
        real_mapping.symlink_to(target)
        with self.assertRaises(ValueError):
            self.build()


if __name__ == "__main__":
    unittest.main()
