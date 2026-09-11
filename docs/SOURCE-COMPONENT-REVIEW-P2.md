# First component source reviews

September 8, 2026. Six components from two existing development dossiers now have narrow AI scholarly reviews recorded in a new private registry. **No app, training or release use was approved, and no evidence was loaded into chat.** The retained Bible model remains B.

| Record | Components reviewed | What the review supports |
| --- | --- | --- |
| GT01, Mark 1:1 | `claim-GT-A1`, `claim-GT-A5`, `reading-GT-R1` | The exact selected SBLGNT edition text, its apparatus marker, and a defensible project English rendering. This does not choose the earliest reading or approve the other witness/variant claims. |
| AT03, Daniel 2:4 | `claim-at-boundary`, `reading-boundary-label`, `reading-aramaic-address` | Exact OSHB/WLC tokens and the edition's Hebrew/Aramaic annotations. The language-name token remains in the Hebrew introduction; the address follows it. This is an edition observation, not manuscript collation. |

These are six content components, not six independent passages or accuracy measurements. Sol source reviewers and the parent AI checked exact component/citation/source bindings and selected source locators. Their shared project roles are disclosed; no human specialist or expert certification is recorded. Draft English-rendering labels and the original requests for specialist review remain intact. Mark's genitive interpretation and wider textual history are not settled by this review.

The review artifacts are `data/evidence/component-reviews/p2-v1/{GT01,AT03}.{json,md}`. The new registry is `data/evidence/eligibility/evidence-eligibility-v2-ai-reviewed.json`; it preserves all 83 original component identities and content hashes, records six scholarly approvals, and leaves every use pending. The v1 registry and original source drafts remain unchanged. Private acceptance and the zero-eligible readiness projection are under `runs/evidence-request-pairwise-p3-v1/`.

## Remaining delivery requirement

The reviewers found a conditional basis for narrow private use under the retained source notices. SBLGNT carries CC BY 4.0; OSHB distinguishes its WLC base text from its licensed annotations. Required attribution, license/source links, change notices and applicable disclaimer/non-endorsement notices must accompany delivery. The source notices are retained and hash-bound in the reviews; these observations do not approve public release or other uses. See the [SBLGNT license page](https://www.sblgnt.com/license/) and [pinned OSHB notice](https://github.com/openscriptures/morphhb/blob/3d15126fb1ef74867fc1434be1942e837932691f/LICENSE.md).

The current evidence formatter copies source author/title/URL but omits explicit license and change-notice fields. Therefore the conditional use recommendations were not converted into app-use approvals. This is an implementation task, not a request for new owner or specialist permission for these narrow edition observations.

Next implement a versioned notice-delivery path for model inputs and evidence display, check exact source/component bindings and private-field exclusion with constructed fixtures, then verify the real six-component package against the reviewed conditions. Record any supported private-use decisions separately. Continue wider source review and prepare fresh questions before the controlled English-answer comparison. These familiar Mark and Daniel topics remain development material.

The [request preparation](EVIDENCE-REQUEST-PREPARATION.md) and [paired review tools](EVIDENCE-PAIRWISE-REVIEW.md) passed constructed integration in the same work session; their fixtures are not source accuracy evaluations. See the [living execution state](../manifests/execution-state.json) for the next task.


## Subsequent private delivery decision

On September 8, 2026, the new notice delivery module and exact four-notice manifest passed parent integration against all six reviewed components. The new private registry `data/evidence/eligibility/evidence-eligibility-v3-private-delivery.json` records six conditional `app_display` approvals for private development input/display through this verified delivery path. Seventy-seven components remain pending; redistribution, training and adapter release remain pending for all 83 components. Original drafts, scholarly review qualifications and v1/v2 registries are unchanged.

The checks preserved exact Greek/Aramaic content and coverage limits, delivered twelve component/rights notice associations, excluded private review metadata, and rejected pending or withdrawn use decisions, changed notice prose and forged saved wrappers. The focused delivery and eligibility suites passed 20 tests. These checks establish delivery consistency; the scholarly basis remains the separately bound AI source reviews, with no expert certification.

See [notice delivery](EVIDENCE-NOTICE-DELIVERY.md). Private integration and acceptance receipts are under `runs/evidence-delivery-p2-v1/`. The existing chat and legacy formatter are unchanged. The next coordinator must use the new verified rendering path; a raw eligibility projection is insufficient. No source entered chat or training, and no provider request was made.
