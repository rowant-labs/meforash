import copy
import builtins
from contextlib import ExitStack
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest import mock

from bibleprep import prepare_instruction as p
from bibleprep import prepare_instruction_revision as revision


class FixtureRenderer:
    """Deterministic valid shifted tokens for provenance tests, not a TML replica."""
    identity = {"runtime_packages": {"fixture": "1"}, "fixture": True}

    def render(self, prompt, answer, evidence, mode="provided"):
        encode = lambda text: [ord(char) + 10 for char in text]
        prefix = [200002, 1] + encode(prompt + (evidence if mode == "provided" else "")) + [2]
        ids = prefix + [3] + encode(answer) + [4, 200006]
        return {"input_ids": ids[:-1], "target_ids": ids[1:],
                "weights": [0.] * (len(prefix) - 1) + [1.] * (len(ids) - len(prefix)),
                "processed_token_count": len(ids) - 1, "loss_token_count": len(ids) - len(prefix),
                "prompt_token_count": len(prefix), "prompt_token_sha256": p.digest(p.json_bytes(prefix))}


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(p.json_bytes(value) + b"\n")


def write_rows(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"".join(p.json_bytes(row) + b"\n" for row in rows))


def file_ref(root, path):
    return {"path": path, "sha256": p.digest((root / path).read_bytes())}


