# Concurrent beta serving

September 12, 2026. The owner wants to invite people to try Meforash through social media. The previous global single-answer gate is an application constraint, not an established provider limit. The original private preview and frozen experiments remain unchanged.

## Design

Use one Railway service/process/replica with three independent retained-B model workers and a bounded FIFO waiting queue. Each worker owns its own transport; conversations and result tokens remain isolated by authenticated identity. One identity can have only one outstanding question. Twelve additional requests may wait, with a 120-second queued-only deadline. A full queue rejects new work before allowance reservation. A request that times out before submission releases its reservation and question allowance.

The shared SQLite ledger still enforces cost admission across all workers. Parallelism does not multiply the global cap. The current $5 estimated global ceiling is cumulative, not a daily allowance; known costs and unresolved reservations count against it. Account daily allowances are separate. Increasing concurrency makes spending accumulate faster when more people ask questions; it does not promise lower cost per answer.

The serving model, source selection and training are unchanged. Workers do not share a transport pipe. Blocked slots stop receiving work, while other healthy slots may continue. If every slot is unavailable, new work rejects before charging quota; uncertain submitted requests are never automatically retried. Queue abandonment in a browser is not a cancellation request. An operator restart can interrupt active answers; their uncertain accounting is preserved. On restart, ledger rows still marked reserved can be released because the submitted marker is committed before any provider call. Submitted and legacy running rows remain uncertain.

This does not enable multiple Railway replicas: results and scheduling are process memory. Shared distributed admission and result storage would be separate work. Queued conversation content remains in memory rather than being written to the usage database.

## Provider and capacity evidence

Tinker's official [concurrent sampling guide](https://tinker-docs.thinkingmachines.ai/tutorials/basics/async-patterns/) supports independent simultaneous requests. It does not guarantee this account's maximum throughput or latency. Its [pipelining documentation](https://tinker-docs.thinkingmachines.ai/tinker/under-the-hood/) describes throughput-oriented scheduling and warns against application retries that duplicate work. This change preserves the application's existing timeout and conservative uncertain-cost handling, without adding retries.

The current Railway container reports an 8 GB memory limit and an 8 CPU quota. Those are resource ceilings, not prepaid allocations or proof of sustained capacity. Live overlapping requests and memory must be checked with the three-worker setting. Railway bills actual resource use, not the full ceiling: its [published rates](https://docs.railway.com/pricing/plans) are $10 per GB-month of RAM and $20 per vCPU-month, with other usage and plan terms separate. A brief memory sample is not a monthly invoice estimate.

A modest social announcement is the intended scale. This is not a viral-traffic or availability guarantee. Observe waiting time, saturation, provider errors, memory and the remaining budget; adjust only from measured results.

## Verification

Integration passed 612 source-only tests plus three independent pool-failure tests (615 distinct tests), with 94 asset-dependent exclusions. All 27 browser scenarios passed, and a 390-pixel Chromium check verified queue position, distinct waiting/generation time and no overflow. Live verification passed on application commit `7a287ef`. A bounded four-question live probe returned HTTP 202 for all four identities. Three requests were observed running together within 0.3 seconds. The fourth waited 17.35 seconds before generation and then completed in 4.84 seconds. The three initially running requests completed about 17.5–20.0 seconds after submission; all four completed within 22.48 seconds. Cross-user result polling was denied. These are short constructed engineering probes, not a latency distribution, traffic benchmark, or new biblical-accuracy evaluation.

The ledger increased by four completed requests and $0.00743893 estimated inference cost, with no new unresolved reservations. This is a local token-price estimate rather than an invoice; longer questions, history and responses can cost more. No generation was retried, and no model training, export or weight publication occurred.

Railway runtime settings were read back as three workers, queue capacity twelve and timeout 120 seconds. Live JavaScript bytes matched the reviewed files. The warmed container's sampled memory was approximately 2.88–2.89 GB (about 2.70 GB anonymous memory), below its 8 GB limit. At current RAM pricing, a sustained comparable usage level would represent roughly $27–29/month in RAM usage alone; CPU, volume, network, plan accounting and inference remain separate. This is an illustrative projection, not a billing measurement. The app's $5 inference guard does not cap Railway charges.

After the probe, health was ready and idle with the provider initialized. This supports a modest “try it out” announcement with the stated caps; it does not establish viral-traffic capacity. Queued expiry and failed-worker behavior were exercised offline rather than by deliberately breaking the live provider.
