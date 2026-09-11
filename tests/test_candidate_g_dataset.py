"""Focused constructed tests for the offline Candidate G dataset compiler."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from bibleprep import prepare_instruction as instruction
from bibleprep.candidate_g_dataset import (
    CandidateGDatasetError, PREPARED_FIELDS, build_evidence, canonical_bytes,
    canonical_sha256, compile_prepared_dataset, load_exact_rehearsal_rows,
    load_text_sources, sha256_bytes, validate_target_reviews,
)
from tests.test_candidate_g_plan import CandidateGPlanTests


class FakeRenderer:
    def __init__(self):
        self.evidence = []
        self.system_prompt = "Frozen constructed Candidate G baseline prompt."
        self.effort = 0.7

    def render(self, question, answer, evidence, mode):
        self.evidence.append(evidence)
        ids = [200002, 10, 11, 12]
        return {
            "input_ids": ids,
            "target_ids": [10, 11, 12, 200006],
            "weights": [0.0, 1.0, 1.0, 1.0],
            "processed_token_count": 4,
            "loss_token_count": 3,
            "prompt_token_count": 2,
            "prompt_token_sha256": sha256_bytes(instruction.json_bytes(ids[:2])),
        }


class CandidateGDatasetTests(unittest.TestCase):
    def setUp(self):
        base = CandidateGPlanTests(methodName="test_valid_plan_has_exact_counts_and_is_not_training_ready")
        base.setUp()
        self.plan = copy.deepcopy(base.plan)
        self.inventory = copy.deepcopy(base.inventory)
        self.permissions = copy.deepcopy(base.permissions)

        # Give every family an exact, unique selected verse and use the two
        # source/layer combinations supported by the compiler.
        layer_by_language = {x["language"]: x for x in self.inventory["source_layers"]}
        permission_by_language = {x["language"]: x for x in self.permissions["decisions"]}
        all_source_refs = {language: [] for language in ("hbo", "grc", "arc")}
        family_by_id = {}
        for family in [*self.inventory["training_families"],
                       *self.inventory["validation_families"]]:
            family_by_id[family["family_id"]] = family
        rehearsal_by_id = {}
        for item in self.inventory["rehearsal_rows"]:
            rehearsal_by_id[item["rehearsal_row_id"]] = item

        for language, layer in layer_by_language.items():
            source_id = "sblgnt" if language == "grc" else "oshb"
            source_layer = "sblgnt-main-text" if language == "grc" else "oshb-wlc-main-ketiv"
            layer["source_id"] = source_id
            layer["layer"] = source_layer
            layer["edition"] = "Constructed pinned edition"
            permission = permission_by_language[language]
            permission["source_id"] = source_id
            permission["source_layer"] = source_layer

        def bind_item(item):
            language = item["language"]
            layer = layer_by_language[language]
            ref = f"{layer['source_id']}:{item['book']}.{item['chapter']}.1"
            item.update({
                "source_id": layer["source_id"], "source_layer": layer["layer"],
                "source_refs": [ref],
            })
            all_source_refs[language].append(ref)

        for item in [*self.inventory["training_families"],
                     *self.inventory["validation_families"],
                     *self.inventory["rehearsal_rows"]]:
            bind_item(item)
        for language, layer in layer_by_language.items():
            layer["source_refs"] = all_source_refs[language]

        for planned in [*self.plan["training_rows"], *self.plan["validation_rows"]]:
            item = (rehearsal_by_id[planned["rehearsal_row_id"]]
                    if planned["group"] == "rehearsal"
                    else family_by_id[planned["family_id"]])
            for field in ("source_id", "source_layer", "source_refs"):
                planned[field] = copy.deepcopy(item[field])

        self.rights = {
            "schema_version": 1,
            "artifact_kind": "candidate_g_rights_fact_digest_closure_v1",
            "status": "reproducible_nonexpert_planning_facts",
            "hash_basis": "Exact UTF-8 canonical text.",
            "facts": [],
        }
        for language, layer in layer_by_language.items():
            permission = permission_by_language[language]
            text = f"Constructed {language} source-use fact."
            fact_hash = sha256_bytes(text.encode("utf-8"))
            layer["rights_fact_sha256"] = fact_hash
            permission["rights_fact_sha256"] = fact_hash
            self.rights["facts"].append({
                "rights_fact_id": f"rights-{language}",
                "canonical_text": text,
                "canonical_text_utf8_sha256": fact_hash,
                "source_ids": [layer["source_id"]], "languages": [language],
                "permission_refs": [layer["permission_ref"]],
                "basis_refs": [f"fixture:{language}"],
                "rights_notice_bindings": [{
                    "path": layer["rights_notice_path"],
                    "sha256": layer["rights_notice_sha256"],
                }],
                "limits": ["Constructed test only."],
            })

        self.source_records = {}
        for family in [*self.inventory["training_families"],
                       *self.inventory["validation_families"]]:
            ref = family["source_refs"][0]
            source = {
                "id": ref, "source_id": family["source_id"],
                "book": family["book"], "chapter": int(family["chapter"]),
                "verse": 1, "language": family["language"],
                "languages": [family["language"]],
                "text": "בְּרֵאשִׁית" if family["language"] == "hbo" else (
                    "מַלְכָּא" if family["language"] == "arc" else "Ἐν ἀρχῇ"),
                "layer": "main" if family["source_id"] == "sblgnt" else "main/ketiv",
                "source_ref": ref,
            }
            if family["source_id"] == "oshb":
                source["reference_system"] = "Bible.MT"
            else:
                source.update({"source_file": "fixture.xml", "source_line": 7})
            self.source_records[ref] = source

        expected = {row["row_id"]: row for row in
                    [*self.plan["training_rows"], *self.plan["validation_rows"]]
                    if row["group"] != "rehearsal"}
        self.authored = []
        for planned in expected.values():
            self.authored.append({
                "schema_version": 1, **{
                    field: copy.deepcopy(planned[field]) for field in (
                        "row_id", "split", "group", "family_id", "language",
                        "book", "chapter", "source_span", "source_id",
                        "source_path", "source_sha256", "source_layer",
                        "source_refs", "permission_ref", "language_boundary_ref")
                },
                "selected_verse_ids": [planned["source_refs"][0]],
                "question": f"What does {planned['row_id']} ask?",
                "answer": f"A concise final English answer for {planned['row_id']}.",
                "intent": "textual_question", "scope": "Selected verse only.",
                "project_english_rendering": None,
                "authoring": {
                    "author_kind": "ai", "author_role": "target author",
                    "provenance": "Constructed test fixture.",
                    "reasoning_in_target": False,
                },
            })
        self.reviews = [self.review_for(row) for row in self.authored]
        self.prompt_hash = sha256_bytes(
            FakeRenderer().system_prompt.encode("utf-8"))

        self.rehearsal = {}
        for item in self.inventory["rehearsal_rows"]:
            prepared = self.prepared_row(item["old_row_id"], item["language"])
            line = canonical_bytes(prepared)
            item["full_row_sha256"] = sha256_bytes(line)
            self.rehearsal[item["rehearsal_row_id"]] = line
        hashes = {x["rehearsal_row_id"]: x["full_row_sha256"]
                  for x in self.inventory["rehearsal_rows"]}
        for planned in self.plan["training_rows"]:
            if planned["group"] == "rehearsal":
                planned["full_row_sha256"] = hashes[planned["rehearsal_row_id"]]

    @staticmethod
    def prepared_row(row_id, language):
        ids = [200002, 10, 11, 12]
        return {
            "input_ids": ids, "target_ids": [10, 11, 12, 200006],
            "weights": [0.0, 1.0, 1.0, 1.0],
            "processed_token_count": 4, "loss_token_count": 3,
            "prompt_token_count": 2,
            "prompt_token_sha256": sha256_bytes(instruction.json_bytes(ids[:2])),
            "id": row_id, "language": language, "category": "old",
            "chapter_keys": ["old:Book.1"], "source_refs": ["old:ref"],
            "answer_sha256": sha256_bytes(b"old answer"),
            "reviewed_content_sha256": sha256_bytes(b"old reviewed"),
            "evidence_sha256": sha256_bytes(b"old evidence"),
            "evidence_mode": "provided",
        }

    @staticmethod
    def review_for(row):
        rendering = row["project_english_rendering"]
        return {
            "row_id": row["row_id"],
            "authored_row_sha256": canonical_sha256(row),
            "question_sha256": sha256_bytes(row["question"].encode("utf-8")),
            "answer_sha256": sha256_bytes(row["answer"].encode("utf-8")),
            "selected_verse_ids_sha256": canonical_sha256(row["selected_verse_ids"]),
            "project_english_rendering_sha256": (
                canonical_sha256(rendering) if rendering is not None else None),
            "authoring_sha256": canonical_sha256(row["authoring"]),
            "decision": "approved", "reviewer_kind": "ai",
            "reviewer_role": "independent target reviewer", "conflicts": [],
            "expert_certified": False, "source_support": "pass",
            "coverage": "pass", "attribution": "pass", "scope": "pass",
            "english_quality": "pass", "rationale": "Constructed approval.",
            "evidence_refs": row["selected_verse_ids"],
        }

    def compile(self, renderer=None):
        return compile_prepared_dataset(
            self.plan, self.inventory, self.permissions, self.rights,
            self.authored, self.reviews, renderer or FakeRenderer(),
            self.prompt_hash, self.source_records, self.rehearsal,
        )

    def test_compile_exact_counts_mask_and_rehearsal_bytes(self):
        renderer = FakeRenderer()
        data, summary = self.compile(renderer)
        self.assertEqual(summary["counts"], {
            "train": 96, "validation": 24, "new": 104, "rehearsal": 16})
        self.assertFalse(summary["settings"]["reasoning_targets"])
        self.assertFalse(summary["settings"]["rejected_guidance_suffix_adopted"])
        self.assertEqual(summary["settings"]["system_prompt_sha256"],
                         sha256_bytes(renderer.system_prompt.encode("utf-8")))
        self.assertIn("not rerendered", summary["settings"]["rehearsal_framing"])
        self.assertIn(next(iter(self.rehearsal.values())) + b"\n", data["train"])
        new = json.loads(data["validation"].splitlines()[0])
        self.assertEqual(new["weights"], [0.0, 1.0, 1.0, 1.0])
        self.assertEqual(set(new), PREPARED_FIELDS)
        self.assertEqual(len(renderer.evidence), 104)
        with self.assertRaisesRegex(CandidateGDatasetError, "frozen baseline"):
            compile_prepared_dataset(
                self.plan, self.inventory, self.permissions, self.rights,
                self.authored, self.reviews, FakeRenderer(), "0" * 64,
                self.source_records, self.rehearsal)

    def test_exact_unicode_and_minimal_evidence_fields(self):
        renderer = FakeRenderer()
        self.compile(renderer)
        evidence = "\n".join(renderer.evidence)
        self.assertIn("בְּרֵאשִׁית", evidence)
        self.assertIn("מַלְכָּא", evidence)
        self.assertIn("Ἐν ἀρχῇ", evidence)
        for forbidden in ("morphology", "tokens", "apparatus", "raw_record"):
            self.assertNotIn(forbidden, evidence)
        self.assertIn("not target or training approval", evidence)

    def test_selected_span_language_and_review_bindings_are_strict(self):
        authored = copy.deepcopy(self.authored)
        authored[0]["selected_verse_ids"] = ["outside:verse"]
        with self.assertRaisesRegex(CandidateGDatasetError, "leave or repeat"):
            compile_prepared_dataset(
                self.plan, self.inventory, self.permissions, self.rights,
                authored, self.reviews, FakeRenderer(), self.prompt_hash,
                self.source_records,
                self.rehearsal)
        records = copy.deepcopy(self.source_records)
        selected = self.authored[0]["selected_verse_ids"][0]
        records[selected]["languages"] = [self.authored[0]["language"], "arc"]
        with self.assertRaisesRegex(CandidateGDatasetError, "mixed"):
            compile_prepared_dataset(
                self.plan, self.inventory, self.permissions, self.rights,
                self.authored, self.reviews, FakeRenderer(), self.prompt_hash,
                records, self.rehearsal)
        reviews = copy.deepcopy(self.reviews)
        reviews[0]["question_sha256"] = "0" * 64
        with self.assertRaisesRegex(CandidateGDatasetError, "question_sha256 is stale"):
            validate_target_reviews({x["row_id"]: x for x in self.authored}, reviews)

    def test_rights_notice_and_rehearsal_bindings_reject_changes(self):
        rights = copy.deepcopy(self.rights)
        rights["facts"][0]["rights_notice_bindings"][0]["sha256"] = "0" * 64
        with self.assertRaisesRegex(CandidateGDatasetError, "Rights notice binding"):
            compile_prepared_dataset(
                self.plan, self.inventory, self.permissions, rights,
                self.authored, self.reviews, FakeRenderer(), self.prompt_hash,
                self.source_records,
                self.rehearsal)
        rehearsal = copy.deepcopy(self.rehearsal)
        key = next(iter(rehearsal))
        rehearsal[key] += b" "
        with self.assertRaisesRegex(CandidateGDatasetError, "rehearsal row binding"):
            compile_prepared_dataset(
                self.plan, self.inventory, self.permissions, self.rights,
                self.authored, self.reviews, FakeRenderer(), self.prompt_hash,
                self.source_records,
                rehearsal)

    def test_source_loader_rejects_stale_file_and_non_main_text(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = {
                "id": "oshb:Book.1.1", "source_id": "oshb", "book": "Book",
                "chapter": 1, "verse": 1, "language": "hbo",
                "languages": ["hbo"], "text": "אָ", "text_layer": "main/ketiv",
                "source_ref": "Gen.1.1", "reference_system": "Bible.MT",
            }
            raw = canonical_bytes(source) + b"\n"
            (root / "source.jsonl").write_bytes(raw)
            inventory = {"source_layers": [{
                "local_path": "source.jsonl", "content_sha256": sha256_bytes(raw),
                "source_refs": [source["id"]], "source_id": "oshb", "language": "hbo",
            }]}
            loaded = load_text_sources(root, inventory)
            self.assertEqual(loaded[source["id"]]["text"], "אָ")
            inventory["source_layers"][0]["content_sha256"] = "0" * 64
            with self.assertRaisesRegex(CandidateGDatasetError, "file hash differs"):
                load_text_sources(root, inventory)
            inventory["source_layers"][0]["content_sha256"] = sha256_bytes(raw)
            source["text_layer"] = "morphology"
            changed = canonical_bytes(source) + b"\n"
            (root / "source.jsonl").write_bytes(changed)
            inventory["source_layers"][0]["content_sha256"] = sha256_bytes(changed)
            with self.assertRaisesRegex(CandidateGDatasetError, "main/ketiv"):
                load_text_sources(root, inventory)


if __name__ == "__main__":
    unittest.main()
