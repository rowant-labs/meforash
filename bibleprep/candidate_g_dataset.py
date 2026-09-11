"""Compile reviewed Candidate G rows offline without training or provider calls.

New examples use the established Inkling native SFT renderer.  Rehearsal rows
are copied from exact saved prepared-row bytes and are never rerendered.  This
module does not author content, access credentials, call a model, or train.
"""
from __future__ import annotations

from collections import Counter
import hashlib
import json
from pathlib import Path
import re

from bibleprep.candidate_g_plan import validate_plan
from bibleprep import prepare_instruction as instruction


SCHEMA_VERSION = 1
MAXIMUM_INPUT_TOKENS = 8192
LANGUAGES = frozenset({"hbo", "arc", "grc"})
INTENTS = frozenset({
    "textual_question", "translation_question", "evidence_boundary",
    "contemporary_application",
})
SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")
AUTHOR_ROW_FIELDS = frozenset({
    "schema_version", "row_id", "split", "group", "family_id", "language",
    "book", "chapter", "source_span", "source_id", "source_path",
    "source_sha256", "source_layer", "source_refs", "permission_ref",
    "language_boundary_ref", "selected_verse_ids", "question", "answer",
    "intent", "scope", "project_english_rendering", "authoring",
})
REVIEW_FIELDS = frozenset({
    "row_id", "authored_row_sha256", "question_sha256", "answer_sha256",
    "selected_verse_ids_sha256", "project_english_rendering_sha256",
    "authoring_sha256", "decision", "reviewer_kind", "reviewer_role",
    "conflicts", "expert_certified", "source_support", "coverage",
    "attribution", "scope", "english_quality", "rationale", "evidence_refs",
})
PREPARED_FIELDS = frozenset({
    "input_ids", "target_ids", "weights", "processed_token_count",
    "loss_token_count", "prompt_token_count", "prompt_token_sha256", "id",
    "language", "category", "chapter_keys", "source_refs", "answer_sha256",
    "reviewed_content_sha256", "evidence_sha256", "evidence_mode",
})
SOURCE_ATTRIBUTION = {
    "oshb": "Open Scriptures Hebrew Bible, based on the Westminster Leningrad Codex; selected main/ketiv text.",
    "sblgnt": "SBL Greek New Testament, Michael W. Holmes; Society of Biblical Literature and Logos Bible Software.",
}


class CandidateGDatasetError(ValueError):
    """Raised when authored, reviewed, source, or prepared data is invalid."""


