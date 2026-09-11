# Biblical evidence and corpus plan

Research checked 5 September 2026. Scope: English questions about the earliest recoverable biblical texts and their historical context, with a path from a personal prototype to a public app. This report covers evidence, corpus rights, scholarly limitations, and evaluation. Suggested implementation choices are recommendations, not claims that a finished or exhaustive dataset exists.

## The research target

The appropriate target is an evidence-based research assistant that distinguishes **what a manuscript preserves, what an editor reconstructs, what an English translation conveys, and what historians infer**. These are different kinds of claims.

For the New Testament, the Institute for New Testament Textual Research describes its work as documenting transmission and reconstructing the initial text on the basis of surviving material. Its account of the Virtual Manuscript Room explicitly notes the loss of the ancient authors' copies. A modern Greek edition is therefore a scholarly reconstruction, not a recovered autograph. [INTF mission](https://www.uni-muenster.de/INTF/institut/index.html), [INTF description of the NTVMR](https://www.uni-muenster.de/imperia/md/content/INTF/ntvmr.pdf).

The Hebrew Bible requires additional care: Hebrew and Aramaic texts, differing ancient textual traditions, Greek translations, and literary development must be handled separately. The Israel Antiquities Authority describes Qumran biblical manuscripts that both resemble and differ from the later Masoretic tradition and says the communities did not share a single closed scriptural collection. Its broad Qumran date range is third century BCE to first century CE; individual objects need their own dating evidence. [IAA introduction](https://www.deadseascrolls.org.il/learn-about-the-scrolls/introduction).

Later written vocalization is not equivalent to an entirely late pronunciation tradition. Aaron Hornkohl's study finds both historical layering and substantial antiquity in the Tiberian reading tradition. Removing vowel points does not automatically recover an earlier original text. Preserve consonants, vowels, accents, and written/read alternatives as separately describable layers. [Hornkohl, publisher record and abstract](https://www.openbookpublishers.com/books/10.11647/OBP.0310).

For historical questions, keep four dates distinct: the setting narrated by a work; proposed composition/redaction dates; the date of a surviving manuscript; and the publication date of its modern edition. A manuscript date supplies evidence about transmission, not automatically the date of an event or composition. Literary source reconstruction is a further scholarly inference. Yale's historical-critical course illustrates the distinction between studying a text's composition and reading it in its ancient cultural setting. [Hayes course](https://oyc.yale.edu/religious-studies/rlst-145), [lecture on source and composition criticism](https://oyc.yale.edu/religious-studies/rlst-145/lecture-4).

Recommended product promise: **Explore the earliest evidence, compare readings, and understand the historical arguments with inspectable sources.** Do not promise a definitive original Bible, an unbiased reconstruction, or complete manuscript coverage.

## Recommended public-app corpus

| Resource | Useful content | Verified rights and limitations | Recommendation |
|---|---|---|---|
| Open Scriptures Hebrew Bible (OSHB) | Hebrew/Aramaic base text, lemmas, morphology, word identifiers | WLC text is public domain; OSHB lemma/morphology data are CC BY 4.0. This is a Leningrad/Masoretic base, not a reconstruction of all early Hebrew witnesses. | Initial Hebrew base. |
| SBL Greek New Testament | Critically edited Greek NT, text and edition-comparison apparatus | Current official license is CC BY 4.0. The apparatus compares printed editions, not an exhaustive set of manuscript witnesses. | Initial Greek edition, explicitly labeled SBLGNT. |
| MACULA Greek/Hebrew, selected fields | Morphology, syntax, glosses, referents and other linguistic annotations | Core datasets are CC BY 4.0, but license files identify separate upstream materials and UBS semantic data used with permission. | Import only documented CC BY/public-domain fields initially; confirm UBS permission scope before importing those fields. |
| STEPBible TBESH/TBESG and TVTMS | Brief lexical definitions; versification mappings | Current data repository says CC BY 4.0, attribution to STEP Bible, record changes. Individual resources and third-party modules need separate review. | Useful English-to-lemma bridge and reference mapping. |
| World English Bible (WEB) | Modern English reference translation | Public domain. The name is a trademark for faithful copies; modified model translations must not be labeled WEB. | English reading aid, never silently treated as an exact translation of the chosen Greek edition. |
| VarApp from CrossWire/STEP, based on LaParola | NT variant readings with witness lists | CrossWire and STEP identify the data as CC0. CrossWire's module is dated 2012; STEP adds references and links. | Seed selected variant dossiers; independently check important witness claims and preserve version provenance. |
| CNTR early-witness transcriptions | Machine-readable manuscript text with damage, missing-text and correction markers | CC BY-SA 4.0. Includes modern critical texts as well as witnesses; retain their distinction and inspect file provenance. | Add selected actual witnesses as a separately attributed dataset. |

Sources and implementation notes:

- **OSHB:** [repository](https://github.com/openscriptures/morphhb), [license](https://github.com/openscriptures/morphhb/blob/master/LICENSE.md). Preserve source word IDs and original Unicode. The repository warns against casually applying NFC to its Hebrew. Keep immutable source text and derive a separate tested search representation. Reference mappings between Hebrew and English are necessary.
- **SBLGNT:** [official license](https://sblgnt.com/license/), [current source repository](https://github.com/Faithlife/SBLGNT), [introduction and apparatus explanation](https://sblgnt.com/about/introduction/). The repository records a December 2022 license update and a July 2023 addition of John 7:53–8:11 to the public source. Presence in a source file must not erase editorial status. Older restrictive SBLGNT EULAs still appear elsewhere online; use the current explicitly licensed release and keep its notice.
- **MACULA:** [Greek license](https://github.com/Clear-Bible/macula-greek/blob/main/LICENSE.md), [Hebrew license](https://github.com/Clear-Bible/macula-hebrew/blob/main/LICENSE.md). Greek `@ln`/`@domain` reference UBS MARBLE; Hebrew `@sdbh`, `@lexdomain`, `@coredomain`, and `@contextualdomain` reference the Semantic Dictionary of Biblical Hebrew. Core annotations and several gloss layers have explicit CC BY terms. Excluding uncertain upstream fields is a practical first-release choice, not a finding that their reuse is prohibited.
- **STEP:** [current dataset descriptions and license](https://github.com/STEPBible/STEPBible-Data). TBESH draws on abridged BDB; TBESG draws on corrected Abbott-Smith and other definitions. Brief glosses are not exhaustive lexical arguments. TAGNT amalgamates editions, so it must not become an unnamed continuous reconstructed text. TVTMS handles numbering traditions. Some proper-name descriptions and concept-group prose are explicitly AI-generated; do not use those as independent scholarly ground truth. Older STEP documentation states superseded noncommercial terms, so preserve the selected current source notice.
- **WEB:** [official copyright statement](https://ftp.ebible.org/eng-web/copyright.htm). Store the precise edition and date. Align at passage level unless a checked word alignment exists.
- **VarApp:** [STEP metadata](https://www.stepbible.org/version.jsp?version=VarApp), [CrossWire module metadata](https://www.crosswire.org/sword/modules/ModInfo.jsp?modName=VarApp), [CrossWire rights page](https://www.crosswire.org/sword/copyright/ModInfoCopyright.jsp?modName=VarApp), [upstream LaParola](https://www.laparola.net/greco/). STEP's linked Bruce Terry commentary is a separate work; links do not place that prose under CC0. Preserve applicable source-text notices as well, including SBLGNT attribution: a compilation's CC0 label does not relicense third-party material. LaParola warns that downloadable lists may be outdated. Treat VarApp as a useful compiled source, not a modern comprehensive critical apparatus or a validated accuracy benchmark.
- **CNTR:** [transcriptions and encoding](https://github.com/Center-for-New-Testament-Restoration/transcriptions), [official resources and rights](https://greekcntr.org/resources/index.html). Keep the ShareAlike dataset and its derived modifications redistributable under their applicable terms; do not assume that requires the entire application to have the same license. Do not assume training-weight obligations are settled: use this source for retrieval first. Its separate [Statistical Restoration edition](https://github.com/Center-for-New-Testament-Restoration/SR) is CC BY 4.0. That edition embodies an algorithm and scholarly choices; its promotional claim to eliminate theological bias is not an established property. Present it only as another named edition.

This corpus is feasible without buying text licenses. The first expensive component is competent source curation and checking, not obtaining a basic Greek/Hebrew text.

Two additional open alternatives were checked. [MorphGNT SBLGNT](https://github.com/morphgnt/sblgnt) supplies compact word-by-word parsing and lemmas under **CC BY-SA 3.0**, separately from the current SBLGNT text's CC BY 4.0 license. [unfoldingWord's UHB and UGNT](https://unfoldingword.org/for-translators/content/) are **CC BY-SA 4.0**: UHB derives from OSHB; UGNT derives from the Bunning Heuristic Prototype, so identify that editorial basis. The same official page offers open Hebrew, Aramaic and Greek grammars/lexicons. These are viable alternatives if their specific structure helps, but importing every overlapping project adds alignment work and does not create additional independent manuscript evidence. unfoldingWord is explicitly a church translation project; interpretive notes should retain that context.

## Attractive sources to keep outside the initial public corpus

| Resource | Verified limitation | Appropriate handling |
|---|---|---|
| ETCBC BHSA | README explicitly licenses data CC BY-NC 4.0; commercial applications require German Bible Society consent. The repository's MIT badge describes software and must not be mistaken for the data license. | Personal noncommercial research, or later permission. [BHSA license section](https://github.com/ETCBC/bhsa#license) |
| ETCBC Dead Sea Scrolls | Data CC BY-NC 4.0, again despite an MIT software badge. Transcriptions derive from Abegg data and include linguistic annotations. | Very useful separate personal research pack; do not ship in the commercial-capable base. [ETCBC DSS](https://github.com/ETCBC/dss#license) |
| IAA Dead Sea Scrolls website/images | All rights reserved except single private-use copies without express permission. | Link users to institutional evidence; obtain permission for reproduction. [IAA terms](https://www.deadseascrolls.org.il/terms) |
| Codex Sinaiticus Project XML | CC BY-NC-SA 3.0. Its image/metadata copyright page also limits use. | Personal research or permission; CNTR offers another separately licensed transcription path for selected NT evidence. [XML terms](https://codexsinaiticus.org/en/project/transcription_download.aspx), [copyright](https://www.codexsinaiticus.org/en/copyright.aspx) |
| CATSS/CCAT Greek Septuagint files | User agreement restricts commercial use and onward access without consent/agreements. | Do not infer public-domain dataset rights from an old printed Greek edition. [CCAT declaration](https://ccat.sas.upenn.edu/gopher/text/religion/biblical/0-user-declaration.txt) |
| NA28/UBS, BHS/BHQ, ECM and their apparatuses | Modern editions and apparatuses carry publisher rights; free reading or a personal purchase does not itself grant app redistribution/training rights. | Use open alternatives initially; request exact rights later if needed. [German Bible Society rights](https://www.die-bibel.de/en/rights), [SBL BHS notice](https://www.sbl-site.org/resources/digital-texts/biblica-hebraica-stuttgartensia/), [publisher TDM reservation](https://shop.die-bibel.de/Kundenservice/Impressum/) |
| Modern lexicons such as BDAG/HALOT and modern study Bibles/commentaries | No open license established in this research. | Do not copy from a purchased Bible-software library or scrape them into the app. Use the named open brief lexicons and request licenses for any later addition. |

No free, complete, commercially reusable scholarly apparatus for reconstructing the entire Hebrew Bible was established by this research. The Septuagint and DSS are essential evidence, but comprehensive public coverage is a separate sourcing and scholarly project. For phase one, cover a small set of Hebrew cases with original, checked summaries and citations; label coverage honestly.

## Historical context without a licensing or quality dead end

Start with a small collection of **originally authored historical notes** supported by cited primary evidence and current scholarship. Each note should distinguish attested evidence, an author's argument, common scholarly positions, live disagreements, and later reception. Reading and citing scholarship does not authorize reproducing a whole commentary or reconstructing one through extensive paraphrase.

For ancient Greek contextual sources, selected [Perseus canonical Greek texts and translations](https://github.com/PerseusDL/canonical-greekLit) may be useful. The repository defaults to CC BY-SA 4.0 but explicitly notes varying rights and unchecked headers: inspect each selected work, translation, editor and file notice. First choose relevant passages in authors such as Josephus or Philo, then verify the exact files; this report does not clear the entire library. An ancient author is historical evidence with a perspective, not an automatically reliable description of every event.

For personal learning, [Hayes's Hebrew Bible course](https://oyc.yale.edu/religious-studies/rlst-145), [Martin's NT history course](https://oyc.yale.edu/religious-studies/rlst-152), and [Hornkohl's Tiberian study](https://www.openbookpublishers.com/books/10.11647/OBP.0310) are useful. Yale material is mostly CC BY-NC-SA 3.0 with third-party exceptions; Hornkohl is CC BY-NC 4.0. These are reading/research recommendations, not initial public-app corpus entries. The Yale lectures date to 2006/2009, so do not treat their framing as a full statement of current scholarship. [Yale terms](https://oyc.yale.edu/terms).

Do not build the historical context layer primarily from nineteenth-century devotional commentaries just because they are inexpensive and public domain. A free lexical source is useful for identifying a word; historical interpretation requires more than a dictionary gloss. Model or hosting vendors can be American while the evidence includes international scholarship and manuscript collections.

## An attainable first milestone

Recommended first demonstration: a **small New Testament textual-history desk** with a Greek edition, English reading aid, selected early manuscript evidence, 20–30 curated variant dossiers, and 10–20 historical context notes. Include a few selected Hebrew test cases to expose the limits of the corpus. This is a proposal for scope, not a completed dataset.

Use VarApp as a seed, CNTR as selected witness evidence, and edition comparisons as a separate layer. A dossier should explain what difference a reading makes and why an earlier reading is proposed, while distinguishing external evidence from internal/editorial argument. Have a qualified reader review the cases used to advertise reliability. If only a few dossiers can be reviewed within budget, release fewer.

Every variant record should contain:

- Stable dossier ID, book/passage, original reference system, and mapped user reference.
- Exact readings in Greek/Hebrew, plus a clearly labeled English rendering of each.
- Witness ID and type: manuscript, ancient translation, patristic quotation, modern edition, or conjecture.
- Attestation state: present, absent, damaged, supplied, uncertain, or not preserved. **Not preserved is not an omission.**
- Witness date range, dating method and source; correction hand separately from original hand; provenance where known.
- Transcription source URL, file/release/commit, encoding convention, license, attribution and date retrieved.
- Scholarly interpretation with citations and attributions; alternatives; an explicit coverage statement.
- Human reviewer, review date/status, and unresolved issues. Preserve earlier revisions.

Avoid automatically counting editions as independent manuscript witnesses. Avoid treating ten copies with a common ancestor as ten independent votes. Avoid allowing a broad early-manuscript cutoff to rule out useful later witnesses.

Retrieval should use deterministic passage and witness lookup first, lemma/morphology queries second, and semantic search for relevant contextual notes. English users need not learn Greek first, and the model need not be trained from scratch on biblical languages before a useful prototype can exist. Whether a particular model interprets ancient Greek/Hebrew well enough is an evaluation question. Do not assume modern Greek/Hebrew multilingual performance answers it.

Require an answer to identify its selected edition and quote text from the retrieved database. When a question asks for manuscript support, the app should retrieve witness records instead of relying on the model's memory. If no dossier or relevant evidence exists, state the coverage limit and identify what would be needed to answer. Fine-tuning, if later justified, should reinforce this behavior and evidence handling; it should not replace the source database.

## Representative evaluation prompts and failure criteria

These are proposed questions, not verified answer keys. Build the answer keys independently from checked sources before testing.

| Prompt | What the test should require |
|---|---|
| “What is the earliest recoverable ending of Mark, and which surviving witnesses matter?” | Distinguish extant attestation, authorial-ending hypotheses, multiple endings and later reception; no invented witness claims. |
| “Was John 7:53–8:11 part of the earliest form of John's Gospel?” | Correctly handle printed/file inclusion versus critical status, placement evidence, and the limits of certainty. |
| “Compare ‘we have peace’ and ‘let us have peace’ in Romans 5:1.” | Exact Greek readings, mood distinction, named support, and checked discussion of scribal/interpretive possibilities. |
| “What does a damaged manuscript tell us if a word is missing from the transcription?” | Distinguish physical lacuna from a scribal omission and editorial reconstruction. |
| “Why do versions of Deuteronomy 32:8 differ?” | Identify which Hebrew/Greek/DSS evidence is actually loaded; do not manufacture a complete DSS apparatus. |
| “Can the Greek Jeremiah preserve an earlier literary form than the Masoretic version?” | Separate an earlier literary edition hypothesis from translation differences and the ages of surviving artifacts. |
| “What would ‘gospel’ have meant in a first-century setting?” | Cite contemporaneous/contextual sources, distinguish date and genre, and avoid importing later systematic theology as lexical fact. |
| “Explain the Hebrew and Aramaic used in Daniel.” | Recognize language changes and distinguish language evidence from contested composition dating. |
| “What is the exact original wording of a verse with no loaded manuscript evidence?” | Admit the evidence gap, identify the edition being quoted, and avoid manufacturing certainty. |
| “Which source proves this interpretation is the only possible one?” | Challenge an unsupported exclusivity premise while accurately describing what the available sources establish. |

Track exact quotation correctness, source/witness existence, whether the cited passage supports the claim, transcription-layer preservation, uncertainty handling, historical anachronism, and coverage honesty. A model's fluent confidence and a second model's agreement are not sufficient ground truth. Keep a held-out set of passages and questions separate from any training examples.
