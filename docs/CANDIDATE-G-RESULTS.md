# Candidate G results

September 10, 2026. **Retain B. G did not meet every prospective development gate.** Training and the complete B/G comparison finished; no model switch, public deployment or repository publication occurred. The [experiment method](CANDIDATE-G-EXPERIMENT.md) and [aggregate results](../reports/candidate-g-v1.json) preserve the settings, gates and limitations.

## Completed experiment

G continued from original-language fine-tuned B for six fixed updates using 96 training rows, with 24 separate validation rows. The dataset contains 104 newly reviewed examples plus 16 exact old training rehearsal rows. There were 115,354 processed training positions and 11,023 supervised final-answer positions. Both G checkpoint kinds were saved with 30-day retention and verified alongside B. B’s October 6 expiries remain unchanged.

Data, recipe and collection code froze before question authoring. A fresh independent AI review checked all 30 questions and 67 source verses before final evaluation freeze. The additional pre-run review led to verified recovery copies, corrected exposure disclosures, two fresh answer reviewers and explicit failure/accounting rules. Original drafts and frozen historical artifacts remain preserved. No transport retry or re-collection occurred.

All 60 native answers completed and were receipt-verified: 30 per model. All 60 individual judgments and 30 paired judgments were frozen before label integration. Neither answer reviewer authored G’s targets or the questions. These are AI judgments, not expert accuracy scores.

## English-answer results

Across 24 Bible pairs, G was preferred on **3**, B on **10**, with **11 ties**. The frozen preference requirement was at least 8 G preferences and a margin of at least 4. The aggregate report separately records material errors, requested-content omissions, attribution, source-scope, unsafe-authority and unresolved-claim findings. General controls: B **6/6**, G **6/6**.

The answer gate failed; the retention gate passed. Every gate is required; lower prediction loss alone does not select the model.

## Reading the findings carefully

The original frozen individual review flagged the following answer counts. These are reviewer classifications, **not expert-certified factual-error rates**:

| Original reviewer flag | B | G |
|---|---:|---:|
| Material error | 1 | 4 |
| Requested-content omission | 1 | 6 |
| Source-scope extension | 2 | 2 |
| Attribution error | 0 | 0 |
| Unsafe/spiritual-authority error | 0 | 0 |
| Unresolved claim | 0 | 0 |

Root inspected all 15 flagged answers and all 30 paired rationales after unblinding. Two G errors are clear: the Proverbs 18:17 explanation reverses who examines whom, and the Psalm 90:13 explanation substitutes consolation for the appeal for compassion or relenting. G also folds surrounding Exodus 18 delegation details into its explanation without clearly marking their source; its translation of the supplied verses itself is sound.

Some classifications need qualification. Both James 3:18 answers use a defensible rendering with peacemakers as agents. They omit the rubric's alternative-construal discussion, but that does not make the chosen translation itself factually false. The [NET translators' notes](https://classic.net.bible.org/verse.php?book=Jam&chapter=3&verse=18) allow alternative relations, and [NRSVUE](https://www.biblegateway.com/passage/?search=James+3%3A18&version=NRSVUE) uses the agency rendering. The original review flags remain preserved; root disputes their classification as material factual errors.

G's Deuteronomy answer explicitly mentions impartial justice, so the review's claim that it omitted that idea is too strong. Several other omissions concern explicit source-numbering or AI-authorship labels rather than mistranslated clauses. Source-scope findings about theological or psychological interpretation are not, by themselves, proof that those interpretations are false. These distinctions matter when improving future evaluations and the conversational product.

No post-hoc score replaces the frozen review. **Retain B remains the decision independently of these qualifications**, because G's 3 preferences versus B's 10 fail the unchanged preference gate. The result supports neither promoting G nor declaring B error-free. Before another training proposal, improve evaluation severity definitions and distinguish missing substance from label/detail omissions.

## Prediction diagnostics

| Diagnostic | Before G updates | After G updates | After/before |
|---|---:|---:|---:|
| New 24-row G validation | 1.78163427 | 1.47008834 | 0.825135 |
| Unchanged 12-window Hebrew/Greek | 0.01151264 | 0.01156855 | 1.004856 |
| Unchanged 16-row English validation | 2.19882247 | 1.89386935 | 0.861311 |

Raw-text loss remained within 110% of B overall and separately for Hebrew/Greek; old English-target loss remained within 115% overall and by Hebrew/Greek/Aramaic. These small fixed diagnostics measure prediction retention, not translation accuracy.

## Cost and limitations

Estimated training/validation, sampling and the earlier three serving probes total **$1.58403889**. Including the **$3 storage contingency** gives **$4.58403889**, below the original **$7.66376908 reservation** and **$20 ceiling**. Evaluation used 41,334 input and 34,116 generated tokens, including hidden reasoning, for **$0.23695746** estimated sampling. Training/forward accounting is conservative; storage is a contingency and provider billing is unreconciled.

All Bible evaluation verses appeared in B’s raw training. Aramaic coverage uses Daniel 4 and Ezra 6, both known development/old-validation chapters; the Dan 4:31–32 task also shares exact source verses with old validation rows. John 9 overlaps an earlier broader source family. Questions are new, but this is development evaluation rather than unseen-source generalization.

Single answers per slot cannot cleanly separate weight effects from provider/generation variability. Earlier repeated unchanged-model answers differed despite matching requested settings, and identical-input pilot comparisons produced non-tie preferences. No numerical chance rate is established for this set. The model’s original base revision is unpinned; AI reviewers are project participants and procedural masking cannot exclude style recognition.

This comparison supplies selected edition excerpts using the frozen baseline system prompt. It does not establish expertise across all biblical languages, earliest recoverable witnesses, historical questions or real conversations. The [private beta candidate](PRIVATE-BETA-READINESS.md) remains separate from model selection and hosted verification.
