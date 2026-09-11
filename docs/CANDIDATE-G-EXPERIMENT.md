# Candidate G: grounded English continuation from B

Updated September 10, 2026. The bounded [Candidate G sequence is complete](CANDIDATE-G-RESULTS.md). G completed six updates; both full checkpoints and all four required B/G roles were verified. All 60 answers and 30 pairs were reviewed. Across the 24 Bible pairs, G was preferred on 3, B on 10, with 11 ties. Retention passed, but the frozen preference gate independently failed, so retain B. Aggregate findings are AI-review flags rather than factual-accuracy scores; root review disputes the James material-error flag for both arms and treats some omissions as rubric/notice-level, without changing the preference failure. No further training, recollection, model switch or public launch follows automatically.

## Question and data

Can a small, carefully reviewed English continuation help the original-language-adapted B answer questions more completely, distinguish its own translation from a supplied project draft, respect source limits, and offer reflection when requested?

The dataset contains **104 new examples and sixteen exact rehearsal records from the earlier training split**. The final split is 96 training and 24 validation records. New examples use selected WLC Hebrew/Aramaic main text and SBLGNT Greek main text, with edition/use notices. These are named editions, not a claim to possess an undisputed original Bible. No user conversations or newly collected historical-evidence drafts are included.

The new examples cover direct textual questions, evidence boundaries and paired question intents. Twelve explicitly request short full translations. Eight supply clearly attributed project-authored English drafts for comparison or explanation. The first reviewed version was preserved and superseded before evaluation authoring to add those eight attribution tasks. Independent AI review approved all **104 final new rows**; exact original training records supply the sixteen rehearsal rows. This review is not specialist certification, and private training approval does not by itself approve dataset or adapter redistribution.

The new examples use forty training and twelve validation chapter families, with no overlap between those groups. All selected original-language passages had appeared in B's earlier raw-text training. They are new English tasks, not unseen-language training material. See the [source plan](CANDIDATE-G-DATA-PLAN.md) and [source card](SOURCE-CARD.md).

## Exact training recipe

G starts from B's weights with a fresh optimizer: full `thinkingmachines/Inkling`, rank-8 LoRA, attention/MLP/unembedding adaptation, one pass, six batches of sixteen, and learning rate 0.00002. The shuffled order and seed are fixed. The training set contains **115,354 processed input positions and 11,023 supervised final-answer positions**. Prompt tokens receive no loss. The 24 validation rows contain 30,604 input positions and 2,588 supervised positions.

The new examples use the frozen baseline English system prompt from the earlier evidence pilot. The sixteen exact rehearsal records retain their original prompt framing. Native prompt parity was checked with constructed fixtures. No hidden reasoning text is used as an authored target, and this experiment introduces no recurrent layers or architectural change.

Before and after training, measure the new 24-row validation set, the unchanged twelve Hebrew/Greek raw-text windows, and the unchanged sixteen-row English validation set. Validation receives no updates. These losses measure prediction and retention; they are not translation-accuracy scores.

## Authorized sequence and prospective decision

The prospective method required the final 96/24 dataset, six-update recipe and collection implementation to be frozen before fresh-question authoring. It then required independent source review of all thirty questions, their source evidence and case-specific expectations, followed by a final evaluation freeze before training or generation. Those pre-training requirements passed and the evaluation is frozen. The unchanged comparison uses identical B and G prompts and evidence with alternating request order: ten Hebrew, eight Greek, six Aramaic and six general-English cases. The Bible questions include twelve direct, six boundary and six intent cases.

The owner's authorization allowed one G training run of exactly six updates and the subsequent frozen B/G comparison, conditional on the final source review and evaluation freeze, a current preflight, and an exact pre-training notice. Those conditions were completed before training. The frozen contingency required preserving a stale preflight and creating a versioned refresh and honest refreeze rather than rushing review or weakening freshness checks. The notice stated the 96/24 split, 115,354 processed and 11,023 supervised training positions, six updates, the $7.66376908 reservation under the $20 operator ceiling, and the thirty-day G checkpoint retention period.

Use chapter families outside G's training and validation sets and inspect earlier questions for close task duplicates. Record prior exposure explicitly: all Bible evaluation verses appeared in B's raw-text training; the Aramaic cases use previously seen Daniel 4 and Ezra 6 chapters; and John 9 shares a prior source family. These are new questions, not an unseen-source benchmark. Never send answer rubrics to the model. Stop the whole collection after the first uncertain, partial or malformed response, including a transport failure without text. Do not retry, resume or recollect within this sequence. Review every returned final answer, including partial text; an incomplete collection is inconclusive and retains B.

Use two fresh GPT 5.6 Sol answer reviewers who authored neither G targets nor evaluation questions. Mask candidate identities and left/right order, recognizing that procedural masking is not access control and writing style may still reveal identity. Freeze individual and paired reviews before revealing B/G labels. These are AI reviews with disclosed project-role overlap, not expert certification.

G is eligible only if all sixty answers complete and all reviews and receipts verify; it wins at least eight of the twenty-four Bible pairs with at least four more wins than losses; it has no material, attribution, source-scope or unsafe-authority errors or unresolved claims; it has no more requested-content omissions than B; and it answers all six general controls correctly. Raw-text NLL must stay within 110% of the fresh B baseline, and old English-target NLL within 115%, both overall and by represented language. Every gate is required.

Failure retains B. Passing supports a bounded preference for the tested workflow and still requires a check through the actual application's prompt and source-delivery path before integration. One sample per slot cannot separate a weight effect cleanly from generation variability: an earlier 24-prompt repeat produced changed final text throughout, although an unpinned provider revision prevents assigning the difference to sampling alone, and the pilot produced 1/2/1 preferences from fixed-packet and lookup inputs that were byte-identical. Do not change the frozen gate or claim a numerical chance rate from those observations. It does not establish expert accuracy or public readiness.

## Cost and operational boundary

The conservative G reservation was **$7.66376908 within a $20 operator ceiling**: $1.34431308 for training and validation forwards, up to $3.219456 for sixty bounded samples, $3 for checkpoint/storage contingency and $0.10 for the serving probe. Final estimated training/validation, sampling and earlier serving-probe cost is **$1.58403889**; adding the **$3 storage contingency** gives **$4.58403889**, below the reservation. Provider billing remains unreconciled. The run saved both full G checkpoint kinds with thirty-day retention and preserved B and all prior experiments.

The [beta readiness record](PRIVATE-BETA-READINESS.md) and [open-source release candidate](OPEN-SOURCE-RELEASE-CANDIDATE.md) track product and publication work separately from model selection.
