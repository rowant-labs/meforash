"""Prepare auditable, verse-preserving next-token data; never call a model API."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def chapter_split(source: str, book: str, chapter: int, seed: str) -> str:
    """Hash a chapter key; reading_groups first resolves editorial families."""
    key = f"{seed}:{source}:{book}:{chapter}".encode()
    return "validation" if int.from_bytes(hashlib.sha256(key).digest()[:8], "big") % 20 == 0 else "train"


def chapter_families(records: list[dict]) -> dict[tuple, tuple]:
    """Union chapters linked by editorial groups, including transitive links.

    Group identifiers are scoped to their source/book. Every layer in a linked
    chapter uses the earliest chapter's seed, not only the bracketed fragments.
    """
    parents = {}
    editorial_groups = {}

    def find(key):
        if parents[key] != key:
            parents[key] = find(parents[key])
        return parents[key]

    for record in records:
        chapter = (record["source_id"], record["book"], record["chapter"])
        parents.setdefault(chapter, chapter)
        for span in record.get("editorial_spans", []) + record.get("alternatives", []):
            if "group_id" not in span:
                continue
            group = (record["source_id"], record["book"], span["group_id"])
            first = editorial_groups.setdefault(group, chapter)
            roots = sorted((find(first), find(chapter)))
            parents[roots[1]] = roots[0]
    return {chapter: find(chapter) for chapter in parents}


def _reading_editorial_spans(record: dict, alternative: dict | None = None) -> list[dict]:
    """Retain source coordinates rather than mislabel them as packed offsets."""
    spans = record.get("editorial_spans", [])
    if alternative is None:
        # These supplements have been removed from the primary reading.
        spans = [span for span in spans if span.get("editorial_status") != "double_bracketed"]
    else:
        spans = [span for span in spans if span.get("group_id") == alternative["group_id"]]
        if not spans:
            spans = [{key: value for key, value in alternative.items() if key != "text"}]
    return [{**span, "verse_id": record["id"], "offset_basis": "source_verse.text"}
            for span in spans]


def reading_groups(records: list[dict]) -> list[list[dict]]:
    groups: dict[tuple, list[dict]] = {}
    families = chapter_families(records)
    for record in records:
        base = {k: record[k] for k in ("id", "source_id", "book", "chapter", "verse", "language")}
        family = families[(base["source_id"], base["book"], base["chapter"])]
        base["split_family"] = dict(zip(("source_id", "book", "chapter"), family))
        main = record.get("main_text", record["text"])
        if main.strip():
            layer = "main_ketiv" if record["source_id"] == "oshb" else "main"
            key = (base["source_id"], base["book"], base["chapter"], base["language"], layer)
            groups.setdefault(key, []).append({**base, "text": main, "layer": layer,
                                               "editorial_spans": _reading_editorial_spans(record)})
        for alt in record.get("alternatives", []):
            if not alt["text"].strip():
                continue
            layer = f"supplement:{alt['kind']}:{alt['group_id']}"
            key = (base["source_id"], base["book"], base["chapter"], base["language"], layer)
            groups.setdefault(key, []).append({**base, "text": alt["text"], "layer": layer,
                                               "editorial_spans": _reading_editorial_spans(record, alt)})
    # Split at gaps so language changes and excluded supplements never imply continuity.
    result = []
    for group in groups.values():
        contiguous = []
        for item in group:
            if contiguous and item["verse"] != contiguous[-1]["verse"] + 1:
                result.append(contiguous)
                contiguous = []
            contiguous.append(item)
        if contiguous:
            result.append(contiguous)
    return result


def encode_sequence(items: list[dict], tokenizer, eos: int, seed: str) -> dict:
    first, last = items[0], items[-1]
    family = first.get("split_family", {key: first[key] for key in ("source_id", "book", "chapter")})
    header = (f"[source={first['source_id']} language={first['language']} "
              f"passage={first['book']}.{first['chapter']}.{first['verse']}-{last['verse']} "
              f"layer={first['layer']}]\n")
    body = "\n".join(item["text"] for item in items)
    editorial_spans, verse_start = [], 0
    for item in items:
        editorial_spans.extend({**span,
                                "sequence_verse_range": {"start": verse_start,
                                                         "end": verse_start + len(item["text"])}}
                               for span in item.get("editorial_spans", []))
        verse_start += len(item["text"]) + 1
    prefix = tokenizer.encode(header, add_special_tokens=False).ids
    body_ids = tokenizer.encode(body, add_special_tokens=False).ids
    ids = prefix + body_ids + [eos]
    # Shift exactly once. Metadata supplies context but is not a prediction target.
    target_weights = [0] * len(prefix) + [1] * (len(body_ids) + 1)
    identity = f"{first['id']}:{last['verse']}:{first['layer']}"
    return {
        "id": identity,
        "source_id": first["source_id"], "book": first["book"],
        "chapter": first["chapter"], "language": first["language"],
        "layer": first["layer"], "verse_ids": [item["id"] for item in items],
        "split": chapter_split(family["source_id"], family["book"], family["chapter"], seed),
        "split_family": family,
        "editorial_spans": editorial_spans,
        "header": header, "text": body,
        "input_ids": ids[:-1], "target_ids": ids[1:], "weights": target_weights[1:],
        "body_token_count": len(body_ids), "processed_token_count": len(ids) - 1,
        "loss_token_count": sum(target_weights[1:]),
    }


def pack_group(group: list[dict], tokenizer, eos: int, seed: str, maximum: int) -> list[dict]:
    packed, pending = [], []
    for item in group:
        candidate = encode_sequence(pending + [item], tokenizer, eos, seed)
        if candidate["processed_token_count"] <= maximum:
            pending.append(item)
            continue
        if pending:
            packed.append(encode_sequence(pending, tokenizer, eos, seed))
        pending = [item]
        single = encode_sequence(pending, tokenizer, eos, seed)
        if single["processed_token_count"] > maximum:
            raise ValueError(f"Verse exceeds window; increase --max-tokens. No truncation: {item['id']}")
    if pending:
        packed.append(encode_sequence(pending, tokenizer, eos, seed))
    return packed


def prepare(root: Path = ROOT, maximum: int = 2048, seed: str = "bible-v1") -> dict:
    from tokenizers import Tokenizer
    manifest = json.loads((root / "manifests/tokenizer.json").read_text())
    directory = root / "data/raw/tokenizers/gpt-oss-120b"
    for entry in manifest["files"]:
        if sha256(directory / entry["path"]) != entry["sha256"]:
            raise ValueError(f"Tokenizer checksum mismatch: {entry['path']}")
    tokenizer = Tokenizer.from_file(str(directory / "tokenizer.json"))
    if tokenizer.normalizer is not None:
        raise ValueError("Tokenizer normalization changed; review Unicode policy")
    eos = tokenizer.token_to_id("<|endoftext|>")
    if eos is None:
        raise ValueError("Expected end-of-text token missing")
    records, input_hashes = [], {}
    for source in ("oshb", "sblgnt"):
        path = root / f"data/processed/{source}/verses.jsonl"
        input_hashes[source] = sha256(path)
        source_manifest = json.loads((root / f"manifests/{source}.json").read_text())
        if source == "oshb":
            expected = source_manifest["prepared_artifact"]["sha256"]
        else:
            expected = source_manifest["prepared_outputs"]["verses.jsonl"]["sha256"]
        if input_hashes[source] != expected:
            raise ValueError(f"Prepared source checksum differs from release manifest: {source}")
        records.extend(json.loads(line) for line in path.read_text().splitlines())
    ids = [r["id"] for r in records]
    if len(set(ids)) != len(ids):
        raise ValueError("Duplicate source verse IDs")
    sequences = []
    for group in reading_groups(records):
        sequences.extend(pack_group(group, tokenizer, eos, seed, maximum))
    out = root / "data/prepared/v1"
    out.mkdir(parents=True, exist_ok=True)
    artifacts = {}
    for label in ("all", "train", "validation"):
        selected = [s for s in sequences if label == "all" or s["split"] == label]
        path = out / f"{label}.jsonl"
        with path.open("w") as handle:
            for sequence in selected:
                handle.write(json.dumps(sequence, ensure_ascii=False, separators=(",", ":")) + "\n")
        artifacts[label] = {
            "path": str(path.relative_to(root)), "sha256": sha256(path),
            "sequences": len(selected),
            "processed_tokens": sum(s["processed_token_count"] for s in selected),
            "loss_tokens": sum(s["loss_token_count"] for s in selected),
            "body_tokens": sum(s["body_token_count"] for s in selected),
        }
    def breakdown(key):
        totals = defaultdict(lambda: {"sequences": 0, "processed_tokens": 0, "body_tokens": 0})
        for s in sequences:
            row = totals[s[key]]
            row["sequences"] += 1
            row["processed_tokens"] += s["processed_token_count"]
            row["body_tokens"] += s["body_token_count"]
        return dict(totals)
    pricing = json.loads((root / "manifests/tinker-pricing.json").read_text())
    prices = {m["tinker_id"]: float(m["train"].replace("$", "")) for m in pricing["models"]}
    report = {
        "schema_version": 1, "status": "prepared_not_trained",
        "tokenizer": {k: manifest[k] for k in ("repository", "revision")},
        "tokenizer_sha256": sha256(directory / "tokenizer.json"),
        "input_sha256": input_hashes, "seed": seed, "maximum_input_tokens": maximum,
        "preparation_code_sha256": {f"bibleprep/{name}.py": sha256(root / f"bibleprep/{name}.py") for name in ("hebrew", "greek", "tokenize")},
        "eos_token_id": eos, "unicode_normalization": "none",
        "source_verse_records": len(records),
        "source_verse_counts": dict(Counter(r["source_id"] for r in records)),
        "books": {source: list(dict.fromkeys(r["book"] for r in records if r["source_id"] == source)) for source in ("oshb", "sblgnt")},
        "artifacts": artifacts, "by_language": breakdown("language"),
        "by_source": breakdown("source_id"), "by_book": breakdown("book"),
        "by_layer": breakdown("layer"),
        "price_source": pricing["source"], "price_checked_on": pricing["retrieved_on"],
        "estimated_training_compute_usd": {
            model: {label: round(item["processed_tokens"] / 1_000_000 * rate, 6) for label, item in artifacts.items()}
            for model, rate in prices.items()
        },
        "cost_limitations": "One pass, unpadded prepared input positions. Reconcile actual provider metering in calibration; inference, validation forward passes, retries, minimum credits, hosting and review excluded. 20B estimate uses 120B tokenizer and requires provider tokenizer parity check.",
        "split_policy": "Chapters connected by any editorial group form one family; all layers use the earliest connected chapter's seed. Editorial offsets remain relative to each source verse's text; sequence_verse_range locates that verse's chosen reading in the sequence body.",
        "split_limitations": "Chapter-family holdout is adapter development only. Base pretraining exposure is unknown; final all.jsonl includes held-out chapters. Do not train on all.jsonl and claim validation is unseen.",
    }
    (out / "summary.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    (root / "manifests/preparation-v1.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--max-tokens", type=int, default=2048)
    parser.add_argument("--seed", default="bible-v1")
    args = parser.parse_args()
    if args.max_tokens < 128:
        parser.error("--max-tokens must be at least 128")
    report = prepare(maximum=args.max_tokens, seed=args.seed)
    print(json.dumps({k: report[k] for k in ("source_verse_counts", "artifacts", "estimated_training_compute_usd")}, indent=2))


if __name__ == "__main__":
    main()
