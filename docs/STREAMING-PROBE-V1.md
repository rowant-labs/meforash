# Streaming transport probe — September 11, 2026

Retained B remains the live model on its established native, final-only transport. No training or production transport change occurred.

A bounded engineering probe used one constructed Hebrew lexical question, the current system instructions, temperature zero, the existing seed, medium thinking effort, a 2,048-output-token cap and a combined $0.05 estimated ceiling. This is not an answer-quality benchmark. Checkpoint provenance and current metadata were checked before sampling; metadata reported no expiry. Private receipts are in `runs/launch-v1/streaming-probe-v1/`.

## Results

- **Compatible chat streaming:** HTTP 200, two answer chunks separate from reasoning, first answer at 8.309 seconds, complete at 9.320 seconds, stop finish. Reported 377 input / 168 output tokens; the native rendered input also contained 377 tokens. Estimated sampling cost $0.00149123. Equal token counts do not establish identical rendering or answer behavior.
- **Raw token-list completion:** HTTP 422 validation rejection. No answer generation observed. No uncertain request was retried.
- **Raw rendered-text completion:** HTTP 200, 37 text chunks, first chunk at 7.052 seconds and completion at 43.498 seconds. Provider reported 415 input tokens versus 377 native input tokens. Output ended at the length limit, and the official native parser found no completed or partial final answer. The returned text retokenized to 2,043 tokens while provider usage reported only 31 completion tokens; this usage cannot be trusted for exact cost reconciliation. Retain a conservative reservation based on the output cap rather than the reported 31 tokens.

## Decision and next step

Do not promote raw completion streaming as a drop-in replacement. Compatible chat streaming is promising but changes the rendering boundary to the provider. Before enabling it, freeze a small transport comparison spanning Hebrew, Greek, contextual follow-up and source attribution; compare native and compatible chat with the same retained checkpoint, prompts, effort, temperature, seed and caps. Verify final-only output separation and accounting, including missing or inconsistent usage. This is transport validation, not new fine-tuning or a new model choice.

Then implement progressive final-answer delivery behind a default-off switch, test interruption and quota behavior, and verify one hosted response before enabling it. A streaming parser or compatible API alone does not prove production readiness. Provider documentation describes the compatible API as beta for low internal traffic.

Sources: [Tinker compatible inference](https://tinker-docs.thinkingmachines.ai/tinker/compatible-apis/openai/), [Tinker pricing](https://tinker-docs.thinkingmachines.ai/tinker/models/).
