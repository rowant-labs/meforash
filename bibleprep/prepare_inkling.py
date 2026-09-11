"""Prepare pinned, original-language Inkling data locally; never call a model API.

This is a raw-document experiment, not chat SFT. Native document boundary tokens
surround masked edition metadata and ordinary-encoded ancient wording. The
provider documents the tokenizer and training primitives, but does not prescribe
this particular continued-pretraining format.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from dataclasses import dataclass
import importlib.metadata
import json
from pathlib import Path

from bibleprep import tokenize as original

ROOT = Path(__file__).resolve().parents[1]
MODEL = "thinkingmachines/Inkling"
ASSET_MANIFEST = "manifests/comparison-large-models-v1.json"
PRICE_MANIFEST = "manifests/comparison-large-pricing-v1.json"
ARTIFACT_DIRECTORY = "data/prepared/inkling-v1"
PREPARATION_MANIFEST = "manifests/preparation-inkling-v1.json"
SEED = "bible-v1"


@dataclass(frozen=True)
class Encoding:
    ids: list[int]


class InklingTextTokenizer:
    """Use the native ordinary encoder, checking exact text and HF token parity."""

    def __init__(self, native, pinned):
        self.native, self.pinned = native, pinned

    def encode(self, text: str, add_special_tokens: bool = False) -> Encoding:
        if add_special_tokens:
            raise ValueError("Document boundaries must be added explicitly.")
        ids = list(self.native.encode_ordinary(text))
        if self.native.decode(ids) != text:
            raise ValueError("Native tokenizer changed original Unicode text.")
        if ids != self.pinned.encode(text, add_special_tokens=False):
            raise ValueError("Native and pinned HF token IDs differ on source text.")
        return Encoding(ids)


def load_tokenizer():
    # These existing helpers validate all local asset hashes and compare the
    # entire native vocabulary with the independently pinned HF rank file.
    from bibleprep import tinker_compare as comparison

    entry, identity, runtime = comparison.local_identity(MODEL, ASSET_MANIFEST)
    packages = {}
    for package in ("tml-renderers", "torch", "transformers", "tokenizers"):
        expected = runtime.get(package)
        if expected is None:
            # The comparison manifest pins the native packages. HF packages are
            # recorded in its dependency lock, with explicit versions here.
            expected = {"transformers": "5.16.1", "tokenizers": "0.23.2"}.get(package)
        if expected is None or importlib.metadata.version(package) != expected:
            raise ValueError(f"Inkling preparation package version differs: {package}")
        packages[package] = expected
    native_package = comparison.package_identity("tml-renderers", runtime["tml-renderers"])
    pinned = comparison.load_pinned_tokenizer(MODEL, ASSET_MANIFEST)
    if pinned.backend_tokenizer.normalizer is not None:
        raise ValueError("Tokenizer normalization changed; review Unicode policy.")
    profile = comparison.TmlProfile(pinned, MODEL, ASSET_MANIFEST)
    bos = profile.native.encode_special("begin_of_text")
    eos = profile.native.encode_special("endoftext")
    if (bos, eos) != (200028, 199999):
        raise ValueError("Pinned Inkling document boundary IDs changed.")
    parity = {key: profile.parity[key] for key in (
        "vocabulary_sha256", "vocabulary_entries", "unicode_probes_passed",
        "comparison", "live_sdk_tokenizer_compared", "sdk_tokenizer_accessor")}
    parity.update({"all_encoded_header_and_body_token_ids_compared": True,
                   "all_encoded_header_and_body_unicode_roundtrips_checked": True})
    return InklingTextTokenizer(profile.native, pinned), bos, eos, {
        "repository": entry["tokenizer_repository"], "revision": entry["revision"],
        "tokenizer_sha256": identity["tokenizer_sha256"],
        "asset_manifest": ASSET_MANIFEST,
        "asset_manifest_sha256": identity["comparison_manifest_sha256"],
        "runtime_packages": packages, "native_package_identity": native_package,
        "parity": parity,
    }


def encode_sequence(items, tokenizer, bos: int, eos: int, seed: str = SEED) -> dict:
    """Reuse audited text/metadata packing; prepend a masked native BOS position."""
    sequence = original.encode_sequence(items, tokenizer, eos, seed)
    first_input = sequence["input_ids"][0]
    sequence["input_ids"] = [bos] + sequence["input_ids"]
    sequence["target_ids"] = [first_input] + sequence["target_ids"]
    sequence["weights"] = [0] + sequence["weights"]
    sequence["processed_token_count"] += 1
    validate_sequence(sequence, bos, eos)
    return sequence


def validate_sequence(sequence: dict, bos: int, eos: int) -> None:
    inputs, targets, weights = (sequence[key] for key in ("input_ids", "target_ids", "weights"))
    if not inputs or len(inputs) != len(targets) or len(inputs) != len(weights):
        raise ValueError("Prepared token/weight lengths differ.")
    if inputs[0] != bos or targets[-1] != eos or inputs[1:] != targets[:-1]:
        raise ValueError("Prepared next-token alignment or document boundary differs.")
    if weights[0] != 0 or set(weights) != {0, 1}:
        raise ValueError("Prepared loss mask must separate metadata and document targets.")
    loss_count = sequence["body_token_count"] + 1
    if weights != [0] * (len(inputs) - loss_count) + [1] * loss_count:
        raise ValueError("Loss must cover exactly the original-language body and EOS.")
    if (sequence["processed_token_count"] != len(inputs)
            or sequence["loss_token_count"] != sum(weights)):
        raise ValueError("Prepared token counts differ from the actual arrays.")


def pack_group(group, tokenizer, bos: int, eos: int, seed: str, maximum: int) -> list[dict]:
    """Pack complete consecutive verses, counting the additional BOS position."""
    packed, pending = [], []
    for item in group:
        candidate = encode_sequence(pending + [item], tokenizer, bos, eos, seed)
        if candidate["processed_token_count"] <= maximum:
            pending.append(item)
            continue
        if pending:
            packed.append(encode_sequence(pending, tokenizer, bos, eos, seed))
        pending = [item]
        if encode_sequence(pending, tokenizer, bos, eos, seed)["processed_token_count"] > maximum:
            raise ValueError(f"Verse exceeds window; increase --max-tokens. No truncation: {item['id']}")
    if pending:
        packed.append(encode_sequence(pending, tokenizer, bos, eos, seed))
    return packed


def fragment_splits(sequences) -> dict[tuple, str]:
    result = {}
    for sequence in sequences:
        for verse_id in sequence["verse_ids"]:
            key = (verse_id, sequence["layer"])
            if key in result:
                raise ValueError("Duplicate prepared reading fragment.")
            result[key] = sequence["split"]
    return result


def verify_prior_split(sequences: list[dict], root: Path) -> dict:
    prior_path = root / "manifests/preparation-v1.json"
    prior = json.loads(prior_path.read_text())
    if prior["seed"] != SEED:
        raise ValueError("The previous development split uses a different seed.")
    old_path = root / prior["artifacts"]["all"]["path"]
    if original.sha256(old_path) != prior["artifacts"]["all"]["sha256"]:
        raise ValueError("The previous preparation artifact failed its checksum.")
    with old_path.open() as handle:
        previous = fragment_splits(json.loads(line) for line in handle)
    current = fragment_splits(sequences)
    if previous != current:
        raise ValueError("Reading-fragment coverage or chapter-family split changed.")
    chapters = defaultdict(set)
    for sequence in sequences:
        chapters[sequence["split"]].add((sequence["source_id"], sequence["book"], sequence["chapter"]))
    if chapters["train"] & chapters["validation"]:
        raise ValueError("A chapter occurs in both development splits.")
    return {"previous_manifest": str(prior_path.relative_to(root)),
            "previous_manifest_sha256": original.sha256(prior_path),
            "every_reading_fragment_preserves_previous_split": True,
            "reading_fragments": len(current),
            "chapters": {key: len(value) for key, value in chapters.items()}}


def prepare(maximum: int = 2048, root: Path = ROOT) -> dict:
    if maximum < 128:
        raise ValueError("--max-tokens must be at least 128")
    tokenizer, bos, eos, tokenizer_identity = load_tokenizer()
    records, input_hashes = [], {}
    for source in ("oshb", "sblgnt"):
        path = root / f"data/processed/{source}/verses.jsonl"
        input_hashes[source] = original.sha256(path)
        source_manifest = json.loads((root / f"manifests/{source}.json").read_text())
        expected = (source_manifest["prepared_artifact"]["sha256"] if source == "oshb"
                    else source_manifest["prepared_outputs"]["verses.jsonl"]["sha256"])
        if input_hashes[source] != expected:
            raise ValueError(f"Prepared source checksum differs from release manifest: {source}")
        records.extend(json.loads(line) for line in path.read_text().splitlines())
    if len({row["id"] for row in records}) != len(records):
        raise ValueError("Duplicate source verse IDs")
    sequences = [sequence for group in original.reading_groups(records)
                 for sequence in pack_group(group, tokenizer, bos, eos, SEED, maximum)]
    split_check = verify_prior_split(sequences, root)
    out = root / ARTIFACT_DIRECTORY
    out.mkdir(parents=True, exist_ok=True)
    artifacts = {}
    for label in ("all", "train", "validation"):
        selected = [s for s in sequences if label == "all" or s["split"] == label]
        path = out / f"{label}.jsonl"
        with path.open("w", encoding="utf-8") as handle:
            for sequence in selected:
                handle.write(json.dumps(sequence, ensure_ascii=False, separators=(",", ":")) + "\n")
        artifacts[label] = {
            "path": str(path.relative_to(root)), "sha256": original.sha256(path),
            "sequences": len(selected),
            "processed_tokens": sum(s["processed_token_count"] for s in selected),
            "loss_tokens": sum(s["loss_token_count"] for s in selected),
            "body_tokens": sum(s["body_token_count"] for s in selected),
        }
    def breakdown(key):
        totals = defaultdict(lambda: {"sequences": 0, "processed_tokens": 0, "body_tokens": 0})
        for sequence in sequences:
            row = totals[sequence[key]]
            row["sequences"] += 1
            row["processed_tokens"] += sequence["processed_token_count"]
            row["body_tokens"] += sequence["body_token_count"]
        return dict(totals)
    pricing = json.loads((root / PRICE_MANIFEST).read_text())
    price = next(row for row in pricing["models"] if row["tinker_id"] == MODEL)
    rate = float(price["train"].replace("$", ""))
    report = {
        "schema_version": 1, "status": "prepared_not_trained", "model": MODEL,
        "tokenizer": tokenizer_identity, "input_sha256": input_hashes,
        "seed": SEED, "maximum_input_tokens": maximum,
        "preparation_code_sha256": {
            f"bibleprep/{name}.py": original.sha256(root / f"bibleprep/{name}.py")
            for name in ("hebrew", "greek", "tokenize", "prepare_inkling", "tinker_compare", "tinker_evaluate", "evaluate")},
        "bos_token_id": bos, "eos_token_id": eos, "unicode_normalization": "none",
        "framing": {
            "objective": "raw_original_language_next_token_prediction",
            "format": "native begin_of_text + masked ordinary metadata + ordinary original-language body + native endoftext",
            "status": "experimental project design; not a provider-prescribed raw-document recipe",
            "metadata_loss": "zero", "body_and_eos_loss": "one",
            "shift": "exactly once; input_ids=full_ids[:-1], target_ids=full_ids[1:], weights=full_weights[1:]",
            "chat_or_thinking_targets": False,
            "tokenization_boundaries": "Metadata and body encoded separately to keep the loss boundary exact; each part is checked against pinned HF tokens and round-tripped without Unicode normalization.",
            "references": [
                "https://tinker-docs.thinkingmachines.ai/cookbook/inkling/tml-renderers/",
                "https://tinker-docs.thinkingmachines.ai/tinker/losses/cross-entropy/",
                "https://huggingface.co/thinkingmachines/Inkling/tree/828496eeae4c243ff1a22f7f28ff83694f2f7bc9",
            ],
        },
        "source_verse_records": len(records),
        "source_verse_counts": dict(Counter(r["source_id"] for r in records)),
        "books": {source: list(dict.fromkeys(r["book"] for r in records if r["source_id"] == source))
                  for source in ("oshb", "sblgnt")},
        "artifacts": artifacts, "by_language": breakdown("language"),
        "by_source": breakdown("source_id"), "by_book": breakdown("book"), "by_layer": breakdown("layer"),
        "development_split_verification": split_check,
        "split_policy": "Reuse previous chapter-family grouping and bible-v1 seed across all edition layers; verify every fragment's split against the checksum-verified previous all.jsonl.",
        "split_limitations": "Development holdout excludes these chapters from adapter updates only. Base pretraining exposure is unknown. all.jsonl includes validation chapters and must not be used for the development pass.",
        "price_source": pricing["source"], "price_checked_on": pricing["retrieved_on"],
        "price_manifest": PRICE_MANIFEST, "price_manifest_sha256": original.sha256(root / PRICE_MANIFEST),
        "training_usd_per_million_processed_tokens": rate,
        "estimated_training_compute_usd": {
            label: round(item["processed_tokens"] * rate / 1_000_000, 6)
            for label, item in artifacts.items()},
        "cost_limitations": "One pass of unpadded input positions at the referenced historical price snapshot, not an invoice or current-price guarantee. Calibration must reconcile provider metering; forward-only evaluation, inference, checkpoint storage and retries excluded.",
    }
    serialized = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    (out / "summary.json").write_text(serialized, encoding="utf-8")
    (root / PREPARATION_MANIFEST).write_text(serialized, encoding="utf-8")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--max-tokens", type=int, default=2048)
    args = parser.parse_args()
    if args.max_tokens < 128:
        parser.error("--max-tokens must be at least 128")
    report = prepare(maximum=args.max_tokens)
    print(json.dumps({key: report[key] for key in (
        "source_verse_counts", "artifacts", "development_split_verification",
        "estimated_training_compute_usd")}, indent=2))


if __name__ == "__main__":
    main()
