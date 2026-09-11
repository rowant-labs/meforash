"""Fixtures target editorial boundaries, Unicode loss, and source verification."""

import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from xml.sax.saxutils import escape

from bibleprep import greek


class GreekPreparationTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)

    def fixture(self, book, rows):
        """Rows supply independently specified text and XML word arrays."""
        text_path = self.root / "data/sblgnt/text" / f"{book}.txt"
        xml_path = self.root / "data/sblgnt/xml" / f"{book}.xml"
        text_path.parent.mkdir(parents=True, exist_ok=True)
        xml_path.parent.mkdir(parents=True, exist_ok=True)
        text_lines = ["ΔΟΚΙΜΗ"]
        xml_lines = ['<book id="fixture"><title>ΔΟΚΙΜΗ</title><p>']
        for chapter, verse, text, words in rows:
            text_lines.append(f"{book} {chapter}:{verse}\t{text}")
            xml_lines.append(f'<verse-number id="Fixture {chapter}:{verse}">{verse}</verse-number>')
            xml_lines.extend(f"<w>{escape(word)}</w><suffix/>" for word in words)
        xml_lines.append("</p></book>")
        text_path.write_text("\n".join(text_lines) + "\n", encoding="utf-8")
        xml_path.write_text("\n".join(xml_lines), encoding="utf-8")
        return text_path, xml_path

    def parse(self, book, rows):
        paths = self.fixture(book, rows)
        return greek.parse_book(*paths, book)

    def test_preserves_combining_marks_and_distinct_punctuation(self):
        spelling = "α\u0313\u0301νθρωπος"
        source = f"⸀{spelling}· λόγος; τέλος· "
        record = self.parse("Matt", [(1, 1, source, [spelling, "λόγος", "τέλος"])])[0]
        self.assertEqual(record["source_text"], source)
        self.assertEqual(record["text"], f"{spelling}· λόγος; τέλος·")
        self.assertEqual(record["main_text"], record["text"])
        self.assertEqual(record["apparatus_markers"][0],
                         {"symbol": "⸀", "source_start": 0, "source_end": 1,
                          "text_offset": 0})

    def test_numbered_apparatus_anchors_are_not_left_as_bible_numbers(self):
        record = self.parse("1Cor", [(12, 10, "⸀ἄλλῳ ⸁ἄλλῳ ⸀1ἄλλῳ ⸀2ἄλλῳ·",
                                     ["ἄλλῳ"] * 4)])[0]
        self.assertEqual(record["text"], "ἄλλῳ ἄλλῳ ἄλλῳ ἄλλῳ·")
        self.assertEqual([m["symbol"] for m in record["apparatus_markers"]],
                         ["⸀", "⸁", "⸀1", "⸀2"])

    def test_john_bracket_continues_across_chapter_and_interior_verses(self):
        records = self.parse("John", [
            (7, 52, "προφήτης.", ["προφήτης"]),
            (7, 53, "⟦καὶ ἐπορεύθη·", ["καὶ", "ἐπορεύθη"]),
            (8, 1, "Ἰησοῦς.", ["Ἰησοῦς"]),
            (8, 11, "μηκέτι ἁμάρτανε.⟧", ["μηκέτι", "ἁμάρτανε"]),
            (8, 12, "Πάλιν.", ["Πάλιν"]),
        ])
        self.assertEqual([r["main_text"] for r in records],
                         ["προφήτης.", "", "", "", "Πάλιν."])
        alternatives = [r["alternatives"][0] for r in records[1:4]]
        self.assertEqual(len({a["group_id"] for a in alternatives}), 1)
        self.assertEqual([a["text"] for a in alternatives],
                         ["καὶ ἐπορεύθη·", "Ἰησοῦς.", "μηκέτι ἁμάρτανε."])
        self.assertEqual(alternatives[1]["kind"], "pericope_adulterae")
        self.assertFalse(alternatives[1]["opens_here"])
        self.assertFalse(alternatives[1]["closes_here"])
        self.assertEqual(alternatives[1]["source_span"]["end"]["id"], "sblgnt:John.8.11")

    def test_mark_shorter_ending_does_not_replace_or_extend_primary_verse(self):
        records = self.parse("Mark", [
            (16, 8, "ἐφοβοῦντο γάρ. ⟦Πάντα δὲ ἀμήν.⟧",
             ["ἐφοβοῦντο", "γάρ", "Πάντα", "δὲ", "ἀμήν"]),
            (16, 9, "⟦Ἀναστὰς δὲ", ["Ἀναστὰς", "δὲ"]),
            (16, 20, "σημείων.⟧", ["σημείων"]),
        ])
        self.assertEqual(records[0]["main_text"], "ἐφοβοῦντο γάρ.")
        self.assertEqual(records[0]["alternatives"][0]["text"], "Πάντα δὲ ἀμήν.")
        self.assertEqual(records[0]["editorial_status"], "main_with_supplement")
        self.assertEqual(records[0]["alternatives"][0]["kind"], "shorter_ending_of_mark")
        self.assertEqual(records[1]["alternatives"][0]["kind"], "longer_ending_of_mark")
        self.assertNotEqual(records[0]["alternatives"][0]["group_id"],
                            records[1]["alternatives"][0]["group_id"])

    def test_square_bracket_doubt_is_retained_across_verses(self):
        records = self.parse("Luke", [
            (22, 19, "σῶμά μου ⸂[τὸ διδόμενον·", ["σῶμά", "μου", "τὸ", "διδόμενον"]),
            (22, 20, "⸄καὶ ποτήριον⸅ ἐκχυννόμενον]⸃.",
             ["καὶ", "ποτήριον", "ἐκχυννόμενον"]),
        ])
        self.assertEqual(records[0]["main_text"], "σῶμά μου [τὸ διδόμενον·")
        self.assertEqual(records[1]["main_text"], "καὶ ποτήριον ἐκχυννόμενον].")
        self.assertEqual(records[1]["editorial_status"], "main_with_doubtful_wording")
        self.assertEqual(records[1]["editorial_spans"][0]["editorial_status"], "doubtful")
        self.assertEqual(records[1]["alternatives"], [])

    def test_absent_verse_is_reported_not_synthesized(self):
        records = self.parse("Matt", [(1, 1, "Βίβλος.", ["Βίβλος"]),
                                      (1, 3, "Ἰούδας.", ["Ἰούδας"])])
        summary = greek.summarize(records)
        self.assertEqual(summary["verses"], 2)
        self.assertEqual(summary["missing_internal_verse_numbers"], ["Matt.1.2"])

    def test_duplicate_reference_fails(self):
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            self.parse("Matt", [(1, 1, "λόγος", ["λόγος"]),
                                (1, 1, "λόγος", ["λόγος"])])

    def test_changed_accent_between_source_formats_fails(self):
        with self.assertRaisesRegex(ValueError, "Greek spelling mismatch"):
            self.parse("Matt", [(1, 1, "λόγος", ["λὸγος"])])

    def test_unbalanced_or_mismatched_editorial_brackets_fail(self):
        for source in ("⟦λόγος", "λόγος⟧", "[λόγος⟧"):
            with self.subTest(source=source), self.assertRaisesRegex(ValueError, "bracket"):
                self.parse("Matt", [(1, 1, source, ["λόγος"])])

    def test_manifest_validation_precedes_output_and_output_is_deterministic(self):
        paths = self.fixture("Matt", [(1, 1, "Βίβλος.", ["Βίβλος"])])
        manifest = self.root / "manifest.json"
        manifest.write_text(json.dumps({"revision": "fixture-revision", "files": [
            {"path": str(path.relative_to(self.root)),
             "sha256": hashlib.sha256(path.read_bytes()).hexdigest()} for path in paths
        ]}), encoding="utf-8")
        output = self.root / "output"
        with patch.object(greek, "MANIFEST_PATH", manifest), patch.object(greek, "BOOKS", ("Matt",)):
            summary = greek.prepare(self.root, output)
            first = (output / "verses.jsonl").read_bytes()
            self.assertEqual(summary["source_revision"], "fixture-revision")
            greek.prepare(self.root, output)
            self.assertEqual(first, (output / "verses.jsonl").read_bytes())
            paths[0].write_text("changed", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Missing or changed pinned"):
                greek.prepare(self.root, self.root / "must_not_exist")
            self.assertFalse((self.root / "must_not_exist").exists())


if __name__ == "__main__":
    unittest.main()