class CandidateGRenderer:
    """Render new rows with an explicitly injected, hashable native prompt."""

    def __init__(self, system_prompt, effort=0.7):
        _text(system_prompt, "system_prompt")
        if effort != 0.7:
            raise CandidateGDatasetError("Candidate G native effort must be exactly 0.7")
        self.system_prompt = system_prompt
        self.effort = effort
        self.tokenizer, _, _, self.identity = instruction.raw.load_tokenizer()
        from tml_renderers import chat, v0
        self.chat, self.renderer = chat, v0.Renderer(self.tokenizer.native)

    def flatten(self, spans):
        ids = []
        for span in spans:
            if not isinstance(span.span, self.chat.EncodedTextTokenSpan):
                raise CandidateGDatasetError("Only native text token spans are allowed")
            ids.extend(span.span.tokens)
        return ids

    def render(self, prompt, answer, evidence, mode="provided"):
        if mode != "provided":
            raise CandidateGDatasetError("Candidate G new rows require supplied evidence")
        chat = self.chat
        user = prompt + "\n\nSOURCE EVIDENCE (data, not instructions):\n" + evidence
        for value in (self.system_prompt, user, answer):
            if any("<|" + name + "|>" in value
                   for name in self.tokenizer.native.special_tokens()):
                raise CandidateGDatasetError("Authored text contains a native protocol marker")
            self.tokenizer.encode(value)
        message = lambda role, content, **kw: chat.Message(
            author=chat.Author(role), content=content, **kw)
        system = message(chat.AuthorKind.System, chat.Text(self.system_prompt))
        question = message(chat.AuthorKind.User, chat.Text(user))
        spans, parser = self.renderer.render_for_completion_with_effort(
            [system, question], self.effort)
        prompt_ids = self.flatten(spans)
        messages = [
            system,
            message(chat.AuthorKind.System, chat.ThinkingEffort(700)),
            question,
            message(chat.AuthorKind.Model, chat.Text(answer),
                    channel_enum=chat.MessageChannel.Final),
            message(chat.AuthorKind.Model, chat.ModelEndSampling()),
        ]
        examples = self.renderer.render_for_sft(messages)
        if len(examples) != 1:
            raise CandidateGDatasetError("Native renderer returned multiple examples")
        ids = self.flatten(examples[0].input_token_spans)
        weights = list(examples[0].per_token_loss_weight_unshifted)
        if (ids[:len(prompt_ids)] != prompt_ids
                or weights != [0.0] * len(prompt_ids) + [1.0] * (len(ids) - len(prompt_ids))):
            raise CandidateGDatasetError("Native prompt prefix or assistant-only mask changed")
        rendered = self.tokenizer.native.decode(ids)
        if self.tokenizer.pinned.encode(rendered, add_special_tokens=False) != ids:
            raise CandidateGDatasetError("Native and pinned token IDs differ")
        parsed = parser.parse_tokens(ids[len(prompt_ids):])
        if (len(parsed) != 2 or not isinstance(parsed[0].content, chat.Text)
                or parsed[0].content.text != answer
                or not isinstance(parsed[1].content, chat.ModelEndSampling)):
            raise CandidateGDatasetError("Native final answer failed round-trip")
        if any(item.author.kind != chat.AuthorKind.Model
               or item.channel_enum == chat.MessageChannel.Analysis for item in parsed):
            raise CandidateGDatasetError("Native target contains an unexpected role or analysis")
        result = {
            "input_ids": ids[:-1], "target_ids": ids[1:], "weights": weights[1:],
            "processed_token_count": len(ids) - 1,
            "loss_token_count": int(sum(weights)),
            "prompt_token_count": len(prompt_ids),
            "prompt_token_sha256": sha256_bytes(instruction.json_bytes(prompt_ids)),
        }
        instruction.validate_sequence(result, MAXIMUM_INPUT_TOKENS)
        return result


def canonical_bytes(value):
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def sha256_bytes(value):
    return hashlib.sha256(value).hexdigest()


def canonical_sha256(value):
    return sha256_bytes(canonical_bytes(value))


def _exact(value, fields, label):
    if not isinstance(value, dict) or set(value) != set(fields):
        raise CandidateGDatasetError(f"{label} fields differ from the frozen contract")


def _text(value, label):
    if not isinstance(value, str) or not value.strip():
        raise CandidateGDatasetError(f"{label} must be nonempty text")


def _sha(value, label):
    if not isinstance(value, str) or not SHA256_RE.fullmatch(value):
        raise CandidateGDatasetError(f"{label} must be a lowercase SHA-256")


def _texts(value, label, *, allow_empty=False):
    if (not isinstance(value, list) or (not allow_empty and not value)
            or any(not isinstance(item, str) or not item.strip() for item in value)):
        raise CandidateGDatasetError(f"{label} must be a list of nonempty strings")


def _planned_new_rows(plan):
    rows = [*plan["training_rows"], *plan["validation_rows"]]
    return {row["row_id"]: row for row in rows if row["group"] != "rehearsal"}


