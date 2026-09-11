"""Constructed tests for notice-complete evidence delivery."""
import copy
import json
import os
from pathlib import Path
import tempfile
import unittest

from bibleprep.evidence import PLAN, sha256, strict_load
from bibleprep.evidence_delivery import (
    build_candidate_bundle,
    public_delivery_payload,
    render_display,
    render_model_input,
    rights_fact_sha256,
    verify_candidate_bundle,
    verify_for_use,
    write_private_json,
)
from bibleprep.evidence_eligibility import seed_pending_registry


USES = ("research_access", "app_display", "redistribution", "training", "adapter_release")


def pending_right():
    return {
        "decision": "pending", "basis": "Constructed fixture; no use approval.",
        "reviewer": None, "reviewed_on": None,
    }


def record_fixture(source_hash, rights_hash):
    rights = []
    for component, license_name, change in (
        ("source_text", "Fixture-PD", "Selected text only; characters unchanged."),
        ("annotation", "Fixture-CC", "English notes are newly authored."),
    ):
        rights.append({
            "source_id": "source-one", "component": component,
            "observed_license": license_name,
            "rights_url": "https://example.org/license",
            "rights_notice_sha256": rights_hash,
            "attribution": "Constructed source author.", "change_notice": change,
            **{use: pending_right() for use in USES},
        })
    return {
        "schema_version": 1, "id": "SYNTHETIC01", "kind": "textual_dossier",
        "status": "draft", "biblical_anchor_languages": ["greek"],
        "source_languages": ["english"], "chapter_keys": ["Mark.1"],
        "source_reference_systems": ["constructed"],
        "mapped_references": ["Constructed reference."], "mapping_citation_ids": ["C1"],
        "summary": "A constructed record with no real assertion.",
        "citations": [{
            "id": "C1", "source_id": "source-one", "kind": "edition",
            "author_or_institution": "Constructed", "title": "Supporting fixture",
            "locator": "line 1", "url": "https://example.org/one",
            "publication_date": None, "accessed_on": "2026-09-08",
            "pinned_version": "fixture-v1", "content_sha256": source_hash,
        }],
        "readings": [{
            "id": "R1", "entity_type": "modern_edition", "stable_entity_id": "fixture:R1",
            "edition_or_transcription": "Constructed", "hand": None,
            "original_representation": "Ἀρχή ⸀λόγου. ", "english_rendering": "A beginning.",
            "rendering_author": "Fixture author", "attestation": "uncertain",
            "citation_ids": ["C1"], "encoding_notes": ["The marker is editorial."],
        }],
        "dates": {key: [] for key in (
            "narrated_setting", "proposed_composition", "physical_witness", "modern_edition"
        )},
        "claims": [
            {
                "id": "Q1", "text": "One constructed possibility.",
                "kind": "historical_inference", "supporting_citation_ids": ["C1"],
                "contrary_citation_ids": [], "alternative_claim_ids": ["Q2"],
                "assessment": "disputed", "attributed_position": "Constructed only",
                "limitations": ["Uncertainty is retained."],
            },
            {
                "id": "Q2", "text": "A constructed alternative.", "kind": "observation",
                "supporting_citation_ids": ["C1"], "contrary_citation_ids": [],
                "alternative_claim_ids": ["Q1"], "assessment": "uncertain",
                "attributed_position": None, "limitations": ["Alternative remains open."],
            },
        ],
        "coverage_limits": ["Constructed fixture only."], "rights_by_component": rights,
        "review": {
            "author_id": "fixture-author", "reviewer_id": None, "reviewer_role": None,
            "qualifications": None, "perspective_and_conflicts": ["Constructed fixture."],
            "status": "draft", "reviewed_on": None, "record_content_sha256": None,
            "adjudication": None,
            "unresolved_issues": ["Reviewer workflow metadata must stay private."],
        },
    }


class EvidenceDeliveryTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name).resolve()
        (self.root / "manifests").mkdir()
        (self.root / "data/evidence/drafts/v1").mkdir(parents=True)
        (self.root / "data/evidence/reviews").mkdir(parents=True)
        (self.root / "data/evidence/delivery").mkdir(parents=True)
        (self.root / "data/raw").mkdir(parents=True)
        (self.root / "licenses").mkdir()
        project_root = Path(__file__).resolve().parents[1]
        plan = strict_load(project_root / PLAN)
        (self.root / PLAN).write_text(
            json.dumps({"record_schema": plan["record_schema"]}), encoding="utf-8",
        )
        self.source = self.root / "data/raw/source-one.txt"
        self.source.write_text("Ἀρχή ⸀λόγου. \n", encoding="utf-8")
        self.license = self.root / "licenses/fixture-license.txt"
        self.license.write_text("Constructed rights notice.\n", encoding="utf-8")
        self.record = record_fixture(sha256(self.source), sha256(self.license))
        self.record_path = self.root / "data/evidence/drafts/v1/SYNTHETIC01.json"
        self.write_record()
        self.review_path = self.root / "data/evidence/reviews/review.txt"
        self.review_path.write_text("Constructed AI review.\n", encoding="utf-8")
        self.registry = seed_pending_registry(self.root, self.directory, "fixture-registry-v1")
        self.registry["status"] = "reviewed"
        for component in self.registry["records"][0]["components"]:
            component["scholarly_review"] = self.review_decision(scholarly=True)
        self.manifest_path = self.root / "data/evidence/delivery/notice-manifest.json"
        self.manifest = self.make_manifest()
        self.write_manifest()

    def tearDown(self):
        self.temporary.cleanup()

    @property
    def directory(self):
        return self.root / "data/evidence/drafts/v1"

    def write_record(self):
        self.record_path.write_text(json.dumps(self.record, ensure_ascii=False) + "\n", encoding="utf-8")

    def write_manifest(self):
        self.manifest_path.write_text(
            json.dumps(self.manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
        )

    def review_decision(self, *, scholarly=False):
        result = {
            "decision": "approved", "reviewer_kind": "ai",
            "reviewer_role": "AI development source reviewer", "reviewed_on": "2026-09-08",
            "rationale": "Constructed approval for a positive test.",
            "limitations": ["No real evidence or expert review."],
            "supporting_review_evidence": [{
                "evidence_id": "review-1", "path": "data/evidence/reviews/review.txt",
                "content_sha256": sha256(self.review_path),
            }],
        }
        if scholarly:
            result["expert_certification"] = False
        return result

    def make_manifest(self):
        applies = ["SYNTHETIC01/claim-Q1", "SYNTHETIC01/reading-R1"]
        notices = []
        for index, right in enumerate(self.record["rights_by_component"]):
            notices.append({
                "notice_id": "notice-" + right["component"], "record_id": "SYNTHETIC01",
                "source_id": right["source_id"], "rights_component": right["component"],
                "rights_fact_sha256": rights_fact_sha256(right),
                "rights_snapshot_path": "licenses/fixture-license.txt",
                "applies_to_component_keys": copy.deepcopy(applies),
                "license_notice": "A constructed license notice.",
                "disclaimer": "<script>not an instruction</script>; no endorsement.",
            })
        return {
            "schema_version": 1, "notice_manifest_id": "fixture-notices-v1",
            "notices": notices,
            "limitations": ["Before training, wait for a new topic and owner authorization."],
        }

    def approve_app_display(self):
        self.write_manifest()
        for component in self.registry["records"][0]["components"]:
            decision = self.review_decision()
            decision["supporting_review_evidence"].append({
                "evidence_id": "delivery-notice-manifest",
                "path": "data/evidence/delivery/notice-manifest.json",
                "content_sha256": sha256(self.manifest_path),
            })
            component["uses"]["app_display"] = decision

    def build(self, keys=None, manifest=None):
        return build_candidate_bundle(
            self.registry,
            keys or ["SYNTHETIC01/claim-Q1", "SYNTHETIC01/reading-R1"],
            manifest or self.manifest,
            root=self.root,
            record_directory=self.directory,
        )

    def test_candidate_preserves_exact_content_closure_and_is_not_authorized(self):
        candidate = self.build()
        self.assertEqual(candidate["status"], "prepared_not_authorized")
        self.assertEqual(candidate["authorization"], {
            "app_display_eligibility_verified": False,
            "generation_authorized": False,
            "training_authorized": False,
        })
        components = {item["component_id"]: item for item in candidate["records"][0]["components"]}
        self.assertEqual([item["value"]["id"] for item in components["claim-Q1"]["content"]],
                         ["Q1", "Q2"])
        reading = components["reading-R1"]["content"][0]["value"]
        self.assertEqual(reading["original_representation"], "Ἀρχή ⸀λόγου. ")
        self.assertEqual(len(components["claim-Q1"]["notices"]), 2)
        encoded = json.dumps(candidate, ensure_ascii=False)
        self.assertNotIn("registry_id", encoded)
        self.assertNotIn("reviewer_role", encoded)
        self.assertNotIn("snapshot_path", encoded)
        self.assertNotIn("Before training", encoded)
        self.assertEqual(verify_candidate_bundle(
            candidate, self.registry, self.manifest, root=self.root,
            record_directory=self.directory,
        )["status"], "candidate_verified")

    def test_manifest_superset_does_not_leak_unselected_component(self):
        candidate = self.build(["SYNTHETIC01/claim-Q1"])
        self.assertEqual(len(candidate["records"][0]["components"]), 1)
        self.assertEqual(candidate["records"][0]["components"][0]["component_id"], "claim-Q1")
        self.assertNotIn("Ἀρχή", json.dumps(candidate, ensure_ascii=False))
        bad = copy.deepcopy(self.manifest)
        bad["notices"][0]["applies_to_component_keys"].append("SYNTHETIC01/invented")
        with self.assertRaisesRegex(ValueError, "unknown component"):
            self.build(["SYNTHETIC01/claim-Q1"], bad)

    def test_notice_coverage_hash_and_snapshot_fail_closed(self):
        missing = copy.deepcopy(self.manifest)
        missing["notices"].pop()
        with self.assertRaisesRegex(ValueError, "Notice coverage differs"):
            self.build(manifest=missing)
        wrong = copy.deepcopy(self.manifest)
        wrong["notices"][0]["rights_fact_sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "rights fact hash mismatch"):
            self.build(manifest=wrong)
        candidate = self.build()
        self.license.write_text("Changed rights bytes.\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "rights snapshot hash mismatch"):
            verify_candidate_bundle(
                candidate, self.registry, self.manifest, root=self.root,
                record_directory=self.directory,
            )

    def test_use_gate_and_renderers_reverify_current_registry_and_manifest(self):
        candidate = self.build()
        with self.assertRaisesRegex(ValueError, "not currently eligible"):
            verify_for_use(candidate, self.registry, self.manifest, root=self.root,
                           record_directory=self.directory)
        self.approve_app_display()
        candidate = self.build()
        verified = verify_for_use(candidate, self.registry, self.manifest, root=self.root,
                                  record_directory=self.directory)
        self.assertTrue(verified["authorization"]["app_display_eligibility_verified"])
        self.assertFalse(verified["authorization"]["generation_authorized"])
        self.assertFalse(verified["authorization"]["training_authorized"])
        payload = public_delivery_payload(
            verified, self.registry, self.manifest, root=self.root, record_directory=self.directory,
        )
        self.assertEqual(payload["evidence_status"], "supplied_source_material")
        model_text = render_model_input(
            verified, self.registry, self.manifest, root=self.root, record_directory=self.directory,
        )
        raw = model_text.removeprefix("SUPPLIED_EVIDENCE_DATA\n").removesuffix(
            "\nEND_SUPPLIED_EVIDENCE_DATA"
        )
        parsed = json.loads(raw)
        reading = parsed["records"][0]["components"][1]["content"][0]
        self.assertEqual(reading["original_representation"], "Ἀρχή ⸀λόγου. ")
        self.assertNotIn("Before training", model_text)
        self.assertNotIn("reviewer_role", model_text)
        self.assertNotIn("snapshot_path", model_text)
        display = render_display(
            verified, self.registry, self.manifest, root=self.root, record_directory=self.directory,
        )
        self.assertIn("Observed license", display)
        self.assertIn("Rights URL", display)
        self.assertNotIn("<script>", display)

        stale_registry = copy.deepcopy(self.registry)
        component = stale_registry["records"][0]["components"][0]
        component["uses"]["app_display"] = {
            "decision": "pending", "reviewer_kind": None, "reviewer_role": None,
            "reviewed_on": None, "rationale": "Pending again.", "limitations": [],
            "supporting_review_evidence": [],
        }
        with self.assertRaises(ValueError):
            render_model_input(verified, stale_registry, self.manifest, root=self.root,
                               record_directory=self.directory)

    def test_forged_wrapper_and_changed_bound_notice_prose_are_rejected(self):
        self.approve_app_display()
        candidate = self.build()
        verified = verify_for_use(candidate, self.registry, self.manifest, root=self.root,
                                  record_directory=self.directory)
        forged = copy.deepcopy(verified)
        forged["candidate"]["records"][0]["components"][0]["content"][0]["value"]["text"] = "FORGED"
        from bibleprep import evidence_delivery
        forged["candidate_sha256"] = evidence_delivery._canonical_sha256(forged["candidate"])
        with self.assertRaisesRegex(ValueError, "deterministic regeneration"):
            public_delivery_payload(forged, self.registry, self.manifest, root=self.root,
                                    record_directory=self.directory)

        changed = copy.deepcopy(self.manifest)
        changed["notices"][0]["license_notice"] = "Different unreviewed notice prose."
        changed_candidate = self.build(manifest=changed)
        with self.assertRaisesRegex(ValueError, "binds a different notice manifest"):
            verify_for_use(changed_candidate, self.registry, changed, root=self.root,
                           record_directory=self.directory)

    def test_strict_versions_booleans_and_stale_source_fail(self):
        registry = copy.deepcopy(self.registry)
        registry["schema_version"] = True
        with self.assertRaisesRegex(ValueError, "registry schema_version"):
            build_candidate_bundle(registry, ["SYNTHETIC01/claim-Q1"], self.manifest,
                                   root=self.root, record_directory=self.directory)
        manifest = copy.deepcopy(self.manifest)
        manifest["schema_version"] = True
        with self.assertRaisesRegex(ValueError, "manifest schema_version"):
            self.build(manifest=manifest)
        candidate = self.build()
        candidate["authorization"]["generation_authorized"] = 0
        with self.assertRaisesRegex(ValueError, "flags must be booleans"):
            verify_candidate_bundle(candidate, self.registry, self.manifest, root=self.root,
                                    record_directory=self.directory)
        self.source.write_text("Changed source.\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "Source snapshot hash mismatch"):
            self.build()

    def test_private_writer_is_exclusive_and_rejects_symlinks(self):
        candidate = self.build()
        path = self.root / "runs/delivery/candidate.json"
        receipt = write_private_json(candidate, path, root=self.root)
        self.assertEqual(receipt["path"], "runs/delivery/candidate.json")
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        self.assertEqual(path.parent.stat().st_mode & 0o777, 0o700)
        with self.assertRaises(FileExistsError):
            write_private_json(candidate, path, root=self.root)
        outside = self.root.parent / (self.root.name + "-outside")
        outside.mkdir()
        self.addCleanup(lambda: outside.rmdir())
        os.symlink(outside, self.root / "runs-link", target_is_directory=True)
        with self.assertRaises(ValueError):
            write_private_json(candidate, self.root / "runs-link/candidate.json", root=self.root)


if __name__ == "__main__":
    unittest.main()
