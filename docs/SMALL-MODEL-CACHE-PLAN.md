# Pinned-cache startup experiment

Prepared September 12, 2026, on the isolated hosting exploration branch. The bounded first attempt is recorded in [v3 results](SMALL-MODEL-SERVING-RESULTS-V3.md); it did not reach completed cache preparation. This is an experimental plan, not a training recipe or deployed configuration.

Runpod's [cached-model documentation](https://docs.runpod.io/serverless/endpoints/model-caching) describes host-side model downloads before worker startup, with no worker billing during that download phase. It may improve cost even when a cache miss still delays the user. GPU loading and engine initialization remain; do not promise a seconds-long response from caching alone.

Current REST v1/v2 create schemas do not expose a documented `models` field for this attachment. Use the official CLI's [model-reference option](https://github.com/runpod/runpodctl/blob/main/docs/runpodctl_serverless_create.md) or the Console. The CLI uses GraphQL for model references. Never silently send an unsupported REST field and interpret HTTP success as evidence that caching was configured.

Cache reference for this candidate:

```text
https://huggingface.co/openai/gpt-oss-20b:6cee5e81ee83917806bbde320786a8fb61efebee
```

Keep model and tokenizer environment revisions pinned to the same commit. Keep the previously verified image digest and record the exact CLI version used. Check [model-status](https://github.com/runpod/runpodctl/blob/main/docs/runpodctl_serverless_model-status.md) for the resolved version hash and assignment status, then separately verify the effective engine revision in startup logs. A cached directory's presence does not prove it was used. Do not pick an arbitrary snapshot directory or switch to `main` to repair a cache miss.

Use zero Active workers, one maximum Flex worker and the existing bounded cleanup process. Compare initial cache miss, confirmed cache hit and a request after scale-down separately. Record billed worker time as well as user waiting time. `ENFORCE_EAGER=true` skips compilation and CUDA graphs according to [vLLM's optimization guide](https://github.com/vllm-project/vllm/blob/main/docs/configuration/optimization.md); changing it can affect decode speed, so keep it fixed within a cache comparison. Hardware, host placement and caching are confounders in an uncontrolled first-boot comparison.

Do not enable Hugging Face offline mode before confirming the pinned cache is usable. If a private adapter is introduced later, provide it explicitly and retain its hash: a cached base alone does not include our adaptation. No public weight release is required.

Acceptance evidence: matching cache/engine revisions, successful complete answers, visible-content latency, initialization breakdown, worker memory, provider bill, and verified teardown. Stop after the bounded pilot if the cache is unavailable or the model fails; preserve failures rather than repeatedly provisioning new hardware.
