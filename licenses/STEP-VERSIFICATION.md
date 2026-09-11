# STEP reference-mapping attribution

The derived [chat reference map](../manifests/chat-versification-v1.json) uses **STEPBible.org, based on work at Tyndale House Cambridge**, *TVTMS — Translators Versification Traditions with Methodology for Standardisation for Eng+Heb+Lat+Grk+Others*.

- Upstream: [STEPBible-Data](https://github.com/STEPBible/STEPBible-Data), commit `c5407786ede9b26a8998366524076f7c739dccdd`.
- Exact source: [pinned TVTMS file](https://github.com/STEPBible/STEPBible-Data/blob/c5407786ede9b26a8998366524076f7c739dccdd/Versification/TVTMS%20-%20Translators%20Versification%20Traditions%20with%20Methodology%20for%20Standardisation%20for%20Eng%2BHeb%2BLat%2BGrk%2BOthers%20-%20STEPBible.org%20CC%20BY.txt).
- Raw file SHA-256: `63058e0f20201af4bdaa7d830da5be8f493455d947c5f147d84840b33db9ddf8`.
- License identified in the selected file: [Creative Commons Attribution 4.0 International](https://creativecommons.org/licenses/by/4.0/). The derived mapping retains that attribution and applicable license; the project's Apache-2.0 license does not replace it.

The upstream header also asks users to direct others to the upstream download rather than redistribute the data, so they receive current data and notices. We preserve that request here. The full downloaded source stays in ignored local data; the project includes the bounded derived reference map and its reproducible preparation code in the publication candidate.

## Changes and scope

The preparation extracts only the final summary labeled English (NRSV, ESV, KJV etc) to Hebrew MT. It trims layout whitespace, standardizes book codes to the project's identifiers, and retains 2,021 unmarked whole-verse pairs. Fourteen split, empty or specially marked mappings are listed as blocked rather than approximated. Original line numbers identify those blocked rows. No biblical wording, lexical material or historical commentary is imported by this step.

The map supports passage lookup only. It does not change the training corpus, establish the wording of an original text, or claim universal agreement across English editions. Untabulated coordinates remain unchanged only when the resulting verse exists in the selected OSHB/WLC corpus. New Testament lookup uses SBLGNT coordinates separately.

The [preparation code](../bibleprep/versification.py) verifies the raw source hash before deriving the map. Further STEP lexical or historical imports remain separate proposals with their own file-level review.