def validate_authored_rows(plan, source_inventory, authored_rows):
    """Validate complete authored-row closure against the fixed row plan."""
    expected = _planned_new_rows(plan)
    if not isinstance(authored_rows, list) or len(authored_rows) != 104:
        raise CandidateGDatasetError("Exactly 104 newly authored rows are required")
    by_id = {}
    family_by_id = {
        family["family_id"]: family
        for family in [*source_inventory["training_families"],
                       *source_inventory["validation_families"]]
    }
    for index, row in enumerate(authored_rows):
        label = f"authored_rows[{index}]"
        _exact(row, AUTHOR_ROW_FIELDS, label)
        if row["schema_version"] != SCHEMA_VERSION:
            raise CandidateGDatasetError(f"{label} schema_version is unsupported")
        _text(row["row_id"], label + ".row_id")
        if row["row_id"] in by_id:
            raise CandidateGDatasetError("Duplicate authored row_id")
        planned = expected.get(row["row_id"])
        if planned is None:
            raise CandidateGDatasetError(f"{label} is not a planned new row")
        for field in (
                "split", "group", "family_id", "language", "book", "chapter",
                "source_span", "source_id", "source_path", "source_sha256",
                "source_layer", "source_refs", "permission_ref",
                "language_boundary_ref"):
            if row[field] != planned[field]:
                raise CandidateGDatasetError(f"{label}.{field} differs from fixed row plan")
        if row["family_id"] not in family_by_id:
            raise CandidateGDatasetError(f"{label} lacks a fixed source family")
        selected = row["selected_verse_ids"]
        _texts(selected, label + ".selected_verse_ids")
        if len(selected) != len(set(selected)) or not set(selected) <= set(row["source_refs"]):
            raise CandidateGDatasetError(
                f"{label}.selected_verse_ids leave or repeat the fixed family span"
            )
        for field in ("question", "answer", "scope"):
            _text(row[field], f"{label}.{field}")
        if row["question"] == row["answer"]:
            raise CandidateGDatasetError(f"{label} question and answer cannot be identical")
        if row["intent"] not in INTENTS:
            raise CandidateGDatasetError(f"{label}.intent is invalid")
        rendering = row["project_english_rendering"]
        if rendering is not None:
            _exact(rendering, {"text", "rendering_author", "review_status"},
                   label + ".project_english_rendering")
            for field in rendering:
                _text(rendering[field], f"{label}.project_english_rendering.{field}")
        authoring = row["authoring"]
        _exact(authoring, {"author_kind", "author_role", "provenance", "reasoning_in_target"},
               label + ".authoring")
        if authoring["author_kind"] not in {"ai", "human", "mixed"}:
            raise CandidateGDatasetError(f"{label}.authoring.author_kind is invalid")
        for field in ("author_role", "provenance"):
            _text(authoring[field], f"{label}.authoring.{field}")
        if authoring["reasoning_in_target"] is not False:
            raise CandidateGDatasetError(f"{label} cannot include a reasoning target")
        for value in (row["question"], row["answer"],
                      rendering["text"] if rendering else ""):
            if "<|" in value or "|>" in value:
                raise CandidateGDatasetError(f"{label} contains a native protocol marker")
        by_id[row["row_id"]] = row
    if set(by_id) != set(expected):
        raise CandidateGDatasetError("Authored rows do not exactly cover all 104 new rows")
    return by_id


