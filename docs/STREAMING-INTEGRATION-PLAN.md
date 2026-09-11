# Progressive answer integration plan

September 11, 2026. This is an offline implementation plan. It authorizes no provider call, deployment, model change, training, or change to the retained B adapter.

## Decision and provider gate

Keep the existing `POST /api/chat` plus authenticated `GET /api/chat/{request_id}` contract. Extend a running result with a revisioned, cumulative final-answer snapshot and poll it every 500–900 milliseconds. Do not add a browser-facing SSE connection. The current polling path already binds a result to its guest, account, or invitation identity; polling does not reserve quota, start a worker, or call the provider. Cumulative snapshots make repeated or missed polls harmless and avoid delta duplication.

Provider streaming must remain behind `MEFORASH_STREAMING=1` until one of two separate gates passes. The preferred exact-native gate requires a raw completion route that accepts the exact locally rendered TML prompt, reports the same input-token count as the pinned tokenizer, returns completion text that round-trips through that tokenizer, preserves the native stop/framing tokens needed by the official parser, and reports output usage consistent with the reconstructed token sequence. The alternative compatible-chat gate requires a prospective, controlled comparison against the current native path covering answers, retained-B/settings identity, final-only event separation, completion behavior, and accounting. Passing that comparison would support a separately named transport decision; it would not prove byte-identical native rendering and must not silently replace the current path.

The bounded probes in [STREAMING-PROBE-V1.md](STREAMING-PROBE-V1.md) did not pass the exact-native gate. The raw text request reported 415 input tokens for a prompt containing 377 pinned native tokens, ended at length, and reported 31 completion tokens despite 37 streamed chunks. The compatible chat route did stream structured answer chunks and reported 377 input tokens, but its exact native rendering remains unverified. Therefore streaming stays off. A provider fix may reopen the exact-native route, or a separately authorized controlled comparison may evaluate the compatible chat route. Neither condition enables the flag automatically. Never fall back from a submitted streaming request to another endpoint, because that could make a second paid generation.

The following inference identity remains byte-for-byte and value-for-value unchanged: `thinkingmachines/Inkling`, the retained B adapter resolved from its existing receipts, the current system prompt and source context, the official TML renderer at effort `0.7`, `reasoning_effort="medium"`, temperature `0.0`, seed `20260905`, one sample, the existing native stop tokens, 24,000 input tokens, 8,192 output tokens, and the 300-second whole-operation deadline. Keep application retries disabled, SDK retries at zero, and the current cost rates and reservation size.

## Exact implementation changes

### `bibleprep/chat_model.py`

Add a chat-only `BoundedStreamingTransport`; leave `bibleprep/tinker_evaluate.py` and its frozen evaluation transport unchanged. The transport uses one spawned `chat_worker`, one request, one monotonic 300-second deadline, and one provider submission. Its pipe protocol is an allowlisted union:

- `{"kind":"progress","revision":N,"answer":"cumulative typed final text"}`
- `{"kind":"complete","revision":N,"response":SAFE_RESULT}`
- `{"kind":"local_error","code":ALLOWLISTED_CODE}`
- `{"kind":"uncertain"}`

No pipe message may contain credentials, raw token IDs, thinking text, provider exception text, request bodies, provider identifiers, or email/account data. Validate exact keys, monotonically increasing revisions, prefix-only cumulative answers, and a 512,000-byte UTF-8 answer ceiling in the parent. A malformed envelope, closed pipe, deadline, or provider failure after submission marks the transport failed, terminates the worker, blocks the `ChatModel`, and raises the existing sanitized timeout/provider error. It never respawns and resubmits that request.

For an exact-native route, add a streaming method to `NativeChatSession` only after that gate passes. Keep provider SSE handling inside the quiet child process. Accumulate raw completion text, and at no more than four progress projections per second re-encode the entire accumulated text with the pinned tokenizer. Pass those reconstructed token IDs to the existing `native_diagnostics_v1.parse_generated`; send only `_safe_result(...)["answer"]` when parsing has no structural issue and the value extends the last published prefix. This exposes only official-parser `Text` in main/final channels. `Thinking`, analysis-channel text, unsupported content, raw decoded text, and exception strings never cross the pipe. At provider completion, parse the complete reconstructed sequence again with the reported stop reason and send the existing validated safe result.

For a separately accepted compatible-chat route, add a distinct `CompatibleChatStreamingSession` instead of changing `NativeChatSession`. Accept only documented structured answer events, discard reasoning events in the child, require the terminal answer to equal the cumulative published answer, and validate reported settings and usage against the comparison contract. Do not re-tokenize compatible-chat text and label it a native-parser result. The final safe answer in either transport must extend the last published snapshot; otherwise return a sanitized terminal error with the last safe partial and known usage accounting.

