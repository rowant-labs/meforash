import unittest
from bibleprep.tokenize import chapter_families, chapter_split, reading_groups, pack_group


class CharacterTokenizer:
    def encode(self, text, add_special_tokens=False):
        class Encoding:
            ids = [ord(c) for c in text]
        return Encoding()


def verse(number, text="λόγος", **extra):
    return {"id": f"sblgnt:Mark.16.{number}", "source_id": "sblgnt", "book": "Mark",
            "chapter": 16, "verse": number, "language": "grc", "text": text, **extra}


class PackingTests(unittest.TestCase):
    def test_shift_mask_and_no_dropped_text(self):
        records = [verse(n, "ἀρχή " * 10) for n in range(1, 5)]
        sequences = pack_group(reading_groups(records)[0], CharacterTokenizer(), 999999, "test", 190)
        self.assertGreater(len(sequences), 1)
        self.assertEqual([v for s in sequences for v in s["verse_ids"]], [r["id"] for r in records])
        self.assertEqual("\n".join(s["text"] for s in sequences), "\n".join(r["text"] for r in records))
        for s in sequences:
            self.assertEqual(s["input_ids"][1:], s["target_ids"][:-1])
            self.assertEqual(s["target_ids"][-1], 999999)
            predicted = [t for t, w in zip(s["target_ids"], s["weights"]) if w]
            self.assertEqual(predicted, [ord(c) for c in s["text"]] + [999999])
            self.assertEqual(len(s["weights"]), len(s["input_ids"]))
            self.assertLessEqual(len(s["input_ids"]), 190)

    def test_supplements_separate_and_split_with_parent(self):
        records = [verse(8, main_text="κύριος", alternatives=[{"text": "ἄλλος", "kind": "shorter", "group_id": "g1"}]),
                   verse(9, main_text="", alternatives=[{"text": "ἔτερος", "kind": "longer", "group_id": "g2"}])]
        groups = reading_groups(records)
        self.assertEqual(len(groups), 3)
        self.assertEqual([g[0]["text"] for g in groups], ["κύριος", "ἄλλος", "ἔτερος"])
        splits = {pack_group(g, CharacterTokenizer(), 999999, "test", 512)[0]["split"] for g in groups}
        self.assertEqual(len(splits), 1)

    def test_never_join_across_gap_or_language(self):
        records = [verse(1), verse(2, language="arc"), verse(3)]
        self.assertEqual(len(reading_groups(records)), 3)

    def test_overlong_verse_fails_without_truncation(self):
        with self.assertRaisesRegex(ValueError, "No truncation"):
            pack_group(reading_groups([verse(1, "x" * 1000)])[0], CharacterTokenizer(), 999999, "test", 128)

    def test_holdout_is_deterministic_and_nonempty(self):
        splits = [chapter_split("oshb", "Gen", c, "test") for c in range(1, 51)]
        self.assertIn("train", splits)
        self.assertIn("validation", splits)
        self.assertEqual(splits, [chapter_split("oshb", "Gen", c, "test") for c in range(1, 51)])

    def test_cross_chapter_group_binds_primary_and_supplement_splits(self):
        records = [
            verse(53, book="John", chapter=7, id="sblgnt:John.7.53", main_text="",
                  alternatives=[{"text": "καὶ", "kind": "pericope_adulterae", "group_id": "john-group"}]),
            verse(1, book="John", chapter=8, id="sblgnt:John.8.1", main_text="",
                  alternatives=[{"text": "Ἰησοῦς", "kind": "pericope_adulterae", "group_id": "john-group"}]),
            verse(12, book="John", chapter=8, id="sblgnt:John.8.12", main_text="Πάλιν"),
        ]
        seed = "bible-v8"
        self.assertNotEqual(chapter_split("sblgnt", "John", 7, seed),
                            chapter_split("sblgnt", "John", 8, seed))
        sequences = [sequence for group in reading_groups(records)
                     for sequence in pack_group(group, CharacterTokenizer(), 999999, seed, 512)]
        self.assertEqual({s["split"] for s in sequences},
                         {chapter_split("sblgnt", "John", 7, seed)})
        self.assertEqual({s["split_family"]["chapter"] for s in sequences}, {7})
        self.assertEqual({s["chapter"] for s in sequences}, {7, 8})

    def test_editorial_family_union_is_transitive_and_order_independent(self):
        records = [
            verse(1, chapter=7, editorial_spans=[{"group_id": "a"}]),
            verse(1, chapter=8, editorial_spans=[{"group_id": "a"}, {"group_id": "b"}]),
            verse(1, chapter=9, editorial_spans=[{"group_id": "b"}]),
            verse(1, chapter=6),
            verse(1, chapter=10, source_id="other", editorial_spans=[{"group_id": "a"}]),
        ]
        families = chapter_families(records)
        self.assertEqual(families, chapter_families(list(reversed(records))))
        for chapter in (7, 8, 9):
            self.assertEqual(families[("sblgnt", "Mark", chapter)], ("sblgnt", "Mark", 7))
        self.assertEqual(families[("sblgnt", "Mark", 6)], ("sblgnt", "Mark", 6))
        self.assertEqual(families[("other", "Mark", 10)], ("other", "Mark", 10))

    def test_smaller_windows_keep_doubtful_span_continuation_without_token_changes(self):
        source_span = {"start": {"id": "sblgnt:Mark.16.1", "offset": 0},
                       "end": {"id": "sblgnt:Mark.16.2", "offset": 51}}
        texts = ["[" + "λόγος" * 10, "λόγος" * 10 + "]"]
        records = [verse(number, text, editorial_spans=[{
            "group_id": "doubtful", "kind": "doubtful_wording", "editorial_status": "doubtful",
            "start": 0, "end": len(text), "opens_here": number == 1,
            "closes_here": number == 2, "source_span": source_span,
        }]) for number, text in enumerate(texts, 1)]
        sequences = pack_group(reading_groups(records)[0], CharacterTokenizer(), 999999, "test", 150)
        plain_records = [{key: value for key, value in row.items() if key != "editorial_spans"}
                         for row in records]
        plain = pack_group(reading_groups(plain_records)[0], CharacterTokenizer(), 999999, "test", 150)
        self.assertEqual(len(sequences), 2)
        self.assertNotIn("[", sequences[1]["text"])
        continuation = sequences[1]["editorial_spans"][0]
        self.assertEqual(continuation["verse_id"], "sblgnt:Mark.16.2")
        self.assertFalse(continuation["opens_here"])
        self.assertTrue(continuation["closes_here"])
        self.assertEqual(continuation["source_span"], source_span)
        self.assertEqual(continuation["offset_basis"], "source_verse.text")
        self.assertEqual(continuation["sequence_verse_range"], {"start": 0, "end": 51})
        for annotated, unannotated in zip(sequences, plain):
            for key in ("input_ids", "target_ids", "weights", "processed_token_count"):
                self.assertEqual(annotated[key], unannotated[key])

    def test_supplement_metadata_stays_with_its_reading(self):
        span = {"group_id": "short", "editorial_status": "double_bracketed",
                "kind": "shorter", "start": 7, "end": 15,
                "opens_here": True, "closes_here": True}
        record = verse(8, "κύριος ⟦ἄλλος⟧", main_text="κύριος", editorial_spans=[span],
                       alternatives=[{**span, "text": "ἄλλος"}])
        sequences = [pack_group(group, CharacterTokenizer(), 999999, "test", 512)[0]
                     for group in reading_groups([record])]
        self.assertEqual(sequences[0]["editorial_spans"], [])
        self.assertEqual(sequences[1]["editorial_spans"][0]["group_id"], "short")
        self.assertEqual(sequences[1]["editorial_spans"][0]["verse_id"], record["id"])
        self.assertEqual(sequences[1]["editorial_spans"][0]["start"], 7)
        self.assertEqual(sequences[1]["editorial_spans"][0]["sequence_verse_range"],
                         {"start": 0, "end": len("ἄλλος")})


if __name__ == "__main__":
    unittest.main()