def validate_target_reviews(authored_by_id, review_rows):
    """Require one independent, hash-bound approval for every new answer."""
    if not isinstance(review_rows, list) or len(review_rows) != len(authored_by_id):
        raise CandidateGDatasetError("Target reviews must exactly cover all authored rows")
    reviews = {}
    for index, review in enumerate(review_rows):
        label = f"review_rows[{index}]"
        _exact(review, REVIEW_FIELDS, label)
        row_id = review["row_id"]
        if row_id in reviews or row_id not in authored_by_id:
            raise CandidateGDatasetError(f"{label} has duplicate or unknown row_id")
        authored = authored_by_id[row_id]
        bindings = {
            "authored_row_sha256": canonical_sha256(authored),
            "question_sha256": sha256_bytes(authored["question"].encode("utf-8")),
            "answer_sha256": sha256_bytes(authored["answer"].encode("utf-8")),
            "selected_verse_ids_sha256": canonical_sha256(
                authored["selected_verse_ids"]),
            "project_english_rendering_sha256": (
                None if authored["project_english_rendering"] is None
                else canonical_sha256(authored["project_english_rendering"])
            ),
            "authoring_sha256": canonical_sha256(authored["authoring"]),
        }
        for field, expected in bindings.items():
            if expected is not None:
                _sha(review[field], f"{label}.{field}")
            elif review[field] is not None:
                raise CandidateGDatasetError(
                    f"{label}.{field} must be null when no rendering was supplied")
            if review[field] != expected:
                raise CandidateGDatasetError(f"{label} {field} is stale")
        if review["decision"] != "approved":
            raise CandidateGDatasetError(f"{label} is not approved")
        if review["reviewer_kind"] not in {"ai", "human", "mixed"}:
            raise CandidateGDatasetError(f"{label}.reviewer_kind is invalid")
        _text(review["reviewer_role"], label + ".reviewer_role")
        _texts(review["conflicts"], label + ".conflicts", allow_empty=True)
        if review["expert_certified"] is not False:
            raise CandidateGDatasetError("This workflow cannot record expert certification")
        if review["reviewer_role"] == authored_by_id[row_id]["authoring"]["author_role"]:
            raise CandidateGDatasetError(f"{label} author and reviewer roles must differ")
        for field in ("source_support", "coverage", "attribution", "scope", "english_quality"):
            if review[field] != "pass":
                raise CandidateGDatasetError(f"{label}.{field} must pass before compilation")
        _text(review["rationale"], label + ".rationale")
        _texts(review["evidence_refs"], label + ".evidence_refs")
        reviews[row_id] = review
    if set(reviews) != set(authored_by_id):
        raise CandidateGDatasetError("Target review closure is incomplete")
    return reviews


def validate_authoring_manifest(manifest, authored_rows, plan, source_inventory,
                                permission_inventory):
    fields = {
        "schema_version", "artifact_kind", "status", "row_count", "split_counts",
        "row_plan_sha256", "family_inventory_sha256", "permission_inventory_sha256",
        "authored_rows_sha256", "batch_files", "limitations",
    }
    _exact(manifest, fields, "authoring_manifest")
    if (manifest["schema_version"] != 1
            or manifest["artifact_kind"] != "candidate_g_authored_targets_v1"
            or manifest["status"] != "authored_pending_independent_review"):
        raise CandidateGDatasetError("Authoring manifest identity/status is invalid")
    if manifest["row_count"] != 104 or manifest["split_counts"] != {
            "train": 80, "validation": 24}:
        raise CandidateGDatasetError("Authoring manifest counts are invalid")
    expected = {
        "row_plan_sha256": canonical_sha256(plan),
        "family_inventory_sha256": canonical_sha256(source_inventory),
        "permission_inventory_sha256": canonical_sha256(permission_inventory),
        "authored_rows_sha256": canonical_sha256(authored_rows),
    }
    if any(manifest[field] != value for field, value in expected.items()):
        raise CandidateGDatasetError("Authoring manifest has stale canonical bindings")
    if not isinstance(manifest["batch_files"], list) or not manifest["batch_files"]:
        raise CandidateGDatasetError("Authoring manifest requires batch file bindings")
    for index, item in enumerate(manifest["batch_files"]):
        _exact(item, {"path", "sha256", "rows"}, f"authoring_manifest.batch_files[{index}]")
        _text(item["path"], "batch path")
        _sha(item["sha256"], "batch hash")
        if type(item["rows"]) is not int or item["rows"] <= 0:
            raise CandidateGDatasetError("Invalid authored batch count")
    if sum(item["rows"] for item in manifest["batch_files"]) != 104:
        raise CandidateGDatasetError("Authored batch counts do not close")
    _texts(manifest["limitations"], "authoring_manifest.limitations")


