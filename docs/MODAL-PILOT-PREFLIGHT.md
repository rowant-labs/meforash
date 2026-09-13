# Modal gpt-oss-20b serving pilot preflight

Prepared September 13, 2026 on `codex/hosting-first-small-model`. This document began as a proposal and preserves that preflight design below. The owner has since authorized one separate, bounded Modal serving test under a **$5 total ceiling**. The bounded execution is complete; its measured outcome is linked below. This authorization changes neither the retained Inkling B decision nor the holds on training, production deployment and publication. The root operator alone handles credentials, provider operations, receipts, budget enforcement and teardown; no credential value is recorded here.

## Implemented test configuration

The tested baseline uses [`tools/modal_serving_pilot.py`](../tools/modal_serving_pilot.py). It pins the Linux AMD64 image `vllm/vllm-openai@sha256:082ca6f035279109041ffd3fe0695cb568b29bc580b35c4f297a66a08b216c1b`, which is expected to provide vLLM 0.29.0 and is checked again at container startup. A small CPU preparation function downloads the allowlisted public root files directly with Python's standard-library HTTP client, verifies the selected shard sizes and SHA-256 values, validates the weight index, and writes a revision-bound manifest to the named Volume. It does not require `huggingface_hub` or a Hugging Face credential.

Serving remains private through authenticated Modal SDK methods. `Model.probe` returns a durable final-only result for asynchronous submission and reconciliation, `Model.remote_gen` optionally streams only final-answer text plus a terminal status/usage event, and `Model.metadata` reports the bounded runtime identity. The implementation creates no public web endpoint. Image build, weight preparation, model startup, inference, scale-to-zero, teardown and billing were recorded separately; a successful build alone was not treated as a serving result.

## Execution outcome

The bounded pilot is complete: plain L4 serving and one observed idle scale-to-zero passed; snapshot preparation hit a provider startup deadline before an external answer. All pilot Apps are stopped and the temporary Volume is deleted. See [measured results](MODAL-SERVING-RESULTS-V1.md). No training or production change occurred.

## Question and order of operations

The pilot would answer two questions in order:

1. Can one exact Modal L4 container load and serve the already qualified `openai/gpt-oss-20b` native-MXFP4 revision with vLLM 0.29.0 at the project's 8K, one-sequence settings?
2. Only if that plain cached baseline passes, do Modal GPU Memory Snapshots produce verified restored cold starts for the same stack without changing response identity or runtime settings?

Do not mix the provider comparison with a model, precision, context, engine or adapter change. This pilot has no adapter. A snapshot pass would not establish future Tinker/PEFT LoRA compatibility.

## Candidate configuration and resolved execution pins

| Component | Proposed pin or limit |
|---|---|
| Modal Python SDK | `modal==1.5.5` |
| Container base | `vllm/vllm-openai@sha256:082ca6f035279109041ffd3fe0695cb568b29bc580b35c4f297a66a08b216c1b` (Linux AMD64); record the resulting Modal Image ID |
| Engine | `vllm==0.29.0` |
| Hugging Face client | none in the CPU preparation function; standard-library HTTP downloads only |
| Model and tokenizer | `openai/gpt-oss-20b` at `6cee5e81ee83917806bbde320786a8fb61efebee` |
| GPU | exactly `gpu="L4"`; no fallback list and no silent larger-GPU substitution |
| Host allowance | 2 physical CPU cores and 32 GiB RAM; measure actual peak before reducing it |
| Autoscaling | `min_containers=0`, `max_containers=1`, 60-second `scaledown_window`; explicitly price any region restriction |
| Engine limits | `--max-model-len 8192`, `--max-num-seqs 1`, `--gpu-memory-utilization 0.85`, `--enforce-eager` |
| Adapter | none; LoRA stays disabled |
| Access | authenticated private Modal SDK class methods; no web endpoint |

