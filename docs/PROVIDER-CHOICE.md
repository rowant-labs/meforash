# Training provider choice

Checked September 5, 2026 against current official documentation. **Use Tinker for the first original-language-only adaptation experiment; keep Together as the managed backup.** Public hosting remains a separate deployment decision. This recommendation is about our actual dataset, learning objective, and budget, not a claim about provider market share.

## Comparison for this project

| Option | Fit for the original-text experiment | Compute estimate for one complete pass | Hosting consequence |
|---|---|---|---|
| Tinker, gpt-oss-120b | Direct token sequences, next-token targets, and loss weights; preserves the prepared objective | $2.57 at $0.737/M, default 32K offering | Checkpoint API fits private evaluation; public serving still needs validation |
| Together, gpt-oss-120b | Generic text and pretokenized data supported; conversion must follow its label/mask convention | About $17.41 at $5/M, above its $6 job minimum | Fine-tunes use dedicated endpoints or downloaded weights |
| Fireworks managed SFT | Current documented input is chat messages; this route has not established equivalent raw-token adaptation | $6/M headline rate is not an equivalent quote for this experiment | Custom LoRAs require dedicated deployment |
| Fireworks Training API | Tinker-compatible token/loss loop fits; the priced shared pools do not currently list gpt-oss | Model-specific dedicated GPU quote needed for this candidate | In-session sampling; production custom LoRAs still use dedicated deployment |
| Unsloth on rented hardware | Explicit raw-text continued-pretraining support with more control over the training environment | Depends on hardware, throughput, and setup time; not measured | Requires operating or arranging a separate inference service |

Training estimates use the locally measured 3,482,204 input-token positions and one pass. Provider-specific packing, loss masks, padding, validation, minimum billing, sampling, and retries can change the bill. These are not demonstrated quality results or monthly hosting prices. Tinker and Together also offer gpt-oss-20b; the current rate-based estimates using the same token count are about $1.38 and $5.22 respectively, subject to tokenizer and configuration parity checks.

Tinker's [cross-entropy interface](https://tinker-docs.thinkingmachines.ai/tinker/losses/cross-entropy/) gives the necessary token-level control. Its [pricing](https://tinker-docs.thinkingmachines.ai/tinker/models/) confirms the 120B and 20B rates. The [checkpoint API](https://tinker-docs.thinkingmachines.ai/tinker/compatible-apis/openai/) is still beta for testing and low internal traffic. Its separate serverless inference beta lists only Inkling and Inkling-Small, so it is not a production gpt-oss hosting commitment.

Together explicitly documents [generic text and pretokenized formats](https://docs.together.ai/docs/fine-tuning/data-preparation), [gpt-oss support](https://docs.together.ai/docs/fine-tuning/supported-models), and [training rates/minimums](https://www.together.ai/pricing). Its pipeline shifts next-token labels internally: our already shifted rows must be converted deliberately, not uploaded verbatim. Its [gpt-oss LoRA targets](https://docs.together.ai/docs/fine-tuning/lora-vs-full) are attention projections, which must be recorded when comparing with a different provider's adapter coverage. [Deployment guidance](https://docs.together.ai/docs/fine-tuning/deployment) offers dedicated inference or checkpoint downloads.

Fireworks now offers a [Tinker-compatible Training API](https://docs.fireworks.ai/fine-tuning/training-api/introduction), a relevant recent option beyond its managed fine-tuning jobs. Its [serverless documentation](https://docs.fireworks.ai/fine-tuning/training-api/serverless) and [pricing](https://fireworks.ai/pricing) list shared training pools for Qwen3.8-27B, Kimi K3, DeepSeek V4 Flash 0731, and Muse Glimmer 30B. The page says generally available, while the overview and storage-pricing language still refer to private preview. Confirm actual account/model access before relying on that route. The [managed SFT documentation](https://docs.fireworks.ai/fine-tuning/fine-tuning-models) requires `messages[]` and rejects the old custom template override in Training V2; wrapping the Bible in assistant messages would change the raw-text experimental setup.

Unsloth's [continued-pretraining guide](https://unsloth.ai/docs/basics/continued-pretraining) explicitly supports raw text. It remains a useful route for more local control or a smaller model, but it adds GPU environment setup and operation that the initial Tinker experiment avoids.

## Recent use and what it establishes

Tinker's current [project examples](https://thinkingmachines.ai/tinker/) include forecasting with Mantic, agent research with Trajectory/Stanford, and formal mathematics with Axiom Math. These are evidence of active research use, not evidence that Bible translation will improve. Fireworks' token-level API and Together's raw/pretokenized dataset support show that all three remain relevant options. No credible comparative adoption count was established in this review; customer logos, anecdotes, and launch claims cannot identify a universal “most used” service.

## Decision and next steps

Get a Tinker key first; no second provider account is required just to configure this project. Keep the original-text experiment and English baseline on the same base/provider where possible. Validate actual model access, tokenizer parity, completion quality, and billing on a small run before adaptation. Build the Tinker-specific sampling/training connection after local access is configured; the existing generic baseline runner is not itself a Tinker sampler-creation workflow.

A successful adapter must still be exported and loaded on a feasible serving system. Neither the cheap base-model APIs nor the current Fireworks/Together dedicated deployment descriptions establish a low monthly price for a lightly used public Bible app. Training and hosting can use different providers after exact adapter compatibility is demonstrated. Revisit Fireworks shared pools if the chosen model changes, its catalog adds gpt-oss, or a suitable shared custom-adapter hosting service becomes available.