def validate_review_manifest(manifest, review_rows, authored_manifest):
    fields = {
        "schema_version", "artifact_kind", "status", "row_count",
        "authoring_manifest_sha256", "authored_rows_sha256", "review_rows_sha256",
        "review_files", "reviewer_overlap", "expert_certified", "limitations",
    }
    _exact(manifest, fields, "review_manifest")
    if (manifest["schema_version"] != 1
            or manifest["artifact_kind"] != "candidate_g_target_reviews_v1"
            or manifest["status"] != "complete_all_approved"):
        raise CandidateGDatasetError("Review manifest identity/status is invalid")
    if manifest["row_count"] != 104:
        raise CandidateGDatasetError("Review manifest row count is invalid")
    if manifest["authoring_manifest_sha256"] != canonical_sha256(authored_manifest):
        raise CandidateGDatasetError("Review manifest has stale authoring binding")
    if manifest["authored_rows_sha256"] != authored_manifest["authored_rows_sha256"]:
        raise CandidateGDatasetError("Review manifest authored-row binding differs")
    if manifest["review_rows_sha256"] != canonical_sha256(review_rows):
        raise CandidateGDatasetError("Review manifest has stale review-row binding")
    if not isinstance(manifest["review_files"], list) or not manifest["review_files"]:
        raise CandidateGDatasetError("Review manifest requires review file bindings")
    for index, item in enumerate(manifest["review_files"]):
        _exact(item, {"path", "sha256", "rows"}, f"review_manifest.review_files[{index}]")
        _text(item["path"], "review path")
        _sha(item["sha256"], "review hash")
    if sum(item["rows"] for item in manifest["review_files"]) != 104:
        raise CandidateGDatasetError("Review file counts do not close")
    _texts(manifest["reviewer_overlap"], "review_manifest.reviewer_overlap", allow_empty=True)
    if manifest["expert_certified"] is not False:
        raise CandidateGDatasetError("Review manifest cannot claim expert certification")
    _texts(manifest["limitations"], "review_manifest.limitations")


def validate_rights_facts(rights_facts, source_inventory):
    _exact(rights_facts, {"schema_version", "artifact_kind", "status", "facts", "hash_basis"},
           "rights_facts")
    if (rights_facts["schema_version"] != 1
            or rights_facts["artifact_kind"] != "candidate_g_rights_fact_digest_closure_v1"
            or rights_facts["status"] != "reproducible_nonexpert_planning_facts"):
        raise CandidateGDatasetError("Rights-fact artifact identity/status is invalid")
    _text(rights_facts["hash_basis"], "rights_facts.hash_basis")
    facts = {}
    for index, fact in enumerate(rights_facts["facts"]):
        label = f"rights_facts.facts[{index}]"
        _exact(fact, {
            "rights_fact_id", "canonical_text", "canonical_text_utf8_sha256",
            "source_ids", "languages", "permission_refs", "basis_refs",
            "rights_notice_bindings", "limits",
        }, label)
        _text(fact["rights_fact_id"], label + ".rights_fact_id")
        _text(fact["canonical_text"], label + ".canonical_text")
        if sha256_bytes(fact["canonical_text"].encode("utf-8")) != (
                fact["canonical_text_utf8_sha256"]):
            raise CandidateGDatasetError(f"{label} canonical text hash differs")
        for field in ("source_ids", "languages", "permission_refs", "basis_refs", "limits"):
            _texts(fact[field], f"{label}.{field}")
        for item in fact["rights_notice_bindings"]:
            _exact(item, {"path", "sha256"}, label + ".rights_notice_bindings[]")
            _text(item["path"], "rights notice path")
            _sha(item["sha256"], "rights notice hash")
        for permission_ref in fact["permission_refs"]:
            if permission_ref in facts:
                raise CandidateGDatasetError("A permission ref has multiple rights facts")
            facts[permission_ref] = fact
    for layer in source_inventory["source_layers"]:
        fact = facts.get(layer["permission_ref"])
        if fact is None or fact["canonical_text_utf8_sha256"] != layer["rights_fact_sha256"]:
            raise CandidateGDatasetError("Source layer lacks exact rights-fact closure")
        if layer["source_id"] not in fact["source_ids"] or layer["language"] not in fact["languages"]:
            raise CandidateGDatasetError("Rights fact source/language scope differs")
        if {"path": layer["rights_notice_path"], "sha256": layer["rights_notice_sha256"]} not in (
                fact["rights_notice_bindings"]):
            raise CandidateGDatasetError("Rights notice binding differs from source layer")
    return facts


