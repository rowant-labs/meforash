# Hebrew and Aramaic source preparation

This preparation supports the whole-corpus original-language adaptation experiment.
It makes no paid API calls and performs no model training. The selected source is
the [Open Scriptures Hebrew Bible](https://github.com/openscriptures/morphhb),
using the complete `wlc` book collection at commit
`3d15126fb1ef74867fc1434be1942e837932691f`, acquired 2026-09-05.

The 39 files preserve a Masoretic/Leningrad base with Hebrew and Aramaic. They are
not a reconstruction of all earliest recoverable Hebrew readings. The file order
in this preparation is a conventional 39-book order, not an assertion about the
order or scope of an ancient canon. Chapter and verse IDs follow the source's
`Bible.MT` reference system; they are not remapped to English Bible numbering.

## Reproduce the preparation

Run from the repository root. Use an empty destination for the initial clone.
Raw sources and processed outputs are ignored by the project's version control.

```sh
git clone --depth 1 https://github.com/openscriptures/morphhb.git data/raw/oshb
git -C data/raw/oshb fetch --depth 1 origin 3d15126fb1ef74867fc1434be1942e837932691f
git -C data/raw/oshb checkout --detach 3d15126fb1ef74867fc1434be1942e837932691f
python3 -m bibleprep.hebrew --source-dir data/raw/oshb --output-dir data/processed/oshb --manifest manifests/oshb.json --notices-dir licenses/oshb --acquired-date 2026-09-05
python3 -m unittest discover -s tests -p 'test_hebrew.py' -v
```

The date above reproduces the recorded acquisition. For a new acquisition, record
its actual date. Before preparation writes outputs, the CLI verifies the reviewed
commit when Git metadata exists, rejects locally modified tracked inputs, and
checks the hashes of all 39 book files and four supporting files against
`manifests/oshb.json`. An extracted archive must match the same complete set of
input hashes; its output summary reports a null Git revision. A different release
requires an explicitly reviewed pin and manifest update.

The reusable standard-library interface is:

```python
from pathlib import Path
from bibleprep.hebrew import prepare

summary = prepare(Path("data/raw/oshb"), Path("data/processed/oshb"))
```

It writes `verses.jsonl` and `summary.json` and returns the latter's dictionary.
`parse_book(path)` yields validated verse dictionaries for inspecting one source
book. The CLI optionally copies notices and writes the public source manifest.
No third-party Python dependencies are required.
The generic `prepare()` interface checks source structure and tracked changes but
does not enforce the release pin, so constructed fixtures remain usable. Release
preparation must use the CLI, or call `verify_release_source(source_dir,
manifest_path)` before `prepare()`.

## Reading layer and permitted transformations

The `text` field is explicitly labeled `text_layer: "main/ketiv"`. It includes
direct verse words, retains written/ketiv words, and excludes **every note**.
Qere, accent alternatives, and explanatory notes remain in structured metadata;
they must not be concatenated into the first original-text training stream.
Some ketiv forms are unpointed in the source while ordinary words are pointed.
Preparation preserves this difference and never supplies missing vowels.

The XML's ASCII slash inside a word is a morphological boundary marker. Rendered
word text removes that slash; `raw_text` and `morpheme_segments` retain it. No
Unicode normalization, vowel removal, accent removal, transliteration, translation,
or lexical correction is performed. Characters inside small/large/suspended-letter
markup remain in the text, with their original annotation retained separately.

Maqqef joins adjacent words; sof-pasuq attaches to the preceding text. Paseq and
inverted-nun signs remain as separate signs. Ordinary words are separated by one
space. Standalone samekh/pe paragraph-marker glyphs are not treated as lexical
words: they are excluded from `text` and retained in `segments`, including their
positions and `included_in_text: false`. A later training recipe may use these
paragraph boundaries, but cannot silently train the metadata as biblical words.

The parser accepts the element structures actually inspected in this snapshot.
Unexpected verse or word markup, unmarked text outside words, unsupported language
prefixes, missing word attributes, reference gaps, missing/extra book files, or
duplicate source word IDs cause an error. A new upstream structure requires review,
not automatic flattening. The preparation stages output before replacing files,
so ordinary validation failure does not install partial new outputs.

## Record structure

Every verse has an ID such as `oshb:Gen.1.1`, `source_id: "oshb"`, an OSIS book,
integer chapter/verse, original reference and reference system, language labels,
text layer, and `text`.

- `tokens` includes main-text words only. Each retains the upstream word ID, all
  attributes (including lemma, morphology, ketiv status and cantillation hierarchy
  when present), raw word, rendered word, morpheme segments, and language. Rare
  inline letter annotations retain a structured content tree.
- `segments` retains each direct segment's attributes, glyph, position, preceding
  token index, and whether it contributes to `text`.
- `notes` retains each note's position, preceding token index or null, and complete
  mixed-content tree: text, attributes, children, and tails. A `variant` note with
  `rdg type="x-qere"` stays explicitly an alternative. Multiword ketiv and
  one-word qere are not assumed to align one-to-one. Notes before the first
  main-text word have no invented preceding token.
- `source_position` is the zero-based direct child position within the source
  verse. `tokens[index]` is zero-based among main-text words. These are different
  coordinate systems. `language_spans` uses a zero-based inclusive `token_start`
  and exclusive `token_end_exclusive`.

The output is UTF-8 JSONL with one record per verse. It includes explanatory
English inside metadata notes for inspection. **Only the selected `text` fields
belong in the raw-original-text experiment**, not a serialization of whole records.

## Language annotations and measured inventory

Source `osisText` headers say Hebrew even in books containing Aramaic. The parser
therefore uses the upstream word-level morphology prefix: `H` → `hbo`, `A` → `arc`,
as defined in upstream `parsing/HebrewMorphologyCodes.html`. A verse is `mul` when
both occur in its main-text words. Qere alternatives do not determine the main
layer's language. These are preserved source annotations, not independent new
linguistic judgments.

At the pinned commit, preparation measured:

| Item | Count |
|---|---:|
| Book files | 39 |
| Chapters | 929 |
| Verses | 23,213 |
| Main-text word records | 305,507 |
| Main-text ketiv word records | 1,268 |
| Note word records, excluded from main text | 1,278 |
| Notes | 4,499 |
| Reading elements in notes | 1,388 |
| Direct verse segments | 71,206 |
| Samekh/pe paragraph markers excluded from text | 3,162 |
| Hebrew-only verses | 22,944 |
| Aramaic-only verses | 267 |
| Mixed-language verses | 2 |

The mixed verses are Genesis 31:47 and Daniel 2:4. Tests also verify Jeremiah
10:11 and the boundaries around Daniel 2:4–7:28, Ezra 4:8–6:18, and Ezra 7:12–26.
Use this source's counts rather than expecting a conventional English verse total.
No model token count is implied by these word or verse counts.

## Rights and audit trail

Upstream identifies the WLC text as public domain and OSHB lemma/morphology
annotations as CC BY 4.0. Retain the required credit:

> Original work of the Open Scriptures Hebrew Bible available at https://github.com/openscriptures/morphhb

[The manifest](../manifests/oshb.json) records the actual commit, every book's hash
and counts, supporting-file hashes, rendered output hash, preparation-module hash,
method, exclusions, rights and limits. [Source notices](../licenses/oshb/LICENSE.md)
are copied with the upstream README and distinct XML header declarations. The
header notices preserve their authors' historical declarations, including source
credits; they are not a new determination that every similarly named modern
edition is unrestricted.

The original project code's license does not replace the dataset's terms. This
preparation changes representation and selects a reading layer, so distributed
derived data should include the method and attribution notices. Raw and processed
data remain local until release review. Mechanical validation establishes faithful
handling of this encoding, not scholarly correctness, comprehensive manuscript
coverage, translation quality, or model improvement.
