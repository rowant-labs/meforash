"""Constructed tests for the strict evidence eligibility registry/projection."""
import copy
import json
from pathlib import Path
import tempfile
import unittest

from bibleprep.evidence import PLAN, sha256, strict_load
from bibleprep.evidence_eligibility import (
    audit_registry,
    build_projection,
    canonical_sha256,
    component_content_sha256,
    render_markdown,
    seed_pending_registry,
    write_pending_registry,
    write_projection,
)


def pending_right():
    return {
        "decision": "pending", "basis": "Constructed fixture; no use approval.",
        "reviewer": None, "reviewed_on": None,
    }


def record_fixture(c1_hash, c2_hash):
    return {
        "schema_version": 1,
        "id": "SYNTHETIC01",
        "kind": "textual_dossier",
        "status": "draft",
        "biblical_anchor_languages": ["greek"],
        "source_languages": ["english"],
        "chapter_keys": ["Mark.1"],
        "source_reference_systems": ["constructed"],
        "mapped_references": ["Constructed reference."],
        "mapping_citation_ids": ["C1"],
        "summary": "A constructed record with no real historical assertion.",
        "citations": [
            {
                "id": "C1", "source_id": "source-one", "kind": "edition",
                "author_or_institution": "Constructed", "title": "Supporting fixture",
                "locator": "line 1", "url": "https://example.org/one",
                "publication_date": None, "accessed_on": "2026-09-08",
                "pinned_version": "fixture-v1", "content_sha256": c1_hash,
            },
            {
                "id": "C2", "source_id": "source-two", "kind": "scholarship",
                "author_or_institution": "Constructed", "title": "Contrary fixture",
                "locator": "page 2", "url": "https://example.org/two",
                "publication_date": None, "accessed_on": "2026-09-08",
                "pinned_version": "fixture-v1", "content_sha256": c2_hash,
            },
        ],
        "readings": [
            {
                "id": "R1", "entity_type": "modern_edition", "stable_entity_id": "fixture:R1",
                "edition_or_transcription": "Constructed", "hand": None,
                "original_representation": "alpha", "english_rendering": "alpha",
                "rendering_author": "Fixture author", "attestation": "present",
                "citation_ids": ["C1"], "encoding_notes": ["Constructed only."],
            }
        ],
        "dates": {key: [] for key in (
            "narrated_setting", "proposed_composition", "physical_witness", "modern_edition"
        )},
        "claims": [
            {
                "id": "Q1", "text": "A constructed disputed claim.",
                "kind": "historical_inference", "supporting_citation_ids": ["C1"],
                "contrary_citation_ids": ["C2"], "alternative_claim_ids": ["Q2"],
                "assessment": "disputed", "attributed_position": "Constructed position",
                "limitations": ["This is synthetic evidence."],
            },
            {
                "id": "Q2", "text": "A constructed alternative.", "kind": "observation",
                "supporting_citation_ids": ["C2"], "contrary_citation_ids": [],
                "alternative_claim_ids": ["Q1"], "assessment": "uncertain",
                "attributed_position": None, "limitations": ["Alternative remains uncertain."],
            },
        ],
        "coverage_limits": ["Constructed fixture only."],
        "rights_by_component": [
            {
                "source_id": source_id, "component": "source_text", "observed_license": None,
                "rights_url": None, "rights_notice_sha256": None,
                "attribution": "Constructed", "change_notice": "Fixture only.",
                **{use: pending_right() for use in (
                    "research_access", "app_display", "redistribution", "training", "adapter_release"
                )},
            }
            for source_id in ("source-one", "source-two")
        ],
        "review": {
            "author_id": "fixture-author", "reviewer_id": None, "reviewer_role": None,
            "qualifications": None, "perspective_and_conflicts": ["Constructed fixture."],
            "status": "draft", "reviewed_on": None, "record_content_sha256": None,
            "adjudication": None, "unresolved_issues": ["No real review performed."],
        },
    }


class EvidenceEligibilityTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name).resolve()
        (self.root / "manifests").mkdir()
        (self.root / "data/evidence/drafts/v1").mkdir(parents=True)
        (self.root / "data/evidence/reviews").mkdir(parents=True)
        (self.root / "data/raw").mkdir(parents=True)
        project_root = Path(__file__).resolve().parents[1]
        plan = strict_load(project_root / PLAN)
        (self.root / PLAN).write_text(json.dumps({"record_schema": plan["record_schema"]}), encoding="utf-8")
        self.source_one = self.root / "data/raw/source-one.txt"
        self.source_two = self.root / "data/raw/source-two.txt"
        self.source_one.write_text("constructed source one\n", encoding="utf-8")
        self.source_two.write_text("constructed source two\n", encoding="utf-8")
        self.record = record_fixture(sha256(self.source_one), sha256(self.source_two))
        self.record_path = self.root / "data/evidence/drafts/v1/SYNTHETIC01.json"
        self.write_record()
        self.review_path = self.root / "data/evidence/reviews/synthetic-review.txt"
        self.review_path.write_text("Constructed reviewer evidence; no real certification.\n", encoding="utf-8")

    def tearDown(self):
        self.temporary.cleanup()

    def write_record(self):
        self.record_path.write_text(json.dumps(self.record, indent=2) + "\n", encoding="utf-8")

    @property
    def directory(self):
        return self.root / "data/evidence/drafts/v1"

    def seed(self):
        return seed_pending_registry(self.root, self.directory, "synthetic-eligibility-v1")

    def approve(self, registry, component_id="claim-Q1", use="app_display", expert=True):
        registry["status"] = "reviewed"
        component = next(
            item for item in registry["records"][0]["components"] if item["component_id"] == component_id
        )
        evidence = [{
            "evidence_id": "review-1", "path": "data/evidence/reviews/synthetic-review.txt",
            "content_sha256": sha256(self.review_path),
        }]
        component["scholarly_review"] = {
            "decision": "approved", "reviewer_kind": "human",
            "reviewer_role": "Qualified synthetic textual reviewer",
            "reviewed_on": "2026-09-08", "rationale": "Constructed approval for a positive test.",
            "limitations": ["No real evidence or reviewer."],
            "supporting_review_evidence": copy.deepcopy(evidence),
            "expert_certification": expert,
        }
        component["uses"][use] = {
            "decision": "approved", "reviewer_kind": "human",
            "reviewer_role": "Synthetic rights reviewer",
            "reviewed_on": "2026-09-08", "rationale": "Constructed use approval.",
            "limitations": ["Test use only."],
            "supporting_review_evidence": copy.deepcopy(evidence),
        }
        return component

    def test_seed_is_exact_all_pending_and_empty_projection_is_valid(self):
        registry = self.seed()
        self.assertEqual(registry["status"], "pending")
        self.assertEqual(len(registry["records"]), 1)
        claim = next(c for c in registry["records"][0]["components"] if c["component_id"] == "claim-Q1")
        self.assertEqual(claim["field_refs"], ["/claims/0", "/claims/1"])
        self.assertEqual(claim["content_sha256"], component_content_sha256(self.record, claim["field_refs"]))
        self.assertEqual({d["citation_id"] for d in claim["citation_dependencies"]}, {"C1", "C2"})
        self.assertTrue(all(d["snapshot_path"] for d in claim["source_dependencies"]))
        summary = audit_registry(registry, self.root, self.directory)
        self.assertEqual(summary["eligible_components_by_use"]["app_display"], 0)
        projection = build_projection(registry, "app_display", self.root, self.directory)
        self.assertEqual(projection["record_count"], 0)
        self.assertEqual(projection["component_count"], 0)

    def test_approved_synthetic_component_projects_full_closure_and_qualifications(self):
        registry = self.seed()
        self.approve(registry)
        first = build_projection(registry, "app_display", self.root, self.directory)
        second = build_projection(registry, "app_display", self.root, self.directory)
        self.assertEqual(first, second)
        self.assertEqual(first["component_count"], 1)
        self.assertEqual(first["registry_sha256"], canonical_sha256(registry))
        component = first["records"][0]["components"][0]
        self.assertEqual([item["value"]["id"] for item in component["content"]], ["Q1", "Q2"])
        self.assertEqual({item["id"] for item in component["citations"]}, {"C1", "C2"})
        self.assertEqual(component["content"][0]["value"]["assessment"], "disputed")
        self.assertEqual(component["content"][0]["value"]["limitations"], ["This is synthetic evidence."])
        self.assertEqual(component["scholarly_review"]["expert_certification"], True)
        self.assertEqual(first["records"][0]["coverage_limits"], ["Constructed fixture only."])
        self.assertEqual(first["records"][0]["record_unresolved_issues"], ["No real review performed."])
        self.assertEqual(build_projection(registry, "training", self.root, self.directory)["component_count"], 0)

    def test_registry_must_be_reviewed_and_projection_binds_full_registry(self):
        registry = self.seed()
        component = self.approve(registry)
        registry["status"] = "pending"
        self.assertEqual(build_projection(registry, "app_display", self.root, self.directory)["component_count"], 0)
        registry["status"] = "superseded"
        self.assertEqual(build_projection(registry, "app_display", self.root, self.directory)["component_count"], 0)
        registry["status"] = "reviewed"
        first_hash = build_projection(registry, "app_display", self.root, self.directory)["registry_sha256"]
        component["uses"]["training"]["rationale"] = "A changed pending rationale."
        second_hash = build_projection(registry, "app_display", self.root, self.directory)["registry_sha256"]
        self.assertNotEqual(first_hash, second_hash)

    def test_selected_claim_must_include_alternative_and_exact_citation_source_closure(self):
        registry = self.seed()
        component = next(c for c in registry["records"][0]["components"] if c["component_id"] == "claim-Q1")
        component["field_refs"] = ["/claims/0"]
        component["content_sha256"] = component_content_sha256(self.record, component["field_refs"])
        with self.assertRaisesRegex(ValueError, "omits alternative"):
            audit_registry(registry, self.root, self.directory)
        registry = self.seed()
        component = next(c for c in registry["records"][0]["components"] if c["component_id"] == "claim-Q1")
        component["citation_dependencies"].pop()
        with self.assertRaisesRegex(ValueError, "Citation dependency closure differs"):
            audit_registry(registry, self.root, self.directory)
        registry = self.seed()
        component = next(c for c in registry["records"][0]["components"] if c["component_id"] == "claim-Q1")
        component["source_dependencies"].pop()
        with self.assertRaisesRegex(ValueError, "Source dependency closure differs"):
            audit_registry(registry, self.root, self.directory)

    def test_stale_record_component_citation_source_and_review_hashes_fail_closed(self):
        cases = []
        registry = self.seed(); registry["records"][0]["record_sha256"] = "0" * 64
        cases.append((registry, "Record hash mismatch"))
        registry = self.seed(); registry["records"][0]["components"][0]["content_sha256"] = "0" * 64
        cases.append((registry, "Component hash mismatch"))
        registry = self.seed(); registry["records"][0]["components"][0]["citation_dependencies"][0]["citation_sha256"] = "0" * 64
        cases.append((registry, "Citation hash mismatch"))
        registry = self.seed(); registry["records"][0]["components"][0]["source_dependencies"][0]["content_sha256"] = "0" * 64
        cases.append((registry, "Source hash mismatch"))
        registry = self.seed(); self.approve(registry)
        component = next(c for c in registry["records"][0]["components"] if c["component_id"] == "claim-Q1")
        component["scholarly_review"]["supporting_review_evidence"][0]["content_sha256"] = "0" * 64
        cases.append((registry, "review evidence hash mismatch"))
        for registry, message in cases:
            with self.subTest(message=message), self.assertRaisesRegex(ValueError, message):
                audit_registry(registry, self.root, self.directory)

    def test_missing_local_snapshot_stays_valid_pending_but_never_eligible(self):
        registry = self.seed()
        component = next(c for c in registry["records"][0]["components"] if c["component_id"] == "claim-Q1")
        component["source_dependencies"][0]["snapshot_path"] = None
        self.approve(registry)
        projection = build_projection(registry, "app_display", self.root, self.directory)
        self.assertEqual(projection["component_count"], 0)
        exclusion = next(item for item in projection["excluded_components"] if item["component_id"] == "claim-Q1")
        self.assertIn("local source snapshot is unresolved", exclusion["reasons"][0])

    def test_nonapproved_decisions_never_become_eligible(self):
        for decision in ("pending", "rejected", "stale", "unknown"):
            with self.subTest(decision=decision):
                registry = self.seed()
                component = self.approve(registry)
                component["scholarly_review"]["decision"] = decision
                component["scholarly_review"]["expert_certification"] = False
                if decision in {"pending", "unknown"}:
                    component["scholarly_review"]["reviewer_role"] = None
                    component["scholarly_review"]["reviewer_kind"] = None
                    component["scholarly_review"]["reviewed_on"] = None
                    component["scholarly_review"]["supporting_review_evidence"] = []
                    component["scholarly_review"]["expert_certification"] = False
                self.assertEqual(
                    build_projection(registry, "app_display", self.root, self.directory)["component_count"], 0
                )

    def test_approved_decisions_require_review_fields_and_ai_cannot_claim_expertise(self):
        registry = self.seed()
        component = self.approve(registry)
        component["scholarly_review"]["supporting_review_evidence"] = []
        with self.assertRaisesRegex(ValueError, "lacks complete review evidence"):
            audit_registry(registry, self.root, self.directory)
        registry = self.seed()
        component = self.approve(registry)
        component["scholarly_review"]["reviewer_role"] = "AI development assistant"
        with self.assertRaisesRegex(ValueError, "cannot claim expert certification"):
            audit_registry(registry, self.root, self.directory)
        registry = self.seed()
        component = next(c for c in registry["records"][0]["components"] if c["component_id"] == "claim-Q1")
        component["scholarly_review"]["expert_certification"] = True
        component["scholarly_review"]["reviewer_kind"] = "human"
        component["scholarly_review"]["reviewer_role"] = "Synthetic textual reviewer"
        with self.assertRaisesRegex(ValueError, "requires an approved scholarly decision"):
            audit_registry(registry, self.root, self.directory)
        registry = self.seed()
        component = self.approve(registry)
        component["scholarly_review"]["reviewer_kind"] = "ai"
        with self.assertRaisesRegex(ValueError, "requires reviewer_kind human"):
            audit_registry(registry, self.root, self.directory)

    def test_duplicate_ids_keys_and_unsupported_fields_are_rejected(self):
        registry = self.seed()
        registry["records"].append(copy.deepcopy(registry["records"][0]))
        with self.assertRaisesRegex(ValueError, "Duplicate registry record ID"):
            audit_registry(registry, self.root, self.directory)
        duplicate_json = self.root / "data/evidence/duplicate.json"
        duplicate_json.write_text('{"schema_version":1,"schema_version":1}\n', encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "Duplicate JSON key"):
            strict_load(duplicate_json)
        registry = self.seed()
        registry["records"][0]["components"][0]["unexpected"] = True
        with self.assertRaisesRegex(ValueError, r"extra=\['unexpected'\]"):
            audit_registry(registry, self.root, self.directory)

    def test_path_escape_symlink_and_overwrite_are_rejected(self):
        registry = self.seed()
        self.approve(registry)
        projection = build_projection(registry, "app_display", self.root, self.directory)
        with self.assertRaises(ValueError):
            write_projection(projection, self.root.parent / "outside", self.root)
        receipt = write_projection(projection, self.root / "runs/projection", self.root)
        self.assertEqual(receipt["output_directory"], "runs/projection")
        self.assertEqual((self.root / "runs").stat().st_mode & 0o777, 0o700)
        self.assertEqual((self.root / "runs/projection").stat().st_mode & 0o777, 0o700)
        self.assertEqual((self.root / "runs/projection/projection.json").stat().st_mode & 0o777, 0o600)
        self.assertEqual((self.root / "runs/projection/projection.md").stat().st_mode & 0o777, 0o600)
        with self.assertRaises(FileExistsError):
            write_projection(projection, self.root / "runs/projection", self.root)
        outside = self.root.parent / (self.root.name + "-outside")
        outside.mkdir()
        self.addCleanup(lambda: outside.rmdir())
        (self.root / "runs-link").symlink_to(outside, target_is_directory=True)
        with self.assertRaises(ValueError):
            write_projection(projection, self.root / "runs-link/projection", self.root)

    def test_pending_registry_writer_is_exclusive_and_private(self):
        path = self.root / "data/evidence/eligibility/registry.json"
        receipt = write_pending_registry(self.seed(), path, self.root)
        self.assertEqual(receipt["path"], "data/evidence/eligibility/registry.json")
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        with self.assertRaises(FileExistsError):
            write_pending_registry(self.seed(), path, self.root)

    def test_canonical_hash_is_key_order_independent(self):
        self.assertEqual(canonical_sha256({"a": 1, "b": 2}), canonical_sha256({"b": 2, "a": 1}))

    def test_markdown_preserves_qualifications_and_escapes_untrusted_content(self):
        self.record["claims"][0]["text"] = "<script>alert(1)</script> [bad](https://evil.example)"
        self.record["claims"][0]["attributed_position"] = "# invented heading"
        self.record["claims"][0]["limitations"] = ["* uncertain"]
        self.write_record()
        registry = self.seed()
        self.approve(registry)
        self.approve(registry, component_id="reading-R1")
        rendered = render_markdown(build_projection(registry, "app_display", self.root, self.directory))
        self.assertNotIn("<script>", rendered)
        self.assertNotIn("[bad](https://evil.example)", rendered)
        self.assertIn("&lt;script&gt;", rendered)
        self.assertIn("assessment: `disputed`", rendered)
        self.assertIn("Parent-record unresolved issues", rendered)
        self.assertIn("Scholarly review details", rendered)
        self.assertIn("Registry SHA-256", rendered)
        self.assertIn("Original representation", rendered)


if __name__ == "__main__":
    unittest.main()
