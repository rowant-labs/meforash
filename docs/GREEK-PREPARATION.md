# Greek source preparation

The initial Greek corpus is the complete 27-book SBL Greek New Testament,
obtained from the [official Faithlife repository](https://github.com/Faithlife/SBLGNT).
It is a named modern critical edition, not an ancient manuscript or a recovered
autograph. No model training or paid API is involved in this preparation.

## Pinned source and rights

The source revision is
[`c4d241a9c1c479a55b989ba35a4976c1d0b8052c`](https://github.com/Faithlife/SBLGNT/tree/c4d241a9c1c479a55b989ba35a4976c1d0b8052c),
dated January 19, 2025, acquired September 5, 2026. The upstream README identifies
text release v1.2 and records its July 2023 addition of John 7:53–8:11. Use this
exact revision rather than whatever a branch contains later.

The current official source is CC BY 4.0. The repository's full license,
copyright notice, and editor attribution are preserved under
[licenses/sblgnt](../licenses/sblgnt/NOTICE.md). This preparation does not use the
older restrictive SBLGNT EULA or assume that the project's software license
relicenses the Greek text. [Official license](https://sblgnt.com/license/)

[manifests/sblgnt.json](../manifests/sblgnt.json) records the source revision,
58 input/support-file SHA-256 hashes, sizes, rights evidence, complete book
inventory, observed editorial groups, preparation choices, and output hashes.
The inputs are 27 verse-text files, 27 XML files, the upstream README, About,
license, and title metadata. Apparatus notes in `data/sblgntapp` remain in the
ignored source checkout but are not imported into the prepared corpus.

## Reproduce

From the project root, obtain the source if it is not already present:

```sh
git clone https://github.com/Faithlife/SBLGNT.git data/raw/sblgnt
git -C data/raw/sblgnt checkout --detach c4d241a9c1c479a55b989ba35a4976c1d0b8052c
```

Then run the standard-library-only preparation and its fixtures:

```sh
python3 -m bibleprep.greek
python3 -m unittest discover -s tests -p test_greek.py -v
```

The CLI accepts `--source-dir` and `--output-dir`. The Python entry point is
`bibleprep.greek.prepare(source_dir: pathlib.Path, output_dir: pathlib.Path) -> dict`.
The source directory is the upstream repository root; the output directory
receives `verses.jsonl` and `summary.json` directly. Preparation verifies all
manifest input hashes before writing output. A source archive without Git
metadata also works when its files match the manifest.

Raw and prepared data stay in ignored `data/raw/` and `data/processed/`
directories. The code, fixture tests, notices, and manifest are shareable project
material. Reproducing files does not publish them automatically.

## Record contract

Each verse has an ID such as `sblgnt:Matt.1.1`, `source_id: "sblgnt"`, an OSIS
book abbreviation, integer chapter/verse, and `language: "grc"`.

| Field | Meaning |
|---|---|
| `source_text` | The exact payload after the source line's tab, without its line ending. Includes apparatus anchors and any trailing layout spaces. |
| `text` | The edition's reading with apparatus-anchor symbols and attached numeric disambiguators removed and boundary whitespace trimmed. Greek characters, interior spacing, punctuation, and editorial square/double brackets remain. |
| `main_text` | `text` with double-bracketed supplements removed. Doubtful single-bracketed text remains with its brackets. May be empty for supplement-only verses. |
| `alternatives` | Double-bracketed supplement fragments. Each contains `text`, `kind`, `editorial_status`, `group_id`, local `start`/`end`, `opens_here`/`closes_here`, and the whole group's `source_span`. |
| `editorial_spans` | Metadata for both single- and double-bracketed groups, including continuations across verses and chapters. |
| `apparatus_markers` | Removed symbols and their exact offsets in `source_text` and `text`; the original apparatus annotations remain separate upstream. |
| `paragraphs` | XML paragraph numbers and zero-based word ranges within this source verse. Some paragraphs begin within a verse. |
| `word_count` | Count of XML word elements, including supplementary words. This is not a model-token count. |
| `source_ref`, `source_file`, `source_line` | Original XML verse reference and relative source-text location. |

All offsets are Unicode code-point indices, starting at zero with an exclusive
end. Editorial offsets and `source_span` refer to `text`, not UTF-8 bytes,
tokenizer positions, `source_text`, or `main_text`. Apparatus `source_start` and
`source_end` refer to `source_text`. No NFC/NFD normalization is applied.

The paired XML and text sources must agree on verse inventory and the exact
sequence of Greek letters, combining marks, and elision apostrophes. Punctuation
comes from the official verse-text format. XML supplies word and paragraph
structure; XML formatting whitespace is not treated as scripture.

## Editorial handling

The edition's introduction distinguishes apparatus anchors from square brackets
marking doubtful wording. Its apparatus compares printed editions and should
not be mistaken for a complete manuscript apparatus. This importer removes
apparatus anchors only from reading fields and keeps their audit information.
It does not substitute another edition's reading. [Editorial introduction](https://sblgnt.com/about/introduction/)

The selected source encloses three supplements in double brackets:

| Supplement | Source location | Preparation |
|---|---|---|
| Shorter ending of Mark | Appended inside Mark 16:8 | Preserve the primary verse in `main_text`; put the appended text in one alternative fragment. |
| Longer ending of Mark | Mark 16:9–20 | Keep 12 source verse records; place their wording in one supplement group with 12 fragments. |
| Pericope adulterae | John 7:53–8:11 | Keep all 12 source verse records, tracking one supplement group across the chapter boundary. |

Use nonempty `main_text` for the primary corpus and, if supplements are included,
assemble each `alternatives` group in source order as a separately identified
sequence. A supplement's presence in this edition's source files must not
silently imply the status of unbracketed primary text. Do not concatenate
`text`, `main_text`, and `alternatives`: that duplicates the same Greek wording.

Six single-bracketed doubtful-wording groups span seven verse records: Luke
22:19–20, 24:40, 24:51, 24:52; Ephesians 1:1; and Colossians 1:20. They remain in
`main_text`; excluding them would silently decide for omission. If a training
window splits a bracket group, its metadata must carry the continuation status
so an isolated closing bracket is not the only indication of doubt.

## Measured inventory and checks

The pinned source contains 27 books, 260 chapters, 7,939 verse records, and
137,741 XML word elements. There are 7,915 nonempty primary verse records,
25 supplementary fragments in three groups, and six doubtful-wording groups.

Fifteen internal verse-number gaps are reported rather than filled: Matthew
17:21, 18:11, 23:14; Mark 7:16, 9:44, 9:46, 11:26, 15:28; Luke 17:36, 23:17;
John 5:4; Acts 8:37, 15:34, 24:7, 28:29. An internal-gap calculation cannot detect
an absent verse beyond a chapter's final source number. Preserve the manifest's
chapter maxima and source versification; for example, this source's 3 John
has 15 numbered verses. Do not infer missing text from an English edition's
verse totals.

The fixture tests check Unicode preservation, numbered apparatus anchors,
cross-chapter and cross-verse brackets, both Mark endings, retained doubtful
wording, absent and duplicate references, XML/text spelling disagreements,
unbalanced brackets, deterministic output, and rejection of changed pinned
files. These checks establish preparation behavior, not the historical truth
of every editorial decision or any improvement in a model.
