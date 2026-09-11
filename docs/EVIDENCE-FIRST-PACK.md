# First historical-evidence research pack

Prepared September 7, 2026. **Eight AI-authored research drafts are prepared; none is expert-certified, approved for app use, or approved for training.** This is the first batch within the [forty-item collection plan](HISTORICAL-EVIDENCE-MILESTONE.md), supporting the original-language fine-tuned model. The current private chat continues to use retained B and its existing passage lookup.

The batch contains four textual dossiers and four context notes. Each group includes two Hebrew-related, one Aramaic-related and one Greek-related item. The [public inventory](../manifests/evidence-first-pack-v1.json) records the selected cases, private draft hashes and measured checks without distributing the unreviewed source records.

| ID | Subject | Research focus |
|---|---|---|
| HT01 | Genesis 4:8 | Preserve the selected Hebrew’s unquoted speech; distinguish reported Samaritan/versional additions, contrary Qumran reporting and editorial judgment. Exact external witness transcriptions remain unchecked. |
| HT07 | Isaiah 53:11 | Distinguish the selected WLC wording from scholarly reports of the light reading. Preserve contrary scholarly judgment and unverified fragment/line details. |
| AT03 | Daniel 2:4b–9 | Check the Hebrew-to-Aramaic boundary, written/read layers, and separately identified Swete Greek versions. Catalog discovery does not establish DSS verse coverage. |
| GT01 | Mark 1:1 | Separate the SBLGNT edition comparison from two CNTR witness transcriptions, including an encoded correction and nearby comparison verses. |
| HC01 | Assyrian royal accounts and Judah | Distinguish the Taylor Prism, a separately identified RINAP inscription, the biblical account, and the limits of corroboration. |
| HC03 | Persian restoration | Compare the Cyrus Cylinder’s royal presentation with Ezra’s Judean narrative without treating them as the same document. |
| AC01 | Administrative Aramaic | Use an identified Arshama provisioning document as context for scribes and letters; preserve the debate over estate and public resources. |
| GC01 | Roman Judean administration | Compare Luke’s governing language with the Pilate inscription, retaining damaged/restored letters, catalog terminology and differing dates. |

HT07 replaces the provisional HT02 starter and AT03 replaces AT01 because usable sources supported those bounded assignments. The original forty-item plan remains intact. These are development cases, not a hidden accuracy benchmark or a narrowed product scope.

## What was actually prepared

Across the eight records, **45 citation entries** are recorded: **31 have hashes matching locally retained source bytes**, and **14 have explicitly null content hashes**. These are citation entries, not 45 independent witnesses. No asserted content hash lacks its corresponding local artifact.

Each draft has a structured JSON record and an English Markdown review companion. Sources, exact locators, selected readings, authored translations, attributed claims, alternative explanations and coverage limits are separate fields. Narrated setting, composition, physical witness and modern edition have distinct date categories. Unknown dates remain unknown.

Source downloads and unreviewed records remain in ignored local data. The preparation retains exact SBLGNT apparatus material and bounded CNTR Mark excerpts, keeping manuscript correction/abbreviation/layout encoding. The Aramaic work retains identified Greek edition files and Bodleian research PDFs. Hebrew source excerpts were checked against the existing WLC artifacts; external Hebrew witness claims remain attributed scholarly reporting until their underlying transcriptions can be checked.

Some sources could only be inspected through retrieved/indexed text. In particular, the Isaiah dossier's author-hosted Tov PDF could not be downloaded; that citation has no local content hash. Such entries remain explicit research gaps. A catalog URL, scholarly report or matching file hash is not independent verification of a manuscript reading.

The readable local review packet is generated under `data/evidence/review-v1/README.md`. It is deliberately excluded from publication candidates, alongside the underlying drafts. This shareable report describes the work without declaring the research complete or redistributing restricted components.

## Source and reuse findings