Extend `ChatModel.generate` with an optional non-throwing `on_progress(cumulative_answer, revision)` callback. When streaming is disabled or no callback is supplied, retain the current synchronous transport. Callback failure must stop further callbacks but must not cancel, restart, or duplicate the paid generation.

### `bibleprep/beta_server.py`

Keep reservation, `mark_submitted`, single-generation concurrency, and result ownership in their current order. Initialize a running job as `{"status":"running","revision":0,"answer":""}`. Pass a callback to `ChatModel.generate` that, under the application lock, replaces only that job's in-memory cumulative answer and revision. Store no progress in SQLite and log none of it.

`GET /api/chat/{request_id}` returns the latest snapshot. A running response is exactly `{"status":"running","revision":N,"answer":TEXT,"complete":false}`. A normal terminal response keeps the current fields and adds its final revision. Repeated GETs do not alter quota or accounting.

If the provider ends normally with `length` or incomplete native framing and the existing parser supplies safe final text, return the current terminal success shape with `complete:false` and its existing warnings. If a timeout, pipe loss, or provider error occurs after a safe final snapshot was published, return `status:"error"`, the sanitized existing error, `partial_answer` equal to the last safe cumulative snapshot, `complete:false`, and its revision. The UI may preserve that text with an incomplete/error note, but it must not add this uncertain turn to future model context. A structural parse failure stops new progress immediately; thinking or untyped text is never substituted.

Quota behavior does not change. A definitive pre-provider failure releases cost and the guest/account question. A normal terminal result uses reported usage and consumes one question. A failure after submission consumes one question and retains the maximum cost reservation as uncertain. Browser disconnects and repeated polling neither cancel nor duplicate the request. A `409 busy` still occurs before reservation.

Apply the same in-memory snapshot and callback shape to `bibleprep/chat_server.py` so the local preview exercises the production model transport. Keep its process budget rules unchanged.

### `web/beta/app.js`

Reuse the current `poll()` loop. Create one temporary assistant node after the first nonempty running answer. Accept only integer revisions greater than the last seen revision and cumulative answers extending the displayed value. Replace the node's plain `textContent` while running; do not repeatedly run the Markdown-like renderer on incomplete syntax. On terminal success, render the authoritative final answer once and append exactly one assistant message to the client-side conversation. On terminal error, retain `partial_answer` with an explicit incomplete/error note but do not append it to the `messages` array. Preserve the existing epoch checks so sign-in, sign-out, new-chat, and stale poll completions cannot update the current conversation.

No changes are required in `bibleprep/beta_preview.py` or the static route allowlist. `bibleprep/railway_deployment.py` needs only strict parsing and injection of the opt-in streaming flag after the provider gate and offline tests pass.

## Offline tests

Add `tests/test_chat_model_streaming.py` with fake provider streams and fake official-parser updates. Verify:

- analysis/thinking, unsupported channels, exception text, raw IDs, and credentials never enter progress envelopes;
- cumulative final text is monotonic and a completed-message update does not duplicate streamed text;
- for an exact-native transport, text chunks split inside tokenizer boundaries are re-encoded cumulatively and produce the same final tokens as one complete string;
- for a compatible-chat transport, only structured answer events become progress, reasoning events are discarded, and the terminal answer equals the cumulative snapshot;
- malformed native framing stops progress and cannot relabel analysis as final text;
- the terminal safe result equals the existing non-streaming parser result for complete, output-limit, partial-final, and parse-error fixtures;
- the request preserves retained B, effort `0.7`, medium reasoning, temperature zero, seed, limits, stop tokens, one sample, and retry-disabled settings;
- deadline, broken pipe, malformed envelope, and callback failure never cause a second worker request or provider submission.

Extend `tests/test_beta_server.py`, `tests/test_chat_server.py`, and `tests/test_chat_server_review.py` to verify identity-isolated progress, monotonic revisions, repeated read-only polls, close/expiry cleanup, and `409 busy` before a second reservation. Cover each accounting outcome: local failure releases quota, normal and output-limit completion finalize actual usage once, and post-submission failure retains one question plus the full uncertain reservation while returning only the last safe partial.

Extend `tests/test_beta_app.js` for running-node replacement, ignored duplicate/out-of-order revisions, terminal rendering without duplicate assistant messages, stale epoch cancellation, and partial-error display excluded from future request history. Existing non-streaming running responses without `revision` or `answer` must continue to work during rollout.

Before enabling the flag, run the focused chat model/server/beta/browser suites, the existing native-diagnostics fixtures, deployment tests, and one bounded live smoke check. Either the exact-native probe must show matching local/provider input-token counts and matching reconstructed/reported output-token counts, or the compatible-chat comparison must already be frozen and accepted with its answer/settings/accounting limits. The smoke check must record one reservation, one provider submission, no thinking in any browser response, a visible progress revision before completion, and one final ledger update. Any parity or comparison-contract mismatch leaves streaming disabled and does not authorize another call automatically.