def create_fixture(root):
    for relative in revision.CODE_FILES:
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("fixture pinned code\n")
    ids = sorted([f"IH{i:03}" for i in range(1, 41)] + [f"IA{i:03}" for i in range(1, 25)]
                 + [f"IG{i:03}" for i in range(1, 41)] + [f"IM{i:03}" for i in range(1, 17)])
    examples, records = [], []
    source_revision = "a" * 40
    for index, cid in enumerate(ids):
        chapter = index + 1
        url = p.source_url("oshb", "Gen", source_revision)
        refs = [{"source_id": "oshb", "passage": f"Gen.{chapter}.1", "url": url, "revision": source_revision}]
        row = {"id": cid, "language": "hbo", "category": "grammar", "source_refs": refs,
               "chapter_keys": [f"oshb:Gen.{chapter}"], "evidence_mode": "provided", "prompt": f"Explain {cid}.",
               "answer": "A checked narrow explanation.", "author": "original_author", "support_notes": "Source checked.",
               "reviewer": "original_reviewer", "review_status": "ai_source_checked", "review_sources": [url]}
        row["reviewed_content_sha256"] = p.content_hash(row)
        examples.append(row)
        records.append({"id": f"oshb:Gen.{chapter}.1", "source_id": "oshb", "book": "Gen", "chapter": chapter,
                        "verse": 1, "language": "hbo", "text_layer": "main/ketiv", "text": "דָּבָר"})
    write_rows(root / "data/processed/oshb/verses.jsonl", records)
    write_rows(root / "data/processed/sblgnt/verses.jsonl", [{"id": "sblgnt:Mark.1.1", "source_id": "sblgnt",
               "book": "Mark", "chapter": 1, "verse": 1, "language": "grc", "text": "λόγος"}])
    write_json(root / "manifests/oshb.json", {"pinned_commit": source_revision, "prepared_artifact": {
        "sha256": p.digest((root / "data/processed/oshb/verses.jsonl").read_bytes())}})
    write_json(root / "manifests/sblgnt.json", {"revision": source_revision, "prepared_outputs": {"verses.jsonl": {
        "sha256": p.digest((root / "data/processed/sblgnt/verses.jsonl").read_bytes())}}})
    inventory = {"schema_version": 1, "status": "frozen", "evaluation_sha256": "e" * 64,
                 "chapter_keys": ["sblgnt:Luke.100"], "criteria_included": False}
    write_json(root / "manifests/old-exclusions.json", inventory)
    write_json(root / "manifests/new-exclusions.json", inventory)
    write_rows(root / revision.ORIGINAL_DATASET, examples)
    validation = [e["chapter_keys"][0] for e in examples if e["id"].startswith("IM")]
    with mock.patch.object(p, "InstructionRenderer", FixtureRenderer):
        parent = p.prepare(revision.ORIGINAL_DATASET, "manifests/old-exclusions.json", root=root,
                           validation_chapters=validation)
    new = {e["id"]: copy.deepcopy(e) for e in examples}
    groups = []
    for name, selected in revision.GROUP_IDS.items():
        drafts, approvals = [], []
        for cid in selected:
            before = next(e for e in examples if e["id"] == cid)
            draft = {"id": cid, "prompt": f"Translate the complete source for {cid}, then explain it.",
                     "answer": "A complete translation. A checked grammatical explanation.", "author": f"{name}_author",
                     "support_notes": "All source clauses checked.", "coverage": ["Full translation", "Grammar"],
                     "rationale": "Broader task exposure.", "source_urls": before["review_sources"],
                     "old_prompt_sha256": p.digest(before["prompt"].encode()),
                     "old_answer_sha256": p.digest(before["answer"].encode()), "status": "authored_pending_review"}
            if name == "aramaic":
                draft.update(new_prompt_sha256=p.digest(draft["prompt"].encode()),
                             new_answer_sha256=p.digest(draft["answer"].encode()))
            candidate = new[cid]
            candidate.update({field: draft[field] for field in revision.AUTHORED_FIELDS})
            candidate.update(reviewer=f"{name}_reviewer", review_sources=draft["source_urls"], review_status="ai_source_checked")
            candidate["reviewed_content_sha256"] = p.content_hash(candidate)
            drafts.append(draft)
            approvals.append({"id": cid, "status": "approved", "content_sha256": candidate["reviewed_content_sha256"],
                              "source_urls": candidate["review_sources"], "coverage_complete": True, "notes": "Checked."})
        draft_path = f"runs/instruction-v3-prep/{name}/revisions.jsonl"
        receipt_path = f"runs/instruction-v3-prep/reviews/{name}.json"
        write_rows(root / draft_path, drafts)
        receipt = {"status": "approved", "reviewer": f"{name}_reviewer",
                   "revisions_file_sha256": p.digest((root / draft_path).read_bytes()), "approvals": approvals,
                   "expert_certified": False, "limitations": ["Fixture AI check."]}
        if name == "aramaic":
            receipt.update(schema_version=1, review_basis="Pinned-source clause check.")
        write_json(root / receipt_path, receipt)
        groups.append({"name": name, "ids": list(selected), "revision_drafts": file_ref(root, draft_path),
                       "receipt": file_ref(root, receipt_path)})
    write_rows(root / revision.REVISED_DATASET, [new[e["id"]] for e in examples])
    plan = {"schema_version": 3, "status": "frozen_before_preparation", "revision_id": "instruction-revision-v3",
            "original_preparation": file_ref(root, revision.ORIGINAL_PREPARATION),
            "original_dataset": file_ref(root, revision.ORIGINAL_DATASET),
            "revised_dataset": file_ref(root, revision.REVISED_DATASET), "changed_training_ids": list(revision.CHANGED_IDS),
            "unchanged_validation_sha256": parent["artifacts"]["validation"]["sha256"],
            "evaluation_exclusion": file_ref(root, "manifests/new-exclusions.json"), "review_groups": groups,
            "settings": copy.deepcopy(revision.SETTINGS)}
    write_json(root / "manifests/revision-plan.json", plan)
    return {"ORIGINAL_PREPARATION_SHA256": plan["original_preparation"]["sha256"],
            "ORIGINAL_DATASET_SHA256": plan["original_dataset"]["sha256"],
            "VALIDATION_SHA256": plan["unchanged_validation_sha256"]}


class RevisionPreparationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.template = tempfile.TemporaryDirectory()
        cls.anchors = create_fixture(Path(cls.template.name))

    @classmethod
    def tearDownClass(cls):
        cls.template.cleanup()

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        shutil.copytree(self.template.name, self.root, dirs_exist_ok=True)
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(mock.patch.multiple(revision, **self.anchors))
        self.stack.enter_context(mock.patch.object(p, "InstructionRenderer", FixtureRenderer))
        self.plan_path = "manifests/revision-plan.json"

    def plan(self):
        return json.loads((self.root / self.plan_path).read_text())

    def save_plan(self, plan):
        write_json(self.root / self.plan_path, plan)

    def edited_rows(self, mutate):
        path = self.root / revision.REVISED_DATASET
        rows = p.read_rows(path)
        mutate(rows)
        write_rows(path, rows)
        plan = self.plan()
        plan["revised_dataset"] = file_ref(self.root, revision.REVISED_DATASET)
        self.save_plan(plan)

    def edit_group(self, name, *, draft_mutate=None, receipt_mutate=None, bind_drafts=False):
        plan = self.plan()
        group = next(g for g in plan["review_groups"] if g["name"] == name)
        if draft_mutate:
            drafts = p.read_rows(self.root / group["revision_drafts"]["path"])
            draft_mutate(drafts)
            write_rows(self.root / group["revision_drafts"]["path"], drafts)
            group["revision_drafts"] = file_ref(self.root, group["revision_drafts"]["path"])
        receipt = json.loads((self.root / group["receipt"]["path"]).read_text())
        if bind_drafts:
            receipt["revisions_file_sha256"] = group["revision_drafts"]["sha256"]
        if receipt_mutate:
            receipt_mutate(receipt)
        write_json(self.root / group["receipt"]["path"], receipt)
        group["receipt"] = file_ref(self.root, group["receipt"]["path"])
        self.save_plan(plan)

    def test_deterministic_build_preserves_all_unchanged_bytes_and_no_eval_access(self):
        reads = []
        original = Path.read_bytes
        original_path_open = Path.open
        original_open = builtins.open
        def guard(path):
            if isinstance(path, int):
                return
            reads.append(str(path))
            self.assertNotIn("/evals/", str(path))
            self.assertNotIn("/evaluation/", str(path))
            self.assertNotEqual(Path(path).name, ".env")
        def observed(path):
            guard(path)
            return original(path)
        def observed_path_open(path, *args, **kwargs):
            guard(path)
            return original_path_open(path, *args, **kwargs)
        def observed_open(path, *args, **kwargs):
            guard(path)
            return original_open(path, *args, **kwargs)
        with mock.patch.object(Path, "read_bytes", observed), mock.patch.object(Path, "open", observed_path_open), \
                mock.patch.object(builtins, "open", observed_open):
            report = revision.prepare(self.plan_path, root=self.root)
            rows = revision.verify_prepared(self.root, report)
        self.assertTrue(reads)
        self.assertEqual([len(rows[k]) for k in ("train", "validation")], [104, 16])
        self.assertEqual(report["unchanged_training_rows"], 90)
        parent = self.root / p.ARTIFACT_DIRECTORY / "validation.jsonl"
        self.assertEqual(parent.read_bytes(), (self.root / revision.ARTIFACT_DIRECTORY / "validation.jsonl").read_bytes())
        self.assertEqual((self.root / revision.ARTIFACT_DIRECTORY).stat().st_mode & 0o777, 0o700)
        self.assertEqual((self.root / revision.ARTIFACT_DIRECTORY / "train.jsonl").stat().st_mode & 0o777, 0o600)
        with self.assertRaisesRegex(ValueError, "overwrite"):
            revision.prepare(self.plan_path, root=self.root)

    def test_unchanged_full_row_serialization_is_preserved(self):
        path = self.root / revision.REVISED_DATASET
        data = path.read_bytes()
        rows = data.splitlines(keepends=True)
        index = next(i for i, line in enumerate(rows) if json.loads(line)["id"] not in revision.CHANGED_IDS)
        rows[index] = json.dumps(json.loads(rows[index]), ensure_ascii=False).encode() + b"\n"
        path.write_bytes(b"".join(rows))
        plan = self.plan(); plan["revised_dataset"] = file_ref(self.root, revision.REVISED_DATASET); self.save_plan(plan)
        with self.assertRaisesRegex(ValueError, "unchanged full row"):
            revision.build(self.plan_path, root=self.root)

    def test_validation_target_cannot_change_even_with_new_review_hash(self):
        def mutate(rows):
            row = next(e for e in rows if e["id"] == "IM001")
            row["answer"] += " changed"
            row["reviewed_content_sha256"] = p.content_hash(row)
        self.edited_rows(mutate)
        with self.assertRaisesRegex(ValueError, "unchanged full row"):
            revision.build(self.plan_path, root=self.root)

    def test_source_evidence_category_and_chapter_changes_rejected_before_render(self):
        for field, value in (("source_refs", []), ("chapter_keys", ["oshb:Gen.999"]),
                             ("evidence_mode", "none"), ("category", "different"), ("language", "grc")):
            with self.subTest(field=field):
                self.edited_rows(lambda rows: next(e for e in rows if e["id"] == "IG002").update({field: value}))
                with self.assertRaisesRegex(ValueError, "Source, evidence"):
                    revision.build(self.plan_path, root=self.root)
                shutil.copy2(Path(self.template.name) / revision.REVISED_DATASET, self.root / revision.REVISED_DATASET)

    def test_order_and_selected_id_changes_rejected(self):
        self.edited_rows(lambda rows: rows.reverse())
        with self.assertRaisesRegex(ValueError, "IDs or order"):
            revision.build(self.plan_path, root=self.root)
        shutil.copy2(Path(self.template.name) / self.plan_path, self.root / self.plan_path)
        plan = self.plan(); plan["changed_training_ids"][0] = "IM001"; self.save_plan(plan)
        with self.assertRaisesRegex(ValueError, "fourteen"):
            revision.build(self.plan_path, root=self.root)

    def test_stale_draft_receipt_binding_and_optional_new_hashes_rejected(self):
        self.edit_group("aramaic", draft_mutate=lambda rows: rows[0].update(rationale="Updated rationale."))
        with self.assertRaisesRegex(ValueError, "stale"):
            revision.build(self.plan_path, root=self.root)
        self.edit_group("aramaic", draft_mutate=lambda rows: rows[0].update(new_answer_sha256="0" * 64), bind_drafts=True)
        with self.assertRaisesRegex(ValueError, "new-content hash"):
            revision.build(self.plan_path, root=self.root)

    def test_changed_target_cannot_reuse_approval_even_after_rehashing_containers(self):
        new_answer = "An unauthorized replacement answer."
        def mutate(rows):
            row = next(e for e in rows if e["id"] == "IG002")
            row["answer"] = new_answer; row["reviewed_content_sha256"] = p.content_hash(row)
        self.edited_rows(mutate)
        self.edit_group("greek", draft_mutate=lambda rows: rows[0].update(answer=new_answer), bind_drafts=True)
        with self.assertRaisesRegex(ValueError, "Reviewed content hash"):
            revision.build(self.plan_path, root=self.root)

    def test_full_candidate_must_match_author_draft(self):
        self.edited_rows(lambda rows: next(e for e in rows if e["id"] == "IG002").update(support_notes="Unreviewed note"))
        with self.assertRaisesRegex(ValueError, "author draft"):
            revision.build(self.plan_path, root=self.root)

    def test_missing_or_incomplete_approval_rejected(self):
        self.edit_group("greek", receipt_mutate=lambda receipt: receipt["approvals"][0].update(coverage_complete=False))
        with self.assertRaisesRegex(ValueError, "coverage approval"):
            revision.build(self.plan_path, root=self.root)
        self.edit_group("greek", receipt_mutate=lambda receipt: receipt["approvals"].pop())
        with self.assertRaisesRegex(ValueError, "coverage/order"):
            revision.build(self.plan_path, root=self.root)

    def test_self_review_and_source_review_reference_mismatch_rejected(self):
        self.edit_group("greek", receipt_mutate=lambda receipt: receipt.update(reviewer="greek_author"))
        with self.assertRaisesRegex(ValueError, "Self-review"):
            revision.build(self.plan_path, root=self.root)
        self.edit_group("greek", receipt_mutate=lambda receipt: receipt.update(reviewer="greek_reviewer"))
        self.edited_rows(lambda rows: next(e for e in rows if e["id"] == "IG002").update(review_sources=["https://different.example/source"]))
        with self.assertRaisesRegex(ValueError, "references differ"):
            revision.build(self.plan_path, root=self.root)

    def test_exclusion_rejects_question_content_and_source_overlap(self):
        path = self.root / "manifests/new-exclusions.json"
        inventory = json.loads(path.read_text())
        for change in ({"questions": ["Forbidden evaluation content"]}, {"chapter_keys": ["oshb:Gen.1"]}):
            write_json(path, {**inventory, **change})
            plan = self.plan(); plan["evaluation_exclusion"] = file_ref(self.root, "manifests/new-exclusions.json"); self.save_plan(plan)
            with self.subTest(change=change), self.assertRaises(ValueError):
                revision.build(self.plan_path, root=self.root)

    def test_pinned_parent_and_settings_cannot_be_replaced(self):
        for update in ({"unchanged_validation_sha256": "0" * 64},
                       {"settings": {**revision.SETTINGS, "thinking_effort_numeric": 0.2}},
                       {"original_preparation": {"path": revision.ORIGINAL_PREPARATION, "sha256": "0" * 64}}):
            plan = json.loads((Path(self.template.name) / self.plan_path).read_text()); plan.update(update); self.save_plan(plan)
            with self.subTest(update=update), self.assertRaises(ValueError):
                revision.build(self.plan_path, root=self.root)

    def test_rehashed_tokens_and_preparation_code_changes_fail_verification(self):
        report = revision.prepare(self.plan_path, root=self.root)
        path = self.root / report["artifacts"]["train"]["path"]
        original = path.read_bytes()
        rows = p.read_rows(path); rows[0]["weights"][0] = 1.; write_rows(path, rows)
        tampered = copy.deepcopy(report); tampered["artifacts"]["train"]["sha256"] = p.digest(path.read_bytes())
        with self.assertRaisesRegex(ValueError, "provenance changed"):
            revision.verify_prepared(self.root, tampered)
        path.write_bytes(original)
        (self.root / revision.CODE_FILES[0]).write_text("changed prep code")
        with self.assertRaisesRegex(ValueError, "provenance changed"):
            revision.verify_prepared(self.root, report)

    def test_stale_bytes_and_duplicate_json_keys_fail_closed(self):
        path = self.root / revision.REVISED_DATASET
        path.write_bytes(path.read_bytes() + b" ")
        with self.assertRaisesRegex(ValueError, "checksum"):
            revision.build(self.plan_path, root=self.root)
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            revision.decode('{"schema_version":3,"schema_version":1}')


class NativeRevisionTests(unittest.TestCase):
    def test_shared_renderer_keeps_once_shifted_final_only_mask(self):
        renderer = p.InstructionRenderer()
        old = renderer.render("Explain the Greek.", "A focused explanation.", "λόγος")
        new = renderer.render("Translate every clause, then explain it.", "A full translation. A focused explanation.", "λόγος")
        for row in (old, new):
            p.validate_sequence(row, revision.SETTINGS["maximum_input_tokens"])
            self.assertEqual(row["weights"], [0.] * (row["prompt_token_count"] - 1)
                             + [1.] * (len(row["input_ids"]) - row["prompt_token_count"] + 1))
            self.assertEqual(row["input_ids"][1:], row["target_ids"][:-1])
            self.assertEqual(row["target_ids"][-1], 200006)
        self.assertNotEqual(old["prompt_token_sha256"], new["prompt_token_sha256"])


if __name__ == "__main__":
    unittest.main()