The exact artifact matters. The pinned SBLGNT Mark apparatus names NA28 in its edition comparison; its older website introduction describes a different comparison list. The dossier follows the actual artifact and attributes the older description separately. Edition labels are not additional ancient manuscripts. [Pinned apparatus](https://raw.githubusercontent.com/LogosBible/SBLGNT/c4d241a9c1c479a55b989ba35a4976c1d0b8052c/data/sblgntapp/text/Mark.txt)

The selected CNTR files preserve correction states. The record attributes the hand classification to CNTR’s technical reference and does not claim an independent paleographic assessment. CNTR-derived material retains separate CC BY-SA 4.0 attribution and future-use review. [Pinned repository](https://github.com/Center-for-New-Testament-Restoration/transcriptions/tree/4c0e9f94117ec3dc4ae40094aec044bb7a416a53)

Additional component-level findings change the earlier import assumptions:

- **STEP Hebrew definitions:** the selected TBESH header requests separate Online Bible permission. No Hebrew definitions were extracted for use. The [file-level review](../licenses/STEP-LEXICAL-REVIEW.md) records this alongside the general CC BY notice.
- **STEP Greek sample:** ten metadata rows for six extended Strong identifiers were prepared privately. All five Jesus/Joshua disambiguation rows remain separate. Long definitions are omitted, and no contextual meaning or automatic verse alignment is asserted.
- **Brown’s Pilate transcription:** the inspected archival XML states CC BY-NC 4.0. It remains a private research component; the general usefulness of the object does not clear its modern transcription for unrestricted reuse. [Pinned archival record](https://raw.githubusercontent.com/Brown-University-Library/iip-texts/0b7dc8358ccdfd0c9391f049da4839fbd91c26e5/archival-files/caes0043.xml)
- **Bodleian Arshama publications:** the consulted editions state CC BY-NC-ND 4.0. Their modern translation and continuous Aramaic transcription were not imported into the authored note. Research access does not establish app, training or adapter-release permission. [Bodleian edition](https://blogs.bodleian.ox.ac.uk/wp-content/uploads/sites/116/2013/10/Vol-2-texts1.pdf)

These are observed source conditions and project use decisions, not blanket legal clearance. Authored notes, source text, transcriptions, annotations, translations and images remain distinct components.

## Reproduce the mechanical checks

Install the separate evidence-validation requirements into the project environment:

```sh
.venv/bin/python -m pip install -r requirements-evidence.txt
.venv/bin/python -m bibleprep.evidence --out runs/evidence-v1/local-draft-audit.json
.venv/bin/python -m unittest tests.test_evidence -v
```

Use a new receipt filename for a later audit; existing receipts are preserved. The draft records are required locally and are not bundled in a public clone. Source acquisition and private author receipts document this batch's preparation; the present release candidate does not yet provide a complete public dataset reproduction.

For the bounded lexical sample, the preparation can fetch its exact pinned source files:

```sh
.venv/bin/python -m bibleprep.lexical_preview --fetch
```

The validator uses the existing plan's Draft 2020-12 JSON Schema, then checks cross-references, duplicate identifiers, source/right-component links, date ordering, translation attribution, and draft-stage use decisions. It rejects unsupported promotion to app/training approval. Its source scan rejects symlink escapes. None of these commands generates model answers or changes the chat's inputs or model weights.

Twelve tests cover meaningful failure cases, including a rights notice disguised as manuscript evidence, unavailable text filled with wording, reversed BCE dates, dangling references, unsupported approval and private-path escapes. Independent AI code review found two implementation gaps, which were fixed and retested. Mechanical and AI source checks do not replace specialist review, validate every locator automatically, or certify the rights of an adapter trained on a source.

## What this enables next

Review and correct the eight records against the underlying evidence, prioritizing the missing witness locators, indexed-only sources and disputed readings. Obtain relevant language/textual and historical expertise before treating these as approved evidence. Separately resolve the components eligible for redistribution, app display and training; exclude or replace restricted components where needed.

The next model experiment should ask whether explicit, checked evidence helps B distinguish edition choices, witness states and uncertainty while answering in English. Freeze a separate evaluation before prompt or training changes. A later fine-tune can learn those evidence-handling behaviors from eligible, reviewed records. This batch has created research material and validation infrastructure; it has not demonstrated a new model-quality gain or completed the forty-item scholarly collection.
