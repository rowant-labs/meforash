"""Check complete source coverage, token loss alignment, and split integrity locally."""
import json
from collections import Counter
from pathlib import Path

from bibleprep.tokenize import ROOT, reading_groups, sha256


def audit(root: Path = ROOT) -> dict:
    from tokenizers import Tokenizer
    manifest = json.loads((root / "manifests/preparation-v1.json").read_text())
    for name, expected in manifest["preparation_code_sha256"].items():
        if sha256(root / name) != expected:
            raise ValueError(f"Preparation code changed since artifacts were generated: {name}")
    tokenizer = Tokenizer.from_file(str(root / "data/raw/tokenizers/gpt-oss-120b/tokenizer.json"))
    sources = []
    for source in ("oshb", "sblgnt"):
        path = root / f"data/processed/{source}/verses.jsonl"
        if sha256(path) != manifest["input_sha256"][source]:
            raise ValueError(f"Prepared source changed: {source}")
        sources.extend(json.loads(line) for line in path.read_text().splitlines())
    expected = {(item["id"], item["layer"]): item["text"] for group in reading_groups(sources) for item in group}
    seen = Counter()
    split_sequences, split_chapters = {}, {}
    all_sequences = set()
    for split in ("all", "train", "validation"):
        artifact = manifest["artifacts"][split]
        path = root / artifact["path"]
        if sha256(path) != artifact["sha256"]:
            raise ValueError(f"Training artifact changed: {split}")
        ids, chapters = set(), set()
        count, processed, loss = 0, 0, 0
        with path.open() as handle:
            for line in handle:
                s = json.loads(line)
                if s["id"] in ids:
                    raise ValueError("Duplicate sequence ID")
                ids.add(s["id"])
                chapters.add((s["source_id"], s["book"], s["chapter"]))
                if split != "all" and s["split"] != split:
                    raise ValueError("Wrong split membership")
                inputs, targets, weights = s["input_ids"], s["target_ids"], s["weights"]
                if not len(inputs) == len(targets) == len(weights) <= manifest["maximum_input_tokens"]:
                    raise ValueError("Token length mismatch")
                if inputs[1:] != targets[:-1] or targets[-1] != manifest["eos_token_id"]:
                    raise ValueError("Incorrect next-token alignment")
                if any(w not in (0, 1) for w in weights) or weights != sorted(weights):
                    raise ValueError("Incorrect loss mask")
                body_ids = [token for token, weight in zip(targets, weights) if weight][:-1]
                if tokenizer.decode(body_ids, skip_special_tokens=False) != s["text"]:
                    raise ValueError("Token decoding changed source Unicode/text")
                keys = [(verse_id, s["layer"]) for verse_id in s["verse_ids"]]
                if "\n".join(expected[key] for key in keys) != s["text"]:
                    raise ValueError("Training text differs from source layer")
                if split == "all":
                    seen.update(keys)
                count += 1
                processed += len(inputs)
                loss += sum(weights)
        if (count, processed, loss) != (artifact["sequences"], artifact["processed_tokens"], artifact["loss_tokens"]):
            raise ValueError("Manifest totals differ from actual data")
        if split == "all":
            all_sequences = ids
        else:
            split_sequences[split], split_chapters[split] = ids, chapters
    if set(seen) != set(expected) or set(seen.values()) != {1}:
        raise ValueError("Missing or duplicated source reading fragments")
    if split_sequences["train"] & split_sequences["validation"]:
        raise ValueError("Sequence leakage")
    if split_chapters["train"] & split_chapters["validation"]:
        raise ValueError("Chapter leakage")
    if split_sequences["train"] | split_sequences["validation"] != all_sequences:
        raise ValueError("Split does not cover the complete corpus")
    result = {
        "status": "passed", "source_verse_records": len(sources),
        "reading_fragments_covered_once": len(expected),
        "all_sequences": len(all_sequences),
        "train_chapters": len(split_chapters["train"]),
        "validation_chapters": len(split_chapters["validation"]),
        "source_text_roundtrip": "exact", "dropped_or_duplicate_reading_fragments": 0,
        "chapter_overlap": 0, "model_calls": 0,
        "meaning": "Mechanical data validation; no scholarly or model-quality claim",
    }
    (root / "manifests/audit-v1.json").write_text(json.dumps(result, indent=2) + "\n")
    return result


if __name__ == "__main__":
    print(json.dumps(audit(), indent=2))