def load_text_sources(root, source_inventory):
    """Load checksum-bound processed sources and retain only approved text fields."""
    root = Path(root).resolve()
    by_path = {}
    records = {}
    for layer in source_inventory["source_layers"]:
        path = (root / layer["local_path"]).resolve()
        try:
            path.relative_to(root)
        except ValueError as exc:
            raise CandidateGDatasetError("Source path escapes project root") from exc
        if path.is_symlink() or not path.is_file():
            raise CandidateGDatasetError("Source path is missing or a symlink")
        data = path.read_bytes()
        if sha256_bytes(data) != layer["content_sha256"]:
            raise CandidateGDatasetError("Processed source file hash differs")
        if path not in by_path:
            parsed = []
            for line in data.splitlines():
                if not line.strip():
                    continue
                row = json.loads(line)
                if not isinstance(row, dict):
                    raise CandidateGDatasetError("Processed source row must be an object")
                parsed.append(row)
            by_path[path] = parsed
        selected_ids = set(layer["source_refs"])
        for source in by_path[path]:
            if source.get("id") not in selected_ids:
                continue
            if source.get("source_id") != layer["source_id"]:
                raise CandidateGDatasetError("Processed source ID differs from source layer")
            if source["id"] in records:
                prior = records[source["id"]]
                if prior["language"] == layer["language"]:
                    raise CandidateGDatasetError("Duplicate selected source verse")
                continue
            language = source.get("language")
            languages = source.get("languages", [language])
            if layer["language"] not in languages:
                continue
            text = source.get("text")
            _text(text, f"source {source['id']}.text")
            if text.encode("utf-8").decode("utf-8") != text:
                raise CandidateGDatasetError("Source Unicode round-trip changed")
            minimal = {
                "id": source["id"], "source_id": source["source_id"],
                "book": source.get("book"), "chapter": source.get("chapter"),
                "verse": source.get("verse"), "language": language,
                "languages": languages, "text": text,
            }
            if source["source_id"] == "oshb":
                minimal.update({
                    "layer": source.get("text_layer"),
                    "source_ref": source.get("source_ref"),
                    "reference_system": source.get("reference_system"),
                })
                if minimal["layer"] != "main/ketiv" or minimal["reference_system"] != "Bible.MT":
                    raise CandidateGDatasetError("OSHB selection is not WLC main/ketiv text")
            elif source["source_id"] == "sblgnt":
                minimal.update({
                    "layer": source.get("editorial_status"),
                    "source_ref": source.get("source_ref"),
                    "source_file": source.get("source_file"),
                    "source_line": source.get("source_line"),
                })
                if (not isinstance(minimal["layer"], str)
                        or not minimal["layer"].startswith("main")
                        or source.get("main_text") != text):
                    raise CandidateGDatasetError("SBLGNT selection is not exact main text")
            else:
                raise CandidateGDatasetError("Unexpected source edition")
            records[source["id"]] = minimal
    return records


