import copy
import json
from pathlib import Path
import tempfile
import unittest

from bibleprep import prepare_inkling as inkling
from bibleprep import tokenize as original


class CharacterTokenizer:
    def encode(self, text, add_special_tokens=False):
        return inkling.Encoding([ord(character) for character in text])


def verse(number, text="בְּרֵאשִׁ֖ית", **extra):
    return {"id": f"oshb:Gen.1.{number}", "source_id": "oshb", "book": "Gen",
            "chapter": 1, "verse": number, "language": "hbo", "text": text, **extra}


class InklingPreparationTests(unittest.TestCase):
    def test_shift_mask_and_no_dropped_or_normalized_text(self):
        records = [verse(n, "בְּרֵאשִׁ֖ית ἀρχή\u0301 " * 3) for n in range(1, 6)]
        sequences = inkling.pack_group(original.reading_groups(records)[0],
                                       CharacterTokenizer(), 999998, 999999, "test", 180)
        self.assertGreater(len(sequences), 1)
        self.assertEqual([v for s in sequences for v in s["verse_ids"]], [r["id"] for r in records])
        self.assertEqual("\n".join(s["text"] for s in sequences), "\n".join(r["text"] for r in records))
        for sequence in sequences:
            self.assertEqual(sequence["input_ids"][0], 999998)
            self.assertEqual(sequence["input_ids"][1:], sequence["target_ids"][:-1])
            predicted = [t for t, w in zip(sequence["target_ids"], sequence["weights"]) if w]
            self.assertEqual(predicted, [ord(c) for c in sequence["text"]] + [999999])
            self.assertEqual(sequence["loss_token_count"], sequence["body_token_count"] + 1)
            self.assertLessEqual(len(sequence["input_ids"]), 180)

    def test_bos_is_counted_at_window_boundary(self):
        group = original.reading_groups([verse(1)])[0]
        old = original.encode_sequence(group, CharacterTokenizer(), 999999, "test")
        with self.assertRaisesRegex(ValueError, "No truncation"):
            inkling.pack_group(group, CharacterTokenizer(), 999998, 999999, "test",
                               old["processed_token_count"])
        packed = inkling.pack_group(group, CharacterTokenizer(), 999998, 999999, "test",
                                    old["processed_token_count"] + 1)
        self.assertEqual(len(packed), 1)

    def test_supplement_and_main_keep_previous_split_and_editorial_metadata(self):
        records = [{"id": "sblgnt:John.7.53", "source_id": "sblgnt", "book": "John",
                    "chapter": 7, "verse": 53, "language": "grc", "text": "καὶ", "main_text": "",
                    "alternatives": [{"text": "καὶ", "group_id": "john-group", "kind": "pericope"}]},
                   {"id": "sblgnt:John.8.1", "source_id": "sblgnt", "book": "John",
                    "chapter": 8, "verse": 1, "language": "grc", "text": "Ἰησοῦς", "main_text": "",
                    "alternatives": [{"text": "Ἰησοῦς", "group_id": "john-group", "kind": "pericope"}]},
                   {"id": "sblgnt:John.8.12", "source_id": "sblgnt", "book": "John",
                    "chapter": 8, "verse": 12, "language": "grc", "text": "Πάλιν"}]
        previous, current = [], []
        for group in original.reading_groups(records):
            previous.extend(original.pack_group(group, CharacterTokenizer(), 999999, inkling.SEED, 512))
            current.extend(inkling.pack_group(group, CharacterTokenizer(), 999998, 999999, inkling.SEED, 512))
        self.assertEqual(inkling.fragment_splits(previous), inkling.fragment_splits(current))
        self.assertEqual({s["split_family"]["chapter"] for s in current}, {7})
        self.assertEqual([s["editorial_spans"] for s in previous], [s["editorial_spans"] for s in current])
        self.assertEqual({s["layer"] for s in current}, {"main", "supplement:pericope:john-group"})

    def test_original_artifact_check_rejects_split_drift_or_dropped_fragment(self):
        group = original.reading_groups([verse(1), verse(2)])[0]
        previous = original.pack_group(group, CharacterTokenizer(), 999999, inkling.SEED, 512)
        current = inkling.pack_group(group, CharacterTokenizer(), 999998, 999999, inkling.SEED, 512)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "manifests").mkdir()
            old = root / "old.jsonl"
            old.write_text("\n".join(json.dumps(row) for row in previous) + "\n")
            (root / "manifests/preparation-v1.json").write_text(json.dumps({
                "seed": inkling.SEED, "artifacts": {"all": {
                    "path": "old.jsonl", "sha256": original.sha256(old)}}}))
            self.assertEqual(inkling.verify_prior_split(current, root)["reading_fragments"], 2)
            modified = copy.deepcopy(current)
            modified[0]["split"] = "validation" if current[0]["split"] == "train" else "train"
            with self.assertRaisesRegex(ValueError, "split changed"):
                inkling.verify_prior_split(modified, root)
            modified = copy.deepcopy(current)
            modified[0]["verse_ids"].pop()
            with self.assertRaisesRegex(ValueError, "coverage"):
                inkling.verify_prior_split(modified, root)
            old.write_text(old.read_text() + "\n")
            with self.assertRaisesRegex(ValueError, "checksum"):
                inkling.verify_prior_split(current, root)

    def test_alignment_validator_rejects_bad_targets_and_masks(self):
        sequence = inkling.encode_sequence(original.reading_groups([verse(1)])[0],
                                           CharacterTokenizer(), 999998, 999999)
        for field, index, value in (("weights", 0, 1), ("target_ids", -1, 999998),
                                    ("target_ids", 1, 123), ("weights", -1, 0)):
            corrupted = copy.deepcopy(sequence)
            corrupted[field][index] = value
            with self.assertRaises(ValueError):
                inkling.validate_sequence(corrupted, 999998, 999999)

    def test_native_encoder_checks_exact_unicode_and_independent_ids(self):
        class Native:
            def encode_ordinary(self, text):
                return [ord(c) for c in text]
            def decode(self, tokens):
                return "".join(chr(t) for t in tokens)
        class Pinned:
            def encode(self, text, add_special_tokens=False):
                return [ord(c) for c in text]
        native, pinned = Native(), Pinned()
        tokenizer = inkling.InklingTextTokenizer(native, pinned)
        text = "בְּ λόγος\u0301"
        self.assertEqual(tokenizer.encode(text).ids, [ord(c) for c in text])
        pinned.encode = lambda *args, **kwargs: [1]
        with self.assertRaisesRegex(ValueError, "token IDs differ"):
            tokenizer.encode(text)
        native.decode = lambda tokens: "normalized"
        with self.assertRaisesRegex(ValueError, "Unicode"):
            tokenizer.encode(text)


if __name__ == "__main__":
    unittest.main()
