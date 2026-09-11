# STEP lexical source review

Checked September 7, 2026 against the exact files below. The [lexical preparation](../bibleprep/lexical_preview.py) creates a private research sample, with no app or training integration.

Both files are pinned to STEPBible-Data commit `c5407786ede9b26a8998366524076f7c739dccdd`. Their general notice attributes the work to STEPBible.org, based on work at Tyndale House Cambridge, under [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). The headers also request directing others to the upstream distribution instead of redistributing the data; that request is retained here.

| File | Exact artifact SHA-256 | Component finding |
|---|---|---|
| [TBESH Hebrew brief lexicon](https://github.com/STEPBible/STEPBible-Data/blob/c5407786ede9b26a8998366524076f7c739dccdd/Lexicons/TBESH%20-%20Translators%20Brief%20lexicon%20of%20Extended%20Strongs%20for%20Hebrew%20-%20STEPBible.org%20CC%20BY.txt) | `464dccadd95fd8620dd05fa0d7a4caba58ec3c4d5db3ebf38e43d046ca25b591` | Line 6 identifies an Online Bible abridged-BDB basis and requests separate permission for applying its definitions. The generic repository notice does not resolve that component-specific instruction. No Hebrew definitions are imported into the sample. |
| [TBESG Greek brief lexicon](https://github.com/STEPBible/STEPBible-Data/blob/c5407786ede9b26a8998366524076f7c739dccdd/Lexicons/TBESG%20-%20Translators%20Brief%20lexicon%20of%20Extended%20Strongs%20for%20Greek%20-%20STEPBible.org%20CC%20BY.txt) | `312f723d7b8ef263bbdfb0451c9b8057125804dfff390b6f8544cff2a84b57f4` | The header identifies Abbott-Smith, Middle Liddell and STEP scholarship. The bounded sample retains only identifier, headword, transliteration, morphology and gloss fields; long definitions are omitted. |

Ten Greek metadata rows are retained for six extended Strong identifiers relevant to the Mark 1:1 dossier. Multiple Jesus/Joshua name entries remain separate; the preparation does not choose a referent or attach a lexicon sense automatically to a verse. Exact row locators and hashes preserve the selection. No source Unicode or field text is normalized; the long-definition column is removed.

Raw downloads and the derived sample remain in ignored local data. The code and these provenance/rights findings are publication candidates. Any later data release must retain attribution and the change notice, and reconsider each included component. App display, training and adapter-release decisions remain pending. Lexical glosses do not establish an ancient author's intended meaning or settle a theological interpretation.