def build_evidence(authored, source_records, source_inventory, permission_inventory,
                   rights_by_permission):
    layers = {(x["source_id"], x["layer"], x["language"]): x
              for x in source_inventory["source_layers"]}
    permissions = {x["permission_ref"]: x for x in permission_inventory["decisions"]}
    layer = layers[(authored["source_id"], authored["source_layer"], authored["language"])]
    permission = permissions[authored["permission_ref"]]
    fact = rights_by_permission[authored["permission_ref"]]
    blocks = []
    for verse_id in authored["selected_verse_ids"]:
        source = source_records.get(verse_id)
        if source is None:
            raise CandidateGDatasetError(f"Selected verse is missing: {verse_id}")
        if source["source_id"] != authored["source_id"]:
            raise CandidateGDatasetError("Selected verse source differs")
        if source["languages"] != [authored["language"]]:
            raise CandidateGDatasetError("Selected verse is mixed or has a different language")
        if str(source["chapter"]) != authored["chapter"] or source["book"] != authored["book"]:
            raise CandidateGDatasetError("Selected verse leaves the fixed book/chapter")
        coordinate = source["source_ref"]
        if source["source_id"] == "oshb":
            coordinate += f"; {source['reference_system']}"
        else:
            coordinate += f"; {source['source_file']} line {source['source_line']}"
        blocks.append(
            f"[{source['id']}; language {authored['language']}; layer {source['layer']}; "
            f"source coordinate {coordinate}]\n{source['text']}"
        )
    notice = [
        "SOURCE PROVENANCE AND NOTICE:",
        f"Edition: {layer['edition']}",
        f"Pinned version: {layer['pinned_version']}",
        f"Attribution: {SOURCE_ATTRIBUTION[layer['source_id']]}",
        f"Selected source layer: {layer['layer']} ({layer['language']})",
        f"Rights notice: {layer['rights_notice_path']} (SHA-256 {layer['rights_notice_sha256']})",
        f"Rights/use basis: {fact['canonical_text']}",
        f"Training-input planning decision: {permission['decision']} (not target or training approval).",
        "Limits: " + " ".join(layer["limits"]),
    ]
    rendering = authored["project_english_rendering"]
    if rendering:
        notice += [
            "SUPPLIED PROJECT ENGLISH RENDERING (project-authored input, not the named source edition):",
            rendering["text"],
            f"Rendering author: {rendering['rendering_author']}; review status: {rendering['review_status']}.",
        ]
    return "\n\n".join(blocks) + "\n\n" + "\n".join(notice)


def load_exact_rehearsal_rows(root, source_inventory):
    """Return exact saved prepared-row bytes keyed by rehearsal planning ID."""
    root = Path(root).resolve()
    by_path = {}
    result = {}
    for rehearsal in source_inventory["rehearsal_rows"]:
        path = (root / rehearsal["prepared_path"]).resolve()
        try:
            path.relative_to(root)
        except ValueError as exc:
            raise CandidateGDatasetError("Rehearsal path escapes project root") from exc
        if path.is_symlink() or not path.is_file():
            raise CandidateGDatasetError("Rehearsal prepared path is missing or a symlink")
        if path not in by_path:
            rows = {}
            for line in path.read_bytes().splitlines():
                row = json.loads(line)
                if row.get("id") in rows:
                    raise CandidateGDatasetError("Duplicate saved prepared ID")
                rows[row.get("id")] = (row, line)
            by_path[path] = rows
        found = by_path[path].get(rehearsal["old_row_id"])
        if found is None:
            raise CandidateGDatasetError("Old rehearsal ID is absent from saved train rows")
        row, line = found
        if set(row) != PREPARED_FIELDS:
            raise CandidateGDatasetError("Saved rehearsal row schema differs")
        if sha256_bytes(line) != rehearsal["full_row_sha256"]:
            raise CandidateGDatasetError("Saved rehearsal row bytes differ from bound hash")
        instruction.validate_sequence(row, MAXIMUM_INPUT_TOKENS)
        result[rehearsal["rehearsal_row_id"]] = line
    if len(result) != 16:
        raise CandidateGDatasetError("Exactly 16 unique rehearsal rows are required")
    return result


