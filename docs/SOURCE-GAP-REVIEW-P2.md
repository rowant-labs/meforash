# First source-gap follow-up

Checked September 8, 2026. The first P2 research increment adds **three private follow-up records with thirteen findings**, covering Genesis 4:8, Isaiah 53:11 and Daniel 2:4b–9. It improves traceability of early-witness evidence; it does not establish original wording or improve measured model accuracy. Retained fine-tuned B and the private chat are unchanged.

Two GPT 5.6 Sol workers performed the bounded research. The primary agent checked key transcription passages, the Daniel source encoding and both Greek print-page scans, reviewed the findings and integrated the records. These are AI research checks, not specialist certification.

## What the sources now support

| Record | Advance | Limits |
| --- | --- | --- |
| HT01 · Genesis 4:8 | The dated 4Q2/4QGenb transcription locates the shorter sequence at fragment 3 i, lines 8–9. Von Gall's Samaritan edition prints the field invitation at printed page 6. | A scholarly transcription and an edited text have been checked. No ancient manuscript image or full Samaritan apparatus was collated. Originality remains a separate judgment. |
| HT07 · Isaiah 53:11 | The word commonly translated “light” is located in the transcriptions of 1QIsaa column 44 line 19, 1Q8/1QIsab column 23 line 22, and damaged 4Q58/4QIsad fragment 8 line 20. | In 4Q58, the first letter is unmarked, the second uncertain, and the third restored. These are not three equally intact readings. No manuscript hands or correction layers were independently inspected. |
| AT03 · Daniel 2:4b–9 | The pinned OSHB encoding identifies the Hebrew-to-Aramaic boundary exactly. 1Q71 supplies partial transcription evidence for verses 4b–6, and 4Q112 for verse 9. Swete's two Greek Daniel texts are separately identified. | The language label in 1Q71 is restored. Neither checked fragment supplies a line for verses 7–8; that is a preservation gap, not evidence of omission. Greek agreement does not itself identify a Semitic exemplar. |

HT01 sources: [Qumran-Digital 4Q2](https://lexicon.qumran-digital.org/transcriptions/4Q2/2025-03-11/index.html), [von Gall's printed edition](https://ia600809.us.archive.org/26/items/derhebrischepent01gall/derhebrischepent01gall.pdf). At the invitation's insertion point, 4Q2 transcribes a partly surviving shorter sequence; the entire sequence must not be described as restored.

HT07 sources: [Qumran-Digital 1QIsaa](https://lexicon.qumran-digital.org/transcriptions/1QIsa%5Ea%5E/2025-08-25/index.html), [1Q8](https://lexicon.qumran-digital.org/transcriptions/1Q8/2025-08-25/index.html?v=2025-08-25), [4Q58](https://lexicon.qumran-digital.org/transcriptions/4Q58/2022-10-14/index.html?v=2022-10-14). The addendum also preserves Tov's report of Seeligmann's contrary reconstruction favoring the shorter reading; witness counts do not automatically establish originality. [Tov, internal page 14](http://www.emanueltov.info/docs/papers/05.isaiah.2008.pdf?v=1.0). That PDF was retrieved over HTTP after the HTTPS endpoint failed certificate-name validation; its local hash records the retrieved bytes, not authenticated transport.

AT03 sources: [pinned OSHB Daniel](https://github.com/openscriptures/morphhb/blob/3d15126fb1ef74867fc1434be1942e837932691f/wlc/Dan.xml), [1Q71 fragment 1 ii lines 3–8](https://lexicon.qumran-digital.org/transcriptions/1Q71/2026-05-21/index.html?v=2026-05-21#c270625-i270640), [4Q112 fragment 1 ii lines 1–2](https://lexicon.qumran-digital.org/transcriptions/4Q112/2024-07-30/index.html#c361212-i361212), Swete's [Old Greek page 502](https://archive.org/details/theoldtestamenti03swetuoft/page/n526/mode/1up) and [Theodotion page 503](https://archive.org/details/theoldtestamenti03swetuoft/page/n527/mode/1up). The latter are printed-edition scans, not ancient manuscript images.

## Artifacts and validation

The [follow-up inventory](../manifests/source-gap-followups-p2-v1.json) binds the six private JSON/Markdown files under `data/evidence/followups/p2-v1/`. Fourteen newly retained source files remain under ignored `data/raw/evidence-p2-v1/`; three previously retained source files are also referenced. Each finding names its original queue entries, draft fields, evidence level, source locator, hash where available and limitations. `resolved_in_part` describes research progress, not approval or closure of an original queue item.

All source hashes, parent references, finding IDs and private permissions passed mechanical checks. All sixteen original draft files and both final P1 exports remain unchanged. The original 130-entry queue remains the historical baseline; no entries have been silently closed. Exact snapshots of previously inaccessible pages improve reproducibility but do not manufacture immutable upstream versions.

Qumran-Digital pages state CC BY-SA 4.0 and identify their transcription provenance. Other source components have different or unresolved terms. No component gained app-display, redistribution, training or adapter-release approval from this research. No paid model calls, retention changes, external contacts or publication occurred.

## Next execution

P2 is **partially complete**. The forty-item plan still has eight initial drafts, with thirty-two remaining; this batch deepens three existing records.

Next implement a separate review/eligibility registry and a private export using constructed fixtures. Bind decisions to exact component hashes, distinguish each intended use, preserve unresolved restrictions and require recorded review evidence. Keep the draft validator unchanged and leave real components pending until supported decisions exist. Prepare a concise specialist packet from the remaining questions. In parallel, P3 can proceed with offline evaluation-runner preparation under the [evaluation runbook](EVALUATION-RUNBOOK.md), preserving question-author separation. These familiar topics are development evidence, not a hidden benchmark.

Actual chat integration follows an eligible source subset and a frozen comparison. Further fine-tuning remains on the roadmap, chosen from that comparison's errors. See the [execution plan](EXECUTION-PLAN.md) and [living queue](../manifests/execution-state.json).
