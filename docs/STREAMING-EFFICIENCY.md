# Streaming and serving efficiency

September 12, 2026. The owner approved direct Railway-to-browser streaming, reducing duplicated rendering memory, and a controlled ten-request test. Retained adapter B, its rendering/token validation, reasoning setting, source context and accounting rules stay unchanged. No training, export or weight publication is part of this work.

Current owner direction: deploy the streaming and memory improvements with three live model workers. The earlier ten-request live probe is deferred. Do not send a provider inquiry.

## Intended implementation

Replace routine browser polling with an authenticated event stream from Railway. The browser still submits questions to our server; no provider credential or direct provider endpoint is exposed. Event streams contain only the same safe answer/status/source fields as authenticated polling. Reconnection can recover the existing request, never submit a replacement paid generation. Stream counts, socket waits and lifetimes are bounded; session revocation and cross-user ownership remain enforced.

The heavier renderer/tokenizer runtime can be shared in one quiet child process. Each provider HTTP request remains separately correlated and limited; rendering/tokenization are serialized where needed, while network streams overlap. Exact prompt rendering, input caps, answer-token lower bounds and provider usage validation are retained. Provider reasoning and response bodies stay inside the quiet child. Abandoned provider operations remain counted until finished; they are not automatically retried.

A failed provider request should block only its logical worker. A failed shared process is a shared failure domain: affected requests fail conservatively, and initialized transports must report unavailable before new reservations. This memory tradeoff requires explicit failure tests, not just a successful load test.

## Provider constraint

The current [Tinker compatible endpoint documentation](https://tinker-docs.thinkingmachines.ai/tinker/compatible-apis/openai/) identifies the endpoint as intended for testing/low internal traffic, not large high-throughput public deployments. A successful controlled test does not override that guidance or establish a service-level commitment. Public-serving suitability and account throughput need confirmation from Thinking Machines; its [support page](https://tinker-docs.thinkingmachines.ai/support/index.md) identifies the customer-support contact.

The provider question is prepared privately. No provider support message has been sent without owner authorization. Technical implementation and provider confirmation are separate completion states.

## Validation plan

Run offline tests for split UTF-8/event boundaries, event reconnects, ownership/revocation, subscriber limits, shared-profile reuse, interleaved response isolation, deadlines, abandoned work, shared-process death and exact usage validation. Then perform three overlapping short-question streams with the actual B adapter for a combined maximum local inference reservation below $0.30. No generation retries are authorized by this probe.

Use the existing operator access and two ordinary guest sessions without weakening guest rate limits. Measure the probe's process memory separately where possible. Preserve private receipts and publish only aggregate engineering results. A successful test is not an accuracy evaluation or a broad production capacity guarantee.
