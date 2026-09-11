# Biblical source card

September 9, 2026. The project uses named editions and explicit reading layers. It does not combine them into an allegedly recovered original text. The current prepared inventory covers 66 book files; this scope does not settle differences between biblical canons.

| Source | Used layer | What it represents | Main limitation |
|---|---|---|---|
| Open Scriptures Hebrew Bible / Westminster Leningrad Codex | Hebrew and Aramaic main/ketiv text | A Masoretic textual base with explicit source coordinates | The medieval codex tradition is not a reconstruction of every earliest Hebrew/Aramaic reading. |
| SBL Greek New Testament, Michael W. Holmes | Selected main Greek text | A modern edited Greek New Testament | It is an editorial text, not an original manuscript or complete manuscript apparatus. |

## Provenance and licensing

OSHB is pinned at commit `3d15126fb1ef74867fc1434be1942e837932691f`; SBLGNT at `c4d241a9c1c479a55b989ba35a4976c1d0b8052c`. The source manifests retain acquisition references, file hashes, parsing decisions and notices. Preserve original Unicode without silent normalization.

The pinned OSHB license identifies the underlying WLC text as public domain. OSHB annotations and other work have separate terms. Candidate G's new excerpt extraction uses only the approved main/ketiv text and provenance, excluding morphology, lemmas, definitions, qere alternatives and notes. Rich processed records are not themselves proof that every field is cleared for every use. [Pinned OSHB license](https://github.com/openscriptures/morphhb/blob/3d15126fb1ef74867fc1434be1942e837932691f/LICENSE.md).

SBLGNT is available under CC BY 4.0. Keep its authorship, source/version and license information, and distinguish any project rendering or modifications from the Greek edition itself. [Official SBLGNT license](https://sblgnt.com/license/).

Training-use, application display and artifact redistribution are separate decisions. Project-authored English targets require their own review and must not reproduce restricted modern translations or lexical definitions. The initial source release includes acquisition/preparation code and notices, not a blanket redistribution grant for all locally collected materials.

## Coordinates and languages

Hebrew/Aramaic references use the source's Bible.MT coordinates. These do not always match common English chapter/verse numbering, notably in Daniel. Keep source coordinates explicit and use only verified mappings. Do not infer a verse's language from the book title alone: mixed-language boundaries require token-level checks. Retain ketiv and qere as distinct layers rather than silently replacing one with the other.

## Historical evidence still missing

Dead Sea Scrolls, Septuagint readings, manuscript transcriptions, other ancient versions, textual apparatus, lexical sources and historical-context studies are not comprehensively incorporated. The [historical-evidence work](HISTORICAL-EVIDENCE-MILESTONE.md) contains selected private drafts and limited use decisions. Those drafts are not automatically approved for chat, training or release.

An answer can explain what a supplied edition says while acknowledging that the excerpt cannot determine an earliest reading. Any claim about manuscript age, attestation, restoration, textual priority or ancient social context needs its own supporting evidence. Supplying an original-language verse alone does not establish those claims.
