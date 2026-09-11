# Evidence pilot readiness

September 8, 2026. This document recorded the prospective readiness assessment.
The pilot was subsequently frozen, executed and reviewed; see the
[actual result](EVIDENCE-PILOT-V1.md). All 18 native answers completed. The
predefined narrow gates passed, but a separate post-freeze audit found a Daniel
language-boundary error and blurred attribution outside the criteria. The
result is development evidence over two familiar source families, not expert
certification, a whole-Bible benchmark or a model-promotion decision.

## What the current evidence can test

The v3 registry makes six components available through the verified delivery
path, but they form only two source families:

| Family | Eligible components | Useful development checks |
| --- | --- | --- |
| GT01, Mark 1:1 | SBLGNT short-ending claim, project English rendering, and edition reading | Whether supplied evidence helps B identify what the named edition displays, translate the selected phrase within recorded alternatives, and avoid treating an apparatus marker as Greek lexical text |
| AT03, Daniel 2:4 | Language-boundary claim, Hebrew-tagged boundary label, and following Aramaic-tagged address | Whether supplied evidence helps B distinguish the Hebrew language label from the following Aramaic address, preserve the edition's language annotations, and avoid turning an edition observation into manuscript or historical certainty |

These components can support a small same-model comparison of B-memory,
B-packet, and B-lookup. That comparison can diagnose whether a failure comes
from absent context, interpretation of a fixed packet, or the lookup path. An
exact lookup fixture is a development diagnostic; it does not establish
production retrieval quality. If the fixture returns the same components as the fixed packet, their rendered inputs can be identical. Any answer difference then reflects generation variability, not demonstrated retrieval improvement; report identical-input pairs explicitly.

The six components are not six independent passages or accuracy measurements.
They do not cover Hebrew beyond the Daniel boundary label, Aramaic beyond the
following address, Greek beyond one Mark verse, broad or application questions,
historical or dating claims, manuscript collation, wider textual alternatives,
or whole-corpus behavior. The English renderings remain project-authored and the
reviews are AI development reviews without expert certification.

The proposed 30-case, 90-slot comparison in the
[evaluation runbook](EVALUATION-RUNBOOK.md) therefore does **not** presently
have source coverage. Its proposed eight Hebrew, six Aramaic, six Greek, four
broad/application, and six general-control cases require many more eligible
source families. Rewording GT01 or AT03 questions would remain known development
work, not a fresh whole-Bible or generalization comparison. The three B arms also
cannot establish that fine-tuning itself helps; that claim would require the
separately proposed matched base-model condition.

## Pilot that was selected

The selected known-topic pilot used four Bible cases, two from each source
family, plus two simple general-English controls. It ran the three core B
conditions once for each case: **6 cases × 3 conditions = 18 planned slots**.

Treat the two general controls as repeated retention checks, not evidence-benefit
observations. Report Bible results over four planned cases and two source
families. Report B-packet versus B-memory as the primary evidence-treatment
contrast and B-lookup versus B-packet separately as a lookup diagnostic. This
pilot can support proceeding to a later fresh-source evaluation; it cannot
support model promotion, a whole-Bible claim, production readiness, or an expert
accuracy claim.

The exact protocol, criteria, sources, requests, native boundary and allowance
were frozen before the single actual collection. Both reviews were frozen
before the private condition map was opened.

## Frozen pre-generation gates

The final protocol adopted these gates before generation:

1. **Evidence closure.** Each Bible case names its exact eligible components.
   Immediately before request preparation, rebuild eligibility from the v3
   registry and exact notice manifest through `evidence_delivery`; bind the
   registry, manifest, source, component, rendered-packet, lookup-policy, and
   implementation hashes. B-memory receives no packet. B-packet receives the
   frozen fixed packet. B-lookup records its actual selection without fallback
   imports.
2. **Criteria quality.** Before any answer exists, freeze per-case required
   content, acceptable alternatives, omissions, critical errors, and source
   limits. For these topics, critical source errors include inventing manuscript
   attestation or historical priority, misreporting the named edition, treating
   the apparatus marker as lexical text, or moving the Daniel language label
   into the Aramaic address. Independent checking must bind exact locators and
   disclose that it is AI review without expert certification.
3. **Protocol closure.** Freeze questions and criteria separately from model
   inputs; also freeze prompt, checkpoint identity, native renderer/tokenizer,
   settings, case and arm order, stop rules, reviewer masking, slot inventory,
   gate thresholds, and worst-case cost. Review all returned finals, including
   partials, before unmasking.
4. **Completeness.** Require 18/18 complete planned answers: 6/6 per arm, with
   4/4 matched-complete Bible pairs for each contrast. A partial answer remains
   reviewable for errors but is not complete. Any missing, uncertain,
   unsubmitted, or incomplete slot makes the pilot conclusion inconclusive; it
   is not a loss for that arm.
5. **Quality.** Require zero critical errors in the scoped source assertions in
   every returned B-packet and B-lookup final, including partials. Review and
   report B-memory critical errors without requiring a perfect memory baseline;
   compare which baseline errors the evidence corrects and which errors it newly
   introduces. Also require no increase in requested-content omissions for
   B-packet versus B-memory on the four matched Bible cases, more B-packet
   preferences than B-memory preferences, and semantic passes on every general
   control in all three arms. Report B-lookup versus B-packet separately,
   requiring the intended eligible closure on all four Bible cases and no added
   critical error or omission. These thresholds describe pilot success only and
   must not auto-promote a model or feature.

## Checks completed before the live pilot

- The coordinator's mock acceptance showed that the notice-complete
  verified delivery output, prepared request, pre-submit journal, native receipt,
  and review bindings remain one exact closure. The mock coordinator is not live
  transport proof.
- The six new cases and source-based criteria were frozen without using
  candidate answers. Record their known-topic development status.
- Retained B availability and identity and the actual native
  transport boundary and frozen settings before submission.
- Current provider pricing, the 18-slot worst-case reservation, and a
  concrete execution allowance. Existing chat or historical experiment budgets
  do not cover this run.

Further source expansion and qualified specialist review are necessary for a
fresh, broader accuracy claim, but they need not delay this explicitly narrow
development pilot. The training hold is unchanged: notify the owner, receive the
new research topic, complete that research, and revisit the plan before any new
training.
