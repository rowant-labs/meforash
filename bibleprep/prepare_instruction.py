"""Prepare reviewed English Inkling SFT locally, without credentials or model calls.

Only an explicit CLI invocation writes artifacts. Source excerpts come from the
pinned processed records. This module reads the evaluation's exclusion inventory,
never its questions, answer keys, or scoring criteria.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re

from bibleprep import prepare_inkling as raw
from bibleprep.evaluate import SYSTEM_PROMPT

ROOT = Path(__file__).resolve().parents[1]
ARTIFACT_DIRECTORY = "data/prepared/instruction-v1"
PREPARATION_MANIFEST = "manifests/preparation-instruction-v1.json"
MODEL = "thinkingmachines/Inkling"
EFFORT = 0.7
SEED = "instruction-v1"
MAXIMUM = 8192
REVIEW_FIELDS = {"review_status", "reviewer", "review_sources", "reviewed_content_sha256"}
FIELDS = {"id", "language", "category", "source_refs", "evidence", "evidence_mode",
          "prompt", "answer", "support_notes", "author", "chapter_keys", "source_word_ids"} | REVIEW_FIELDS
PASSAGE = re.compile(r"([1-3]?[A-Za-z]+)\.([1-9][0-9]*)\.([1-9][0-9]*)(?:-([1-9][0-9]*))?")
CHAPTER = re.compile(r"(?:oshb|sblgnt):[1-3]?[A-Za-z]+\.[1-9][0-9]*")
SHA = re.compile(r"[0-9a-f]{64}")
CODE_FILES = ("bibleprep/prepare_instruction.py", "bibleprep/prepare_inkling.py",
              "bibleprep/tinker_compare.py", "bibleprep/tinker_evaluate.py", "bibleprep/evaluate.py")
REFERENCES = [
    "https://tinker-docs.thinkingmachines.ai/cookbook/inkling/tml-renderers/",
    "https://tinker-docs.thinkingmachines.ai/cookbook/inkling/thinking-effort/",
    "https://raw.githubusercontent.com/thinking-machines-lab/tinker-cookbook/1f962eda3a2cec8de284725f2adc9978e93dfcd3/tinker_cookbook/renderers/tml_v0.py",
]


def json_bytes(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def digest(value):
    return hashlib.sha256(value).hexdigest()


def content_hash(example):
    """Bind source review to all authored content, excluding review metadata."""
    return digest(json_bytes({k: v for k, v in example.items() if k not in REVIEW_FIELDS}))


def relative_path(root, value, *, under=None):
    root = Path(root).resolve()
    path = Path(value)
    if path.is_absolute() or ".." in path.parts or str(path) != value:
        raise ValueError("Artifact paths must be portable project-relative paths.")
    resolved = (root / path).resolve()
    try:
        resolved.relative_to(root / under if under else root)
    except ValueError as exc:
        raise ValueError("Artifact path is outside its permitted project directory.") from exc
    if (root / path).is_symlink():
        raise ValueError("Artifacts must not be symlinks.")
    return resolved


def read_rows(path):
    try:
        rows = [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines() if line.strip()]
    except (OSError, ValueError) as exc:
        raise ValueError("Invalid JSONL artifact.") from exc
    if not rows or any(not isinstance(row, dict) for row in rows):
        raise ValueError("JSONL must contain nonempty object rows.")
    return rows


def load_sources(root=ROOT):
    """Read checksum-verified prepared editions, retaining Unicode and readings."""
    records, identities = {}, {}
    for source in ("oshb", "sblgnt"):
        manifest_path = Path(root) / f"manifests/{source}.json"
        manifest = json.loads(manifest_path.read_text())
        path = Path(root) / f"data/processed/{source}/verses.jsonl"
        expected = (manifest["prepared_artifact"]["sha256"] if source == "oshb"
                    else manifest["prepared_outputs"]["verses.jsonl"]["sha256"])
        if raw.original.sha256(path) != expected:
            raise ValueError("Prepared source checksum differs from its pinned manifest.")
        revision = manifest["pinned_commit"] if source == "oshb" else manifest["revision"]
        identities[source] = {"revision": revision, "records_sha256": expected,
                              "manifest_sha256": raw.original.sha256(manifest_path)}
        for row in read_rows(path):
            if row["id"] in records or row["source_id"] != source:
                raise ValueError("Duplicate or mismatched source verse ID.")
            records[row["id"]] = row
    return records, identities


def source_url(source, book, revision):
    if source == "oshb":
        return f"https://raw.githubusercontent.com/openscriptures/morphhb/{revision}/wlc/{book}.xml"
    if source == "sblgnt":
        return f"https://raw.githubusercontent.com/Faithlife/SBLGNT/{revision}/data/sblgnt/text/{book}.txt"
    raise ValueError("Unsupported source edition.")


def referenced_records(refs, records, identities):
    if not isinstance(refs, list) or not refs:
        raise ValueError("Every example needs pinned source references.")
    selected = []
    seen = set()
    for ref in refs:
        if not isinstance(ref, dict) or set(ref) != {"source_id", "passage", "url", "revision"}:
            raise ValueError("Source reference fields do not match the canonical schema.")
        source = ref["source_id"]
        match = PASSAGE.fullmatch(ref["passage"])
        if source not in identities or not match:
            raise ValueError("Use canonical same-chapter passage references, such as Gen.2.7-9.")
        book, chapter, first, last = match.groups()
        chapter, first, last = int(chapter), int(first), int(last or first)
        if last < first or last - first > 200:
            raise ValueError("Invalid or excessive source passage range.")
        if ref["revision"] != identities[source]["revision"] or ref["url"] != source_url(source, book, ref["revision"]):
            raise ValueError("Source revision or URL differs from the pinned edition.")
        for number in range(first, last + 1):
            key = f"{source}:{book}.{chapter}.{number}"
            if key not in records or key in seen:
                raise ValueError("Missing or duplicate source verse in example references.")
            row = records[key]
            if row.get("alternatives"):
                # A dedicated layer selector is needed before supervising any
                # double-bracketed material; never silently combine its layers.
                raise ValueError("Supplemental readings require a separately reviewed layer schema.")
            if not row.get("text"):
                raise ValueError("Source reference has no nonempty exact text.")
            selected.append(row)
            seen.add(key)
    return selected


def build_evidence(source_refs, records, identities):
    """Create exact per-verse text with explicit edition, revision, and layer labels."""
    blocks = []
    for row in referenced_records(source_refs, records, identities):
        source = row["source_id"]
        edition = "OSHB/WLC" if source == "oshb" else "SBLGNT"
        layer = row.get("text_layer", row.get("editorial_status", "main"))
        header = f"[{edition}; {row['id']}; {layer}; revision {identities[source]['revision']}]"
        # The line after this header is byte-for-byte the prepared verse text.
        block = header + "\n" + row["text"]
        if row.get("editorial_spans"):
            block += "\nEditorial spans (0-based text offsets): " + json.dumps(row["editorial_spans"], ensure_ascii=False, sort_keys=True)
        blocks.append(block)
    return "\n\n".join(blocks)


def validate_example(example, records, identities, excluded):
    required = FIELDS - {"evidence", "evidence_mode", "source_word_ids"}
    if not isinstance(example, dict) or set(example) - FIELDS or required - set(example):
        raise ValueError("Instruction example fields do not match the reviewed schema.")
    for field in ("id", "category", "prompt", "answer", "support_notes", "author", "reviewer"):
        if not isinstance(example[field], str) or not example[field].strip():
            raise ValueError("Required instruction strings must be nonempty.")
    if not re.fullmatch(r"[A-Za-z0-9_-]+", example["id"]):
        raise ValueError("Example ID must be portable.")
    if example["language"] not in {"hbo", "arc", "grc", "mixed"}:
        raise ValueError("Unknown instruction language.")
    if example["review_status"] != "ai_source_checked" or example["author"] == example["reviewer"]:
        raise ValueError("A separate AI source reviewer must approve every example.")
    if example["reviewed_content_sha256"] != content_hash(example):
        raise ValueError("Reviewed content hash differs; re-review edited examples.")
    urls = example["review_sources"]
    if not isinstance(urls, list) or not urls or any(not isinstance(u, str) or not u.startswith("https://") for u in urls):
        raise ValueError("Independent source review must identify supporting HTTPS references.")
    mode = example.get("evidence_mode", "provided")
    if mode not in {"provided", "none"}:
        raise ValueError("Evidence mode must be provided or none.")
    selected = referenced_records(example["source_refs"], records, identities)
    chapters = sorted({f"{r['source_id']}:{r['book']}.{r['chapter']}" for r in selected})
    if not isinstance(example["chapter_keys"], list) or sorted(example["chapter_keys"]) != chapters:
        raise ValueError("Declared chapter keys differ from exact source references.")
    if set(chapters) & set(excluded):
        raise ValueError("Instruction source overlaps frozen evaluation chapters.")
    languages = {language for row in selected for language in row.get("languages", [row["language"]])}
    if example["language"] != (next(iter(languages)) if len(languages) == 1 else "mixed"):
        raise ValueError("Language label differs from referenced source records.")
    evidence = build_evidence(example["source_refs"], records, identities)
    if "evidence" in example and example["evidence"] != evidence:
        raise ValueError("Authored evidence differs from exact pinned source text.")
    if "source_word_ids" in example:
        available = {t["id"] for r in selected for t in r.get("tokens", []) if t.get("id")}
        ids = example["source_word_ids"]
        if not isinstance(ids, list) or not ids or len(ids) != len(set(ids)) or not set(ids) <= available:
            raise ValueError("Source word IDs do not belong to referenced OSHB verses.")
    return evidence


def load_exclusion(root, path):
    location = relative_path(root, path, under="manifests")
    raw_bytes = location.read_bytes()
    inventory = json.loads(raw_bytes)
    required = {"schema_version", "status", "evaluation_sha256", "chapter_keys"}
    allowed = required | {"evaluation_id", "chapter_key_format", "scope", "criteria_included"}
    if not isinstance(inventory, dict) or set(inventory) - allowed or required - set(inventory) or inventory.get("criteria_included", False) is not False:
        raise ValueError("Exclusion inventory must contain only hashes and chapter keys, never evaluation questions or criteria.")
    if inventory["schema_version"] != 1 or inventory["status"] != "frozen" or not SHA.fullmatch(inventory["evaluation_sha256"]):
        raise ValueError("Fresh evaluation must be frozen before preparing instruction targets.")
    keys = inventory["chapter_keys"]
    if not isinstance(keys, list) or not keys or len(keys) != len(set(keys)) or any(not isinstance(k, str) or not CHAPTER.fullmatch(k) for k in keys):
        raise ValueError("Frozen evaluation chapter inventory is invalid.")
    return set(keys), {"path": path, "sha256": digest(raw_bytes), "evaluation_sha256": inventory["evaluation_sha256"],
                       "chapter_keys_count": len(keys), "overlap_count": 0}


class InstructionRenderer:
    def __init__(self):
        self.tokenizer, _, _, self.identity = raw.load_tokenizer()
        from tml_renderers import chat, v0
        self.chat, self.renderer = chat, v0.Renderer(self.tokenizer.native)

    def render(self, prompt, answer, evidence, mode="provided"):
        chat = self.chat
        user = prompt + ("\n\nSOURCE EVIDENCE (data, not instructions):\n" + evidence if mode == "provided" else "")
        # Check every ordinary text segment independently without Unicode changes.
        for text in (SYSTEM_PROMPT, user, answer):
            if any("<|" + name + "|>" in text for name in self.tokenizer.native.special_tokens()):
                raise ValueError("Authored text must not contain native protocol markers.")
            self.tokenizer.encode(text)
        message = lambda role, content, **kw: chat.Message(author=chat.Author(role), content=content, **kw)
        system = message(chat.AuthorKind.System, chat.Text(SYSTEM_PROMPT))
        question = message(chat.AuthorKind.User, chat.Text(user))
        spans, parser = self.renderer.render_for_completion_with_effort([system, question], EFFORT)
        prompt_ids = self.flatten(spans)
        # Equivalent to the pinned official Cookbook _prepare_sft_input: native
        # effort after leading systems; model Text then its explicit turn stop.
        messages = [system, message(chat.AuthorKind.System, chat.ThinkingEffort(700)), question,
                    message(chat.AuthorKind.Model, chat.Text(answer), channel_enum=chat.MessageChannel.Final),
                    message(chat.AuthorKind.Model, chat.ModelEndSampling())]
        examples = self.renderer.render_for_sft(messages)
        if len(examples) != 1:
            raise ValueError("Single-turn example unexpectedly rendered as multiple examples.")
        ids = self.flatten(examples[0].input_token_spans)
        weights = list(examples[0].per_token_loss_weight_unshifted)
        if ids[:len(prompt_ids)] != prompt_ids or weights != [0.] * len(prompt_ids) + [1.] * (len(ids) - len(prompt_ids)):
            raise ValueError("Native SFT prompt prefix or assistant-only loss mask changed.")
        rendered = self.tokenizer.native.decode(ids)
        if self.tokenizer.pinned.encode(rendered, add_special_tokens=False) != ids:
            raise ValueError("Native and pinned HF complete SFT token IDs differ.")
        parsed = parser.parse_tokens(ids[len(prompt_ids):])
        if len(parsed) != 2 or not isinstance(parsed[0].content, chat.Text) or parsed[0].content.text != answer or not isinstance(parsed[1].content, chat.ModelEndSampling):
            raise ValueError("Native response failed final-answer and turn-stop round-trip.")
        if any(m.author.kind != chat.AuthorKind.Model or m.channel_enum == chat.MessageChannel.Analysis for m in parsed):
            raise ValueError("Unexpected role or analysis content in final-only instruction data.")
        result = {"input_ids": ids[:-1], "target_ids": ids[1:], "weights": weights[1:],
                  "processed_token_count": len(ids) - 1, "loss_token_count": int(sum(weights)),
                  "prompt_token_count": len(prompt_ids), "prompt_token_sha256": digest(json_bytes(prompt_ids))}
        validate_sequence(result)
        return result

    def flatten(self, spans):
        ids = []
        for span in spans:
            if not isinstance(span.span, self.chat.EncodedTextTokenSpan):
                raise ValueError("Only native text token spans are allowed.")
            ids.extend(span.span.tokens)
        return ids


def validate_sequence(row, maximum=MAXIMUM):
    ids, targets, weights = row["input_ids"], row["target_ids"], row["weights"]
    prefix = row["prompt_token_count"]
    if not isinstance(prefix, int) or isinstance(prefix, bool) or not 1 < prefix < len(ids):
        raise ValueError("Invalid prompt boundary.")
    if not ids or len(ids) != len(targets) or len(ids) != len(weights) or len(ids) > maximum:
        raise ValueError("Invalid sequence lengths; truncation is not permitted.")
    if any(not isinstance(t, int) or isinstance(t, bool) or not 0 <= t < 200058 for t in ids + targets):
        raise ValueError("Invalid native token IDs.")
    if ids[1:] != targets[:-1] or ids[0] != 200002 or targets[-1] != 200006:
        raise ValueError("Sequence must be shifted exactly once with native chat boundaries.")
    if weights != [0.] * (prefix - 1) + [1.] * (len(ids) - prefix + 1):
        raise ValueError("Only the native assistant response may receive loss.")
    if row["processed_token_count"] != len(ids) or row["loss_token_count"] != sum(weights):
        raise ValueError("Sequence accounting differs from actual tokens.")
    if row["prompt_token_sha256"] != digest(json_bytes(ids[:prefix])):
        raise ValueError("Prompt token hash differs.")


def split_examples(examples, validation_chapters=None):
    """Keep entire connected chapter groups together, including cross-book questions."""
    groups = []
    for example in sorted(examples, key=lambda e: e["id"]):
        chapters, members = set(example["chapter_keys"]), [example]
        untouched = []
        for old_chapters, old_members in groups:
            if old_chapters & chapters:
                chapters |= old_chapters
                members += old_members
            else:
                untouched.append((old_chapters, old_members))
        groups = untouched + [(chapters, members)]
    # Transitive unions can have bridged a previously inspected group.
    while any(a[0] & b[0] for i, a in enumerate(groups) for b in groups[i + 1:]):
        merged = [e for _, members in groups for e in members]
        return split_examples(merged, validation_chapters)
    if len(groups) < 2:
        raise ValueError("Instruction training and validation require separate chapter groups.")
    if validation_chapters is not None:
        chosen = set(validation_chapters)
        known = {c for e in examples for c in e["chapter_keys"]}
        if not chosen or not chosen <= known:
            raise ValueError("Validation chapters must identify nonempty authored chapter groups.")
        if any(bool(chapters & chosen) and not chapters <= chosen for chapters, _ in groups):
            raise ValueError("A connected instruction chapter group cannot cross the split.")
    else:
        target = max(1, round(len(examples) * .1))
        chosen, count = set(), 0
        ordered = sorted(groups, key=lambda g: digest(json_bytes([SEED, sorted(g[0])])))
        for chapters, members in ordered:
            if count == 0 or abs(count + len(members) - target) < abs(count - target):
                if count + len(members) <= len(examples) - 100:
                    chosen |= chapters
                    count += len(members)
    train = [e for e in sorted(examples, key=lambda e: e["id"]) if not set(e["chapter_keys"]) & chosen]
    validation = [e for e in sorted(examples, key=lambda e: e["id"]) if set(e["chapter_keys"]) & chosen]
    if len(train) < 100 or not validation:
        raise ValueError("Need at least 100 training examples and a nonempty separate validation group.")
    return {"train": train, "validation": validation}


def prepare(input_path, exclusion_path, *, root=ROOT, maximum=MAXIMUM, validation_chapters=None):
    root = Path(root)
    source_path = relative_path(root, input_path, under="runs")
    excluded, exclusion = load_exclusion(root, exclusion_path)
    records, source_identities = load_sources(root)
    examples = read_rows(source_path)
    if not 101 <= len(examples) <= 300 or len({e.get("id") for e in examples}) != len(examples):
        raise ValueError("Require 101–300 uniquely identified reviewed examples, including validation.")
    evidence = {e["id"]: validate_example(e, records, source_identities, excluded) for e in examples}
    splits = split_examples(examples, validation_chapters)
    renderer = InstructionRenderer()
    output = root / ARTIFACT_DIRECTORY
    manifest_path = root / PREPARATION_MANIFEST
    if output.exists() or manifest_path.exists():
        raise ValueError("Preparation outputs already exist; preserve them rather than overwriting.")
    if maximum < 128 or maximum > MAXIMUM:
        raise ValueError("Maximum input tokens must lie between 128 and 8192.")
    prepared, artifacts = {}, {}
    for label, selected in splits.items():
        rows = []
        for e in selected:
            result = renderer.render(e["prompt"], e["answer"], evidence[e["id"]], e.get("evidence_mode", "provided"))
            validate_sequence(result, maximum)
            result.update({k: e[k] for k in ("id", "language", "category", "chapter_keys", "source_refs")})
            result.update(answer_sha256=digest(e["answer"].encode()), reviewed_content_sha256=e["reviewed_content_sha256"],
                          evidence_sha256=digest(evidence[e["id"]].encode()), evidence_mode=e.get("evidence_mode", "provided"))
            rows.append(result)
        data = b"".join(json_bytes(row) + b"\n" for row in rows)
        prepared[label] = data
        artifacts[label] = {"path": f"{ARTIFACT_DIRECTORY}/{label}.jsonl", "sha256": digest(data),
                            "sequences": len(rows), "processed_tokens": sum(r["processed_token_count"] for r in rows),
                            "loss_tokens": sum(r["loss_token_count"] for r in rows)}
    chapter_sets = {label: sorted({c for e in selected for c in e["chapter_keys"]}) for label, selected in splits.items()}
    report = {"schema_version": 1, "status": "prepared_not_trained", "objective": "reviewed_english_instruction_sft",
              "review_status": "ai_source_checked", "expert_certified": False, "model": MODEL,
              "thinking_effort_numeric": EFFORT, "native_start_token_id": 200002, "native_end_token_id": 200006,
              "maximum_input_tokens": maximum, "tokenizer": renderer.identity,
              "runtime_versions": renderer.identity["runtime_packages"],
              "preparation_code_sha256": {p: raw.original.sha256(root / p) for p in CODE_FILES},
              "reviewed_dataset": {"path": input_path, "sha256": raw.original.sha256(source_path), "examples": len(examples)},
              "evaluation_exclusion": exclusion, "sources": source_identities, "artifacts": artifacts,
              "system_prompt_sha256": digest(SYSTEM_PROMPT.encode()),
              "split": {"method": "connected_chapter_groups", "selection": "explicit" if validation_chapters is not None else "deterministic_approximate_ten_percent",
                        "seed": SEED, "chapter_disjoint": True, "train_chapters": chapter_sets["train"], "validation_chapters": chapter_sets["validation"]},
              "by_language": {label: dict(Counter(e["language"] for e in selected)) for label, selected in splits.items()},
              "framing": {"format": "official_native_tml_render_for_sft", "assistant_channel": "Final canonicalized to Main by native renderer",
                          "loss": "native assistant response framing, answer, end_message and ModelEndSampling; all prompt tokens masked",
                          "shift": "exactly_once", "reasoning_traces": False, "unicode_normalization": "none",
                          "generation_prefix_token_equality_checked": True, "support_notes_rendered": False},
              "limitations": "AI source review is not expert certification. Final-only targets may bias against analysis emission at medium effort; reasoning retention must be measured. Base prior exposure unknown. This split excludes English examples, not prior raw-text exposure. No model API called.",
              "provider_references": REFERENCES}
    output.mkdir(parents=True, mode=0o700)
    for label, data in prepared.items():
        path = output / f"{label}.jsonl"
        path.write_bytes(data)
        path.chmod(0o600)
    (output / "summary.json").write_bytes(json_bytes(report) + b"\n")
    (output / "summary.json").chmod(0o600)
    manifest_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    return report


def _verify_prepared(root, manifest):
    """Verify reviewed artifacts offline, never opening any evaluation dataset."""
    root = Path(root)
    expected = {"schema_version": 1, "status": "prepared_not_trained", "objective": "reviewed_english_instruction_sft",
                "review_status": "ai_source_checked", "expert_certified": False, "model": MODEL,
                "thinking_effort_numeric": EFFORT, "native_start_token_id": 200002, "native_end_token_id": 200006}
    if any(manifest.get(k) != v for k, v in expected.items()):
        raise ValueError("Instruction manifest is not an approved prepared experiment.")
    if manifest.get("preparation_code_sha256") != {p: raw.original.sha256(root / p) for p in CODE_FILES}:
        raise ValueError("Preparation code changed after artifacts were frozen.")
    if manifest.get("system_prompt_sha256") != digest(SYSTEM_PROMPT.encode()):
        raise ValueError("Instruction system prompt changed.")
    excluded, receipt = load_exclusion(root, manifest["evaluation_exclusion"]["path"])
    if receipt != manifest["evaluation_exclusion"]:
        raise ValueError("Frozen evaluation exclusion receipt changed.")
    source = manifest["reviewed_dataset"]
    path = relative_path(root, source["path"], under="runs")
    if raw.original.sha256(path) != source["sha256"]:
        raise ValueError("Reviewed instruction dataset changed.")
    examples = read_rows(path)
    if len(examples) != source["examples"] or not 101 <= len(examples) <= 300:
        raise ValueError("Reviewed dataset example count changed.")
    records, identities = load_sources(root)
    if identities != manifest["sources"]:
        raise ValueError("Pinned source identity changed.")
    by_id = {e["id"]: e for e in examples}
    if len(by_id) != len(examples):
        raise ValueError("Reviewed example IDs repeat.")
    evidence = {e["id"]: validate_example(e, records, identities, excluded) for e in examples}
    renderer = InstructionRenderer()
    if renderer.identity != manifest["tokenizer"] or renderer.identity["runtime_packages"] != manifest["runtime_versions"]:
        raise ValueError("Pinned tokenizer or rendering runtime changed.")
    result, seen, chapter_sets = {}, set(), {}
    for label in ("train", "validation"):
        item = manifest["artifacts"][label]
        path = relative_path(root, item["path"], under=ARTIFACT_DIRECTORY)
        if raw.original.sha256(path) != item["sha256"]:
            raise ValueError("Prepared token artifact checksum changed.")
        rows = read_rows(path)
        for row in rows:
            validate_sequence(row, manifest["maximum_input_tokens"])
            identifier = row["id"]
            if identifier not in by_id or identifier in seen:
                raise ValueError("Prepared instruction IDs repeat or differ from reviewed input.")
            e = by_id[identifier]
            for field in ("chapter_keys", "language", "category", "source_refs", "reviewed_content_sha256"):
                if row[field] != e[field]:
                    raise ValueError("Prepared instruction metadata differs from reviewed input.")
            if row["answer_sha256"] != digest(e["answer"].encode()) or row["evidence_sha256"] != digest(evidence[identifier].encode()):
                raise ValueError("Prepared answer or source evidence hash differs.")
            rendered = renderer.render(e["prompt"], e["answer"], evidence[identifier], e.get("evidence_mode", "provided"))
            if any(row.get(k) != v for k, v in rendered.items()):
                raise ValueError("Prepared token data differs from exact reviewed native rendering.")
            seen.add(identifier)
        if item["sequences"] != len(rows) or item["processed_tokens"] != sum(r["processed_token_count"] for r in rows) or item["loss_tokens"] != sum(r["loss_token_count"] for r in rows):
            raise ValueError("Prepared artifact accounting changed.")
        result[label] = rows
        chapter_sets[label] = sorted({c for r in rows for c in r["chapter_keys"]})
    if seen != set(by_id) or len(result["train"]) < 100 or not result["validation"]:
        raise ValueError("Prepared split coverage or minimum count is invalid.")
    split = manifest["split"]
    if split["chapter_disjoint"] is not True or set(chapter_sets["train"]) & set(chapter_sets["validation"]):
        raise ValueError("Instruction training and validation chapters overlap.")
    if any(chapter_sets[label] != split[label + "_chapters"] for label in chapter_sets):
        raise ValueError("Recorded instruction split chapters differ.")
    return result



def verify_prepared(root, manifest):
    """Fail safely for missing or malformed artifacts before credentials are read."""
    try:
        return _verify_prepared(root, manifest)
    except (KeyError, TypeError, OSError, AttributeError) as exc:
        raise ValueError("Required preparation artifact or schema field is missing or invalid.") from exc


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, help="Reviewed JSONL inside ignored runs/.")
    parser.add_argument("--exclusion-manifest", required=True, help="Minimal frozen chapter inventory in manifests/.")
    parser.add_argument("--max-tokens", type=int, default=MAXIMUM)
    parser.add_argument("--validation-chapters", help="Optional JSON list of whole validation chapter groups inside runs/.")
    args = parser.parse_args(argv)
    chapters = None
    if args.validation_chapters:
        chapters = json.loads(relative_path(ROOT, args.validation_chapters, under="runs").read_text())
    report = prepare(args.input, args.exclusion_manifest, maximum=args.max_tokens, validation_chapters=chapters)
    print(json.dumps({"status": report["status"], "artifacts": report["artifacts"], "by_language": report["by_language"]}, indent=2))


if __name__ == "__main__":
    main()