Modal documents `L4` as a valid GPU resource string, but its snapshot examples use other GPU types. The exact L4, gpt-oss, vLLM 0.29.0 and GPU-snapshot combination is therefore an empirical gate, not documented compatibility. The current official Modal gpt-oss example uses B200 and vLLM 0.18.1 and cannot stand in for this test. [Modal GPU selection](https://modal.com/docs/guide/gpu), [Modal gpt-oss example](https://modal.com/docs/examples/gpt_oss_inference), [Modal SDK releases](https://modal.com/docs/sdk/py/releases)

## Root-only preparation and credentials

The root operator owns all provider interactions. Only the root process may load the saved Modal credential, immediately before an authorized provider operation. Do not pass it to a worker, print the environment, write it to a receipt, include it in Modal Image layers or expose it to the serving process. Public model preparation should not require an Hugging Face token.

Before GPU provisioning, prepare an immutable, versioned Modal Volume directory containing only this allowlist from the pinned repository root:

```text
model-00000-of-00002.safetensors
model-00001-of-00002.safetensors
model-00002-of-00002.safetensors
model.safetensors.index.json
config.json
generation_config.json
chat_template.jinja
tokenizer.json
tokenizer_config.json
special_tokens_map.json
LICENSE
README.md
USAGE_POLICY
```

Exclude `metal/**`, `original/**`, `.gitattributes` and any other unlisted file. Bind the directory name to the model revision and a manifest hash; record every file's path, size and SHA-256. Mount it read-only at a fixed local path and point both model and tokenizer to that path with offline loading enabled. Check that the index references only the three selected root shards. Preparation success means exact bytes are present and the manifest validates; it does not mean the engine or snapshot works. Modal Volumes persist files after containers stop, so their cost and later deletion need separate receipts. [Modal model-weight storage](https://modal.com/docs/guide/model-weights)

Store only scrubbed operational receipts in an ignored run directory: commands without credentials, resource IDs, timestamps, exact configuration, artifact manifest, container/Image identifiers, response envelopes for constructed prompts, latency, logs needed for identity, billing reads and deletion results. Do not use or record user conversations.

## Gate A: account and safety preflight

The root operator completed the account-access portion without creating compute:

| Check | Verified result |
|---|---|
| Client | isolated Modal 1.5.5 environment |
| Authentication | App listing succeeded |
| Existing Apps | none listed |
| Billing summary | $0 metered and $0 billed |
| Account L4 rate | $0.80000/GPU-hour |
| Account CPU rate | $0.04730/physical-core-hour |
| Account RAM rate | $0.00800/GiB-hour |
| Account Volume rate | $0.09/GiB-month |

These account-specific rates supersede rounded public-page arithmetic for the pilot. The proposed 2-core, 32-GiB, one-L4 container is **$1.15060 per billed container-hour**, with Volume storage separate. At the time of this historical account preflight, no GPU, App, Image or Volume had been created. The later owner authorization recorded above opened the bounded execution phase.

The preflight proposed **$2.00 plain baseline, $2.50 snapshot preparation/restores, and $0.50 storage/build/reconciliation contingency**. Root may rebalance these internal allocations within the owner-authorized $5 total ceiling; do not silently raise that ceiling. At the verified resource-inclusive rate, these are conservative time guards rather than expected costs. Credits are not assumed to reduce the ceiling.

Start an external root-owned watchdog before the first resource write. It must outlive the invoking client, know the App/resource identifiers once created, stop the App at the phase deadline or tranche ceiling, and then verify zero running containers. A local watchdog is a backstop, not evidence that Modal enforces the $5 ceiling.

Before the first write, the root operator must allocate the bounded cost within the owner-authorized scope and finish the watchdog, private-access, receipt-storage, available-balance and teardown preflight. Credit eligibility and GPU provisioning capability are not established by the successful read-only checks. If any is uncertain, stop before deployment.

## Gate B: plain cached baseline

Deploy one private App with snapshots and vLLM sleep mode disabled. Set zero minimum and one maximum container before the first request. Use a short constructed English engineering prompt with low reasoning and a small output cap; do not use Bible evaluation cases or conversation history.

The baseline sequence is:

1. Start the one-container App and record the deployment, Image, Volume and autoscaler configuration.
2. Send one request from scale zero and measure submission-to-first-visible-content, submission-to-finish and server-reported processing time separately.
3. Require logs and `/v1/models` to establish L4 hardware, vLLM 0.29.0, the pinned local model/tokenizer directory, native MXFP4 loading, 8,192 context, eager execution, one sequence and the expected base model ID.
4. Send one identical warm request and preserve its complete response and timing.
5. Allow scale-down, verify zero live containers through Modal state and billing evidence, then perform at most two additional scale-from-zero requests if the baseline tranche permits.
6. Stop the App and verify no live compute before assessing the gate.

The baseline passes only if all authorized requests finish, identity evidence is complete, the output is usable, the App actually scales to zero, teardown is verified and the phase stays within its allocation. Stop before snapshots on OOM, unsupported kernels, wrong revision, BF16/other precision fallback, larger-GPU substitution, timeout, uncertain request state, unbounded billing or missing teardown evidence. Preserve the failure; do not repair it by changing the frozen stack inside this comparison.

## Cancellation and completion races

Give every request a locally generated nonce and record its start time before submission. The server wrapper may log only nonce, phase, timestamps, status, model ID and token counts; it must not log prompt text. A client timeout or cancellation does not prove remote work stopped.

On timeout or interruption:

1. do not resubmit;
2. check the bounded provider state and scrubbed server log for the same nonce;
3. if completion won the race, preserve the completed response and charge it once;
4. if work is still running, allow only the remaining request deadline, then stop the App;
5. if neither completion nor termination can be established, mark the request **outcome uncertain**, stop and verify zero compute.

Teardown must not erase a completed response before it is saved. An uncertain request is never retried inside this pilot.

## Gate C: GPU snapshot comparison

This gate opens only after Gate B passes and the snapshot tranche is still explicitly allocated. Deploy a second private App with every baseline pin unchanged, then add only:

```text
enable_memory_snapshot=True
experimental_options={"enable_gpu_snapshot": True}
VLLM_SERVER_DEV_MODE=1
vllm serve ... --enable-sleep-mode
```

In `@modal.enter(snap=True)`, start vLLM, wait for health, run fixed constructed warmups, confirm no request is in flight, call local `POST /sleep?level=1`, and verify sleeping before returning. Level 1 backs model weights in CPU RAM and discards the KV cache. In `@modal.enter(snap=False)`, call local `POST /wake_up`, wait for health and do not accept external traffic until wake completes. Internal development endpoints must bind behind the authenticated service and must not be exposed to callers. vLLM explicitly warns that its development endpoints should not be public. [Modal vLLM snapshot pattern](https://modal.com/docs/examples/lfm_snapshot), [vLLM 0.29 sleep mode](https://docs.vllm.ai/en/v0.29.0/features/sleep_mode/), [vLLM security](https://docs.vllm.ai/en/v0.29.0/usage/security/)

Snapshot creation starts are preparation, not restored cold-start samples. Modal says GPU functions may need two or three snapshots per GPU type. Require the Containers marker or exact log evidence that a request restored a snapshot before classifying it as such. After verified restoration, run the same constructed baseline prompt and collect at most three restored cold starts plus one warm request, within the tranche. Compare the same latency boundaries and billed runtime; do not compare a snapshot-creation start with a plain cold start. [Modal snapshot verification and invalidation](https://modal.com/docs/guide/memory-snapshots#memory-snapshots-faqs)

The snapshot gate requires:

- a verified restored snapshot on exactly one L4;
- the same engine, model/tokenizer bytes and runtime limits as baseline;
- complete, correctly identified responses before and after restore;
- no evidence that warmup KV state survived the level-1 sleep;
- confirmed scale-to-zero and teardown; and
- measured improvement assessed against added complexity and billed time, without assuming a speedup.

Modal cautions that GPU snapshots may not help storage-bound weight loading and can make it slower. Eager mode removes most compilation work that snapshots commonly skip, so a small or negative result is plausible. GPU snapshots are Alpha, and most multi-GPU code is incompatible; this proposal remains single-GPU. [Modal GPU snapshot limitations](https://modal.com/docs/guide/memory-snapshots#limitations-of-gpu-memory-snapshots)

Changing code, configuration or GPU type invalidates a Modal snapshot, while changing Volume contents does not. Keep the Volume immutable during this pilot. Any future model, tokenizer or adapter bytes require a new content-addressed directory plus an explicit snapshot-version constant and redeployment. A later adapter test must independently prove exact PEFT byte identity and matched base/adapter behavior both before sleep and after restore; no conclusion about LoRA portability follows from the base snapshot test.

## Decision record after the pilot

Report preparation time/cost, plain cold and warm measurements, scale-down behavior, snapshot-creation attempts, verified restore measurements, failures, teardown and billing reconciliation separately. Do not report App uptime as GPU runtime or treat credits as zero cost. The outcome may support a later hosting proposal; it does not authorize adapter training, migration from Inkling B, production deployment, publication or public weight access.