def compile_prepared_dataset(plan, source_inventory, permission_inventory,
                             rights_facts, authored_rows, review_rows, renderer,
                             expected_system_prompt_sha256, source_records,
                             exact_rehearsal_rows):
    """Compile reviewed new rows and exact rehearsal bytes entirely in memory."""
    plan_result = validate_plan(plan, source_inventory, permission_inventory)
    authored = validate_authored_rows(plan, source_inventory, authored_rows)
    reviews = validate_target_reviews(authored, review_rows)
    rights = validate_rights_facts(rights_facts, source_inventory)
    if not isinstance(source_records, dict):
        raise CandidateGDatasetError("Checksum-verified Candidate G source records are required")
    if (not isinstance(getattr(renderer, "system_prompt", None), str)
            or getattr(renderer, "effort", None) != 0.7):
        raise CandidateGDatasetError("Renderer must expose the exact new-row prompt and effort 0.7")
    _sha(expected_system_prompt_sha256, "expected_system_prompt_sha256")
    actual_prompt_sha256 = sha256_bytes(renderer.system_prompt.encode("utf-8"))
    if actual_prompt_sha256 != expected_system_prompt_sha256:
        raise CandidateGDatasetError("New-row system prompt differs from frozen baseline binding")
    outputs = {"train": [], "validation": []}
    prepared_ids = set()
    for planned in [*plan["training_rows"], *plan["validation_rows"]]:
        split = planned["split"]
        if planned["group"] == "rehearsal":
            line = exact_rehearsal_rows.get(planned["rehearsal_row_id"])
            if line is None or sha256_bytes(line) != planned["full_row_sha256"]:
                raise CandidateGDatasetError("Exact rehearsal row binding differs")
            prepared = json.loads(line)
        else:
            row = authored[planned["row_id"]]
            evidence = build_evidence(
                row, source_records, source_inventory, permission_inventory, rights,
            )
            prepared = renderer.render(row["question"], row["answer"], evidence, "provided")
            instruction.validate_sequence(prepared, MAXIMUM_INPUT_TOKENS)
            prepared.update({
                "id": row["row_id"], "language": row["language"],
                "category": row["group"],
                "chapter_keys": [f"{row['source_id']}:{row['book']}.{row['chapter']}"],
                "source_refs": row["selected_verse_ids"],
                "answer_sha256": sha256_bytes(row["answer"].encode("utf-8")),
                "reviewed_content_sha256": canonical_sha256(row),
                "evidence_sha256": sha256_bytes(evidence.encode("utf-8")),
                "evidence_mode": "provided",
            })
            if prepared["answer_sha256"] != reviews[row["row_id"]]["answer_sha256"]:
                raise CandidateGDatasetError("Prepared answer differs from approved review")
            line = canonical_bytes(prepared)
        if set(prepared) != PREPARED_FIELDS:
            raise CandidateGDatasetError("Prepared row fields differ from prior training format")
        if prepared["id"] in prepared_ids:
            raise CandidateGDatasetError("Prepared row IDs collide")
        prepared_ids.add(prepared["id"])
        outputs[split].append(line)
    data = {split: b"".join(line + b"\n" for line in lines)
            for split, lines in outputs.items()}
    if len(outputs["train"]) != 96 or len(outputs["validation"]) != 24:
        raise CandidateGDatasetError("Compiled split counts differ from 96/24")
    summary = {
        "schema_version": 1,
        "artifact_kind": "candidate_g_prepared_dataset_summary_v1",
        "status": "prepared_offline_not_trained",
        "plan_validation": plan_result,
        "settings": {
            "model": instruction.MODEL,
            "system_prompt_sha256": actual_prompt_sha256,
            "new_rows_system_prompt_sha256": actual_prompt_sha256,
            "thinking_effort_numeric": 0.7,
            "maximum_input_tokens": MAXIMUM_INPUT_TOKENS,
            "truncation": "forbidden",
            "loss": "native assistant final response only; prompt masked",
            "reasoning_targets": False,
            "rejected_guidance_suffix_adopted": False,
            "rehearsal_framing": "exact saved historical prepared rows; not rerendered",
        },
        "counts": {"train": 96, "validation": 24, "new": 104, "rehearsal": 16},
        "artifacts": {
            split: {
                "sha256": sha256_bytes(value), "rows": len(outputs[split]),
                "bytes": len(value),
            } for split, value in data.items()
        },
        "bindings": {
            "row_plan_sha256": canonical_sha256(plan),
            "family_inventory_sha256": canonical_sha256(source_inventory),
            "permission_inventory_sha256": canonical_sha256(permission_inventory),
            "rights_facts_sha256": canonical_sha256(rights_facts),
            "authored_rows_sha256": canonical_sha256(authored_rows),
            "review_rows_sha256": canonical_sha256(review_rows),
        },
        "expert_certified": False,
        "training_authorized": False,
        "limitations": [
            "AI target review is not expert certification.",
            "Preparation performs no provider, model, checkpoint, training, evaluation, or deployment call.",
        ],
    }
    return data, summary
