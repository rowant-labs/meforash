# Modal snapshot reuse confirmation v3

September 13, 2026. Owner-authorized follow-up on the separate `codex/hosting-first-small-model` branch, under a new $5 ceiling. No training, production change, adapter export or weight publication.

Keep v2's exact model revision, image digest, L4, CPU/RAM limits, snapshot hooks, 900-second initialization allowance, 8K context and one sequence. Separate v3 resource names necessarily require initial snapshot creation again; classify those separately. Prepare and fully verify model files once before requests.

Collect six additional provider-verified snapshot reuse starts, allowing at most ten total starts to accommodate creation. Require zero running containers between requests and a distinct container identifier in provider logs. Measure actual client-first-content and full streamed-answer time, preserving incremental final-channel events and terminal status before cleanup. Attach model metadata to the terminal event from that same streamed call. Record last-content time separately from terminal-event time so metadata overhead is visible. This adds measurement instrumentation without changing model or initialization settings. A missing terminal result, failed identity check or timeout is a failure, not a successful latency sample. Logs determine creation versus reuse; do not classify from speed alone.

Stop on failure, ten-start ceiling or insufficient time. The root orchestration deadline is 90 minutes, with an independent 95-minute cleanup watchdog. At most one GPU worker runs. The $5 ceiling includes compute, preparation, storage and accounting contingency; final provider billing may lag. Check stopped Apps, zero containers and absence of the temporary Volume before recording teardown success.

Read-only adapter research proceeds alongside: distinguish documented support from actual export/load verification. Neither base-model timing nor a correct engineering answer establishes Bible quality or adapter portability. Record the outcome before deciding on training.

## Collector correction during execution

The first creation request returned a complete, identity-checked stream, but its completion marker was not yet present in the immediate provider-log fetch. The fail-closed collector stopped and verified cleanup. A later log receipt contains the exact matching nonce and boot token. Preserve that attempt as a collection race, not a model failure or reuse measurement.

Resume uses the unchanged serving module and original $5 campaign ceiling and watchdog deadline. The local collector now allows up to six log fetches, five seconds apart, to accommodate delayed log indexing; it deduplicates lines and still requires the exact nonce/boot-token/container binding. The correction changes no inference settings or timing receipts. Fresh resource preparation and any snapshot creation are reported separately.

## Outcome

The resumed series completed two snapshot creation starts and six verified reuse starts. First text on reuse ranged from 30.954 to 108.840 seconds (median 84.333); all answers and model identities passed. Both collection attempts were cleaned up, with stopped Apps, zero containers and deleted temporary storage verified. See [v3 results](MODAL-SERVING-RESULTS-V3.md). The offline adapter converter fixture also passed; live adapter loading and Bible quality remain unverified. No training or production change occurred.
