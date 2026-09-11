# Compatible-chat streaming comparison

September 11, 2026. Engineering validation of a serving transport for retained B, not a new training experiment or expert accuracy benchmark. Private protocols, receipts and independent AI reviews are in `runs/launch-v1/streaming-comparison-v1/` and `runs/launch-v1/streaming-comparison-v2/`.

The first protocol froze four paired cases before collection: Hebrew meaning, Greek clauses, a life-applicable follow-up and supplied-source attribution. It capped eight calls at $0.15 estimated with 2,048 output tokens each and no automatic retries. All four compatible-chat answers completed and passed the input-count and output-usage checks. Three native answers completed; the native source case produced no final answer with `incomplete_tml`. The original all-complete criterion was therefore not met; that outcome is preserved.

A separately frozen source-focused follow-up used two fresh questions, four calls, a $0.06 ceiling, and the same model/settings. All four answers completed. Independent AI review found no material new streaming regression in the five usable pairs across the two batches, including translation, attribution, source limits and follow-up behavior. Labels were visible and this is a small engineering sample, not a blinded preference benchmark.

All six streaming answers reported input-token counts equal to the local native render and total output usage at least as large as the final answer's token count. Equality of counts is not proof of byte-identical provider rendering. The compatible route uses provider chat rendering with medium effort, while the original route uses local native rendering at 0.7. Temperature, seed and retained B checkpoint remain unchanged. This is an explicit serving-transport change, not a claim of unchanged sampling semantics or improved model quality.

First answer text arrived at 3.991–14.231 seconds in these six streaming checks. The 12 comparison answers cost $0.03588142 estimated in total, including the failed native result; these token-rate estimates are not reconciled invoices. Deployment inference keeps the existing 8,192-output-token cap, higher than these short comparison checks.

## Implementation and release decision

The progressive implementation is default-off. It forwards only structured answer content through bounded worker messages, discards reasoning events, preserves the single submission and identity-owned polling contract, and retains a full cost reservation on uncertain failure. Partial failures are visibly incomplete and excluded from later conversation context. There is no automatic fallback to another model endpoint.

The first implementation smoke exposed an overly strict event schema: valid provider events include a nullable `tool_calls` member even when no tool is called. That failure and the bounded diagnostic are retained. Accept null/empty tool-call fields while rejecting actual tool calls, and require the corrected implementation and hosted checks to pass before enabling the switch. Any unknown usage or protocol failure remains uncertain rather than triggering a second paid request.

The corrected implementation smoke completed through the real subprocess transport with four progressive snapshots, first text at 20.524 seconds and completion at 23.963 seconds (including cold local runtime startup). Current release status: accepted for bounded hosted rollout; hosted verification pending. The original native transport remains available with `MEFORASH_STREAMING=0`.
