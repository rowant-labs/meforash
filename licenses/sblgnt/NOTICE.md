# SBL Greek New Testament attribution and changes

The Greek New Testament: SBL Edition. Michael W. Holmes, General Editor.
Copyright 2010 Logos Bible Software and the Society of Biblical Literature.

Source: [Faithlife/SBLGNT](https://github.com/Faithlife/SBLGNT), revision
[`c4d241a9c1c479a55b989ba35a4976c1d0b8052c`](https://github.com/Faithlife/SBLGNT/tree/c4d241a9c1c479a55b989ba35a4976c1d0b8052c).
The repository describes the text release as v1.2 (July 10, 2023); the selected
commit includes subsequent source maintenance dated January 19, 2025.

The upstream text is licensed under [Creative Commons Attribution 4.0
International](https://creativecommons.org/licenses/by/4.0/). The full license,
including its warranty disclaimer, is preserved in
[LICENSE-CC-BY-4.0.txt](LICENSE-CC-BY-4.0.txt). The upstream
[README](UPSTREAM-README.md) and [title metadata](UPSTREAM-TITLE.xml) preserve
the source's attribution and licensing statements. Relative links inside the
copied upstream README refer to files in the upstream repository.

This project converts the selected verse text and XML into JSONL. It preserves
Greek accents, spelling, and punctuation without Unicode normalization. The
audit field retains source apparatus anchors; the reading fields omit those
anchors. Double-bracketed supplements are separately identified, and the primary
reading field excludes them. Doubtful single-bracketed wording remains included
with its brackets. Paragraph and editorial metadata are added. These changes
are documented in [the preparation guide](../../docs/GREEK-PREPARATION.md) and
[the source manifest](../../manifests/sblgnt.json).

Retain this attribution, the license reference, and an account of modifications
with redistributed prepared text. This project is not endorsed by the source
editor, Society of Biblical Literature, Logos, or Faithlife. Original project
code has its own license; it does not replace the source text's CC BY 4.0 terms.
