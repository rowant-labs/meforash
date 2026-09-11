"""Constructed OSHB-like fixtures, not training data or a biblical edition."""

from pathlib import Path
import hashlib
import json
import tempfile
import unittest
from unittest.mock import patch

from bibleprep.hebrew import BOOKS, OSIS, PINNED_REVISION, SourceError, main, parse_book, prepare, verify_release_source


def document(book: str, content: str, verse: int = 1) -> str:
    return f'''<osis xmlns="{OSIS}"><osisText xml:lang="he">
    <div type="book" osisID="{book}"><chapter osisID="{book}.1">
    <verse osisID="{book}.1.{verse}">{content}</verse>
    </chapter></div></osisText></osis>'''


def word(text: str, identifier: str, morph: str = "HNcmsa", kind: str = "") -> str:
    kind_attribute = f' type="{kind}"' if kind else ""
    return f'<w id="{identifier}" lemma="1" morph="{morph}"{kind_attribute}>{text}</w>'


class HebrewFixtureTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)

    def parse(self, content: str, verse: int = 1):
        path = self.directory / "Gen.xml"
        path.write_text(document("Gen", content, verse), encoding="utf-8")
        return list(parse_book(path))[0]

    def test_ketiv_qere_and_note_prose_are_separate(self):
        content = (
            word("מ/בן", "k1", kind="x-ketiv")
            + '<seg type="x-maqqef" subType="x-ketiv">־</seg>'
            + word("ימין", "k2", kind="x-ketiv")
            + '<note type="variant"><catchWord>מ/בן־ימין</catchWord>'
            + '<rdg type="x-qere">' + word("מִ/בִּנְיָמִ֗ין", "q1") + '</rdg></note>'
            + '<note type="exegesis">ENGLISH NOTE MUST NOT ENTER TEXT <rdg>א</rdg>.</note>'
            + '<seg type="x-sof-pasuq">׃</seg><seg type="x-pe">פ</seg>'
        )
        record = self.parse(content)
        self.assertEqual(record["text"], "מבן־ימין׃")
        self.assertEqual(record["text_layer"], "main/ketiv")
        self.assertEqual([t["id"] for t in record["tokens"]], ["k1", "k2"])
        self.assertEqual(record["tokens"][0]["raw_text"], "מ/בן")
        self.assertEqual(record["tokens"][0]["morpheme_segments"], ["מ", "בן"])
        note = record["notes"][0]
        self.assertEqual(note["after_token_index"], 1)
        self.assertFalse(note["included_in_text"])
        self.assertEqual(note["content"]["children"][1]["attributes"]["type"], "x-qere")
        self.assertEqual(note["content"]["children"][1]["children"][0]["text"], "מִ/בִּנְיָמִ֗ין")
        self.assertFalse(record["segments"][-1]["included_in_text"])
        self.assertEqual(record["segments"][-1]["raw_text"], "פ")
        self.assertNotIn("ENGLISH", record["text"])

    def test_language_comes_from_words_not_document_header(self):
        content = word("א", "h1") + word("ב", "a1", "ANcmsa") + word("ג", "h2")
        record = self.parse(content)
        self.assertEqual(record["language"], "mul")
        self.assertEqual(record["language_spans"], [
            {"language": "hbo", "token_start": 0, "token_end_exclusive": 1},
            {"language": "arc", "token_start": 1, "token_end_exclusive": 2},
            {"language": "hbo", "token_start": 2, "token_end_exclusive": 3},
        ])
        self.assertEqual(self.parse(word("א", "a1", "ANcmsa"))["language"], "arc")

    def test_alternative_language_does_not_change_main_language(self):
        content = word("א", "h1") + '<note type="variant"><rdg type="x-qere">' + word("ב", "a1", "ANcmsa") + '</rdg></note>'
        record = self.parse(content)
        self.assertEqual(record["language"], "hbo")
        self.assertEqual(record["text"], "א")

    def test_inline_letter_markup_and_unicode_order_are_preserved(self):
        # This combining-mark order must survive; do not silently NFC/NFD it.
        original = 'אֹ֖רֶ<seg type="x-small">ן</seg>'
        record = self.parse(word(original, "s1") + '<seg type="x-paseq">׀</seg>' + word("וְ/עַ<seg type=\"x-suspended\">י</seg>ן", "s2") + '<seg type="x-reversednun">׆</seg>')
        self.assertEqual(record["text"], "אֹ֖רֶן ׀ וְעַין ׆")
        self.assertEqual(record["tokens"][0]["raw_text"], "אֹ֖רֶן")
        self.assertEqual(record["tokens"][1]["inline_content"]["children"][0]["tail"], "ן")

    def test_note_before_any_word_is_not_invented_main_reading(self):
        record = self.parse('<note type="variant"><rdg type="x-qere">' + word("א", "q1") + '</rdg></note>' + word("ב", "h1"))
        self.assertEqual(record["text"], "ב")
        self.assertIsNone(record["notes"][0]["after_token_index"])

    def test_unknown_language_and_inline_notes_fail_closed(self):
        with self.assertRaisesRegex(SourceError, "language prefix"):
            self.parse(word("א", "bad1", "XNcmsa"))
        with self.assertRaisesRegex(SourceError, "inline word element"):
            self.parse(word("א<note>editor prose</note>", "bad2"))

    def test_unmarked_text_and_reference_gaps_are_not_dropped(self):
        with self.assertRaisesRegex(SourceError, "Unmarked text"):
            self.parse(word("א", "h1") + "accidental prose")
        with self.assertRaisesRegex(SourceError, "Expected verse"):
            self.parse(word("א", "h1"), verse=2)

    def test_missing_books_do_not_create_outputs(self):
        output = self.directory / "processed"
        with self.assertRaisesRegex(SourceError, "Book inventory mismatch"):
            prepare(self.directory, output)
        self.assertFalse(output.exists())

    def full_fixture(self) -> Path:
        source = self.directory / "source"
        (source / "wlc").mkdir(parents=True)
        (source / "LICENSE.md").write_text("Constructed test fixture; no upstream corpus bundled.\n", encoding="utf-8")
        (source / "README.md").write_text("Test fixtures only.\n", encoding="utf-8")
        for book in BOOKS:
            (source / "wlc" / f"{book}.xml").write_text(document(book, word("א", book + "-word")), encoding="utf-8")
        return source

    def test_full_inventory_and_reproducible_artifact(self):
        source = self.full_fixture()
        first = prepare(source, self.directory / "first")
        second = prepare(source, self.directory / "second")
        self.assertEqual(first, second)
        self.assertEqual(first["counts"]["books"], 39)
        self.assertEqual(first["counts"]["verses"], 39)
        records = [json.loads(line) for line in (self.directory / "first" / "verses.jsonl").read_text(encoding="utf-8").splitlines()]
        self.assertEqual(records[0]["id"], "oshb:Gen.1.1")
        self.assertEqual(records[-1]["id"], "oshb:Mal.1.1")
        self.assertIsNone(first["source_revision"])

    def test_duplicate_word_id_in_alternative_aborts_preparation(self):
        source = self.full_fixture()
        duplicate = word("א", "Gen-word") + '<note type="variant"><rdg type="x-qere">' + word("ב", "Gen-word") + '</rdg></note>'
        (source / "wlc" / "Gen.xml").write_text(document("Gen", duplicate), encoding="utf-8")
        output = self.directory / "output"
        with self.assertRaisesRegex(SourceError, "Duplicate source word ID"):
            prepare(source, output)
        self.assertFalse(output.exists())

    def release_fixture(self):
        source = self.full_fixture()
        (source / "parsing").mkdir()
        (source / "parsing" / "HebrewMorphologyCodes.html").write_text("Fixture language definitions", encoding="utf-8")
        (source / "wlc" / "VerseMap.xml").write_text("<fixture/>", encoding="utf-8")

        def artifact(relative):
            path = source / relative
            return {"path": relative, "bytes": path.stat().st_size,
                    "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}

        manifest = self.directory / "release-fixture.json"
        manifest.write_text(json.dumps({
            "source_id": "oshb", "pinned_commit": PINNED_REVISION,
            "books": [{"book": book, "artifact": artifact(f"wlc/{book}.xml")} for book in BOOKS],
            "supporting_source_artifacts": [artifact(name) for name in (
                "LICENSE.md", "README.md", "wlc/VerseMap.xml", "parsing/HebrewMorphologyCodes.html")],
        }), encoding="utf-8")
        return source, manifest

    def test_changed_pinned_input_is_rejected_by_cli_before_outputs(self):
        source, manifest = self.release_fixture()
        verify_release_source(source, manifest)  # Exact archive contents are accepted.
        original = source / "wlc" / "Gen.xml"
        # Same byte length: checking only filenames or file sizes would miss this.
        original.write_text(original.read_text(encoding="utf-8").replace("א", "ב"), encoding="utf-8")
        output = self.directory / "release-output"
        with self.assertRaisesRegex(SourceError, "input hash mismatch: wlc/Gen.xml"):
            main(["--source-dir", str(source), "--source-manifest", str(manifest), "--output-dir", str(output)])
        self.assertFalse(output.exists())

    def test_wrong_git_pin_is_rejected_even_when_inputs_match(self):
        source, manifest = self.release_fixture()
        output = self.directory / "release-output"
        with patch("bibleprep.hebrew._revision", return_value="f" * 40):
            with self.assertRaisesRegex(SourceError, "revision does not match release pin"):
                main(["--source-dir", str(source), "--source-manifest", str(manifest), "--output-dir", str(output)])
        self.assertFalse(output.exists())


RAW = Path(__file__).resolve().parents[1] / "data" / "raw" / "oshb" / "wlc"


@unittest.skipUnless((RAW / "Dan.xml").exists(), "Optional check requires acquired OSHB source")
class HebrewSourceBoundaryTests(unittest.TestCase):
    def test_actual_language_boundaries_and_short_aramaic_portions(self):
        records = {}
        for book in ("Gen", "Dan", "Ezra", "Jer"):
            records.update({row["source_ref"]: row for row in parse_book(RAW / f"{book}.xml")})
        expected = {
            "Gen.31.47": "mul", "Jer.10.11": "arc",
            "Dan.2.3": "hbo", "Dan.2.4": "mul", "Dan.2.5": "arc",
            "Dan.7.28": "arc", "Dan.8.1": "hbo",
            "Ezra.4.7": "hbo", "Ezra.4.8": "arc",
            "Ezra.6.18": "arc", "Ezra.6.19": "hbo",
            "Ezra.7.11": "hbo", "Ezra.7.12": "arc",
            "Ezra.7.26": "arc", "Ezra.7.27": "hbo",
        }
        for reference, language in expected.items():
            with self.subTest(reference=reference):
                self.assertEqual(records[reference]["language"], language)
        aramaic_words = [t["text"] for t in records["Gen.31.47"]["tokens"] if t["language"] == "arc"]
        self.assertEqual(aramaic_words, ["יְגַ֖ר", "שָׂהֲדוּתָ֑א"])


if __name__ == "__main__":
    unittest.main()
