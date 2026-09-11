import json
from pathlib import Path
import unittest

from bibleprep.chat_sources import PassageLibrary
from bibleprep.versification import prepare

ROOT = Path(__file__).resolve().parents[1]


class ChatSourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.library = PassageLibrary(ROOT)

    def lookup(self, question):
        return self.library.select([{"role": "user", "content": question}])

    def test_entire_named_corpus_and_all_map_targets(self):
        self.assertEqual(self.library.count, 31152)
        self.assertEqual(len(self.library.mapping["mappings"]), 2021)
        self.assertEqual(len(self.library.mapping["blocked"]), 14)

    def test_known_english_to_hebrew_and_aramaic_coordinates(self):
        for question, expected in (("Psalm 51:10", "oshb:Ps.51.12"),
                                   ("Joel 2:28", "oshb:Joel.3.1"),
                                   ("Exodus 8:5", "oshb:Exod.8.1"),
                                   ("Daniel 6:22", "oshb:Dan.6.23")):
            with self.subTest(question=question):
                sources, _ = self.lookup(question)
                self.assertEqual([s["id"] for s in sources], [expected])

    def test_direct_mt_is_bound_to_individual_reference(self):
        sources, _ = self.lookup("Compare English Psalm 51:10 with MT Psalm 51:12")
        self.assertEqual([s["id"] for s in sources], ["oshb:Ps.51.12"])
        sources, _ = self.lookup("Psalm 51:10 (MT)")
        self.assertEqual(sources[0]["id"], "oshb:Ps.51.10")
        for question in ("oshb:Ps.51.12", "OSHB: Psalm 51:12", "Psalm 51:12 in Hebrew numbering"):
            sources, _ = self.lookup(question)
            self.assertEqual(sources[0]["id"], "oshb:Ps.51.12")

    def test_split_and_marked_mappings_never_silently_use_identity(self):
        for question in ("Numbers 26:1", "Psalm 13:5", "Psalm 38:16", "Nehemiah 7:69"):
            sources, notes = self.lookup(question)
            self.assertFalse(sources)
            self.assertTrue(any("uncertain" in n for n in notes))

    def test_unicode_and_editorial_supplements_are_preserved(self):
        sources, _ = self.lookup("John 7:53")
        self.assertTrue(sources[0]["text"].startswith("⟦"))
        self.assertEqual(sources[0]["editorial_status"], "supplement_only")
        self.assertEqual(sources[0]["editorial_notes"][0]["status"], "double_bracketed")
        sources, _ = self.lookup("Genesis 1:1")
        self.assertEqual(sources[0]["text"], self.library.rows[("Gen", 1, 1)]["text"])
        self.assertIn("main/ketiv", sources[0]["editorial_status"])

    def test_ranges_aliases_and_two_passages(self):
        sources, _ = self.lookup("1 Cor. 13:4–7 and John 1:1")
        self.assertEqual(len(sources), 5)
        self.assertEqual(sources[0]["id"], "sblgnt:1Cor.13.4")
        self.assertEqual(sources[-1]["id"], "sblgnt:John.1.1")

    def test_unsupported_syntax_never_becomes_a_shorter_valid_prefix(self):
        for question in ("John 3:16-17a", "John 3:16a", "John 3:16,17", "John 3:16-4:2"):
            sources, notes = self.lookup(question)
            self.assertFalse(sources, question)
            self.assertTrue(any("unsupported" in n or "crossing" in n for n in notes))

    def test_absent_verse_does_not_create_an_edition_reading(self):
        sources, notes = self.lookup("John 5:4")
        self.assertFalse(sources)
        self.assertTrue(any("unavailable" in n for n in notes))

    def test_followup_inherits_only_actual_prior_reference(self):
        sources, notes = self.library.select([
            {"role": "user", "content": "Explain John 1:1"},
            {"role": "assistant", "content": "A constructed response."},
            {"role": "user", "content": "What is the final clause doing?"}])
        self.assertEqual(sources[0]["id"], "sblgnt:John.1.1")
        self.assertTrue(any("earlier conversation" in n for n in notes))

    def test_broad_question_does_not_fabricate_retrieval(self):
        sources, notes = self.lookup("How can I be more patient with people?")
        self.assertEqual(sources, [])
        self.assertTrue(any("No exact source passage" in n for n in notes))

    def test_mapping_preparation_reproduces_and_rejects_changed_source(self):
        raw = (ROOT / "data/raw/step-versification/TVTMS.txt").read_bytes()
        self.assertEqual(prepare(raw), json.loads((ROOT / "manifests/chat-versification-v1.json").read_text()))
        with self.assertRaises(ValueError):
            prepare(raw + b"\n")


if __name__ == "__main__":
    unittest.main()
