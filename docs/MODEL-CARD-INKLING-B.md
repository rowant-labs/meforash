# Inkling B model card

September 9, 2026. **B is an experimental original-language Bible LoRA adapter, currently retained for the private English chat.** This card describes the project checkpoint; it does not distribute weights or certify historical, linguistic or theological accuracy.

## Intended use and behavior

English exploration of biblical passages, translation and grammar, historical interpretation, and Bible-based non-denominational reflection when requested. The application should distinguish source wording, interpretation and contemporary reflection, preserve uncertainty and user agency, and avoid claiming divine authority. Appropriate practical assistance remains relevant when a conversation concerns health or immediate safety.

The intended whole-Bible experience exceeds the historical evidence coverage currently implemented. B is not a recovered original Bible, a manuscript apparatus, an expert translator, or a substitute for checking consequential claims against reliable sources.

## Base and adaptation

Base: full `thinkingmachines/Inkling`, served through Tinker. This is distinct from Inkling-Small and from unchanged Inkling. The provider base revision was not pinned; the project pinned its tokenizer/rendering assets and recorded its local software and training recipe.

B uses rank-8 LoRA with attention, MLP and unembedding adaptation. A fresh adapter completed one development-corpus pass: **136 updates, 3,280,433 processed input positions and 3,229,825 loss-bearing positions**. Training optimized original-language next-token prediction. B did not receive the later English instruction datasets used by C–F or the proposed G dataset merely because those experiments share the project.

The prepared source inventory contains 31,152 verse records across 66 book files. Training preserves a chapter-family validation split. Hebrew and Aramaic use the selected WLC main/ketiv layer through OSHB; Greek uses the selected SBLGNT main text. See the [source card](SOURCE-CARD.md) and [training record](INKLING-TRAINING.md).

The private application adds an English policy prompt and explicit passage lookup at inference. Those application features are distinct from B's weight updates. Retrieved source cards identify supplied evidence; they do not independently verify every generated claim.

## Evaluation evidence

A fixed twelve-window held-out Hebrew/Greek diagnostic showed **77.3% lower negative log likelihood** after the original-text pass. This measures text prediction, not translation accuracy, and contains no Aramaic validation result.

In a small AI-reviewed English comparison, B was preferred to unchanged Inkling on 11 of 24 Bible questions, less preferred on four, and tied on nine. This is development evidence with project-role overlap, not an expert-reviewed accuracy rate or a whole-Bible claim. Subsequent E/F instruction continuations did not establish an answer-quality gain over B, so B was retained. Full findings and limitations are in the [adaptation review](INKLING-ADAPTATION-RESULTS.md), [instruction comparison](INKLING-INSTRUCTION-RESULTS.md), [calibration comparison](INKLING-CALIBRATION-V2.md), and [target-revision comparison](INKLING-REVISION-RESULTS-V3.md).

The later guidance comparison also failed its adoption gate. Candidate G is a separate experiment and must be judged from its prospective evidence before any model selection changes.

## Serving, data and release limits

Private checkpoint inference works. The sampler and training-state checkpoints were verified as private and unexpired on September 9; both are scheduled to expire October 6 unless retention is changed. No verified external conversion, base-weight match, third-party load or restoration test is recorded. A code release therefore does not provide a self-hostable B model.

The private preview retains no chat logs and does not use user conversations as training data. Messages are sent to the model provider to obtain answers. A future hosted service needs explicit authentication, durable usage accounting and an accurate provider-processing notice.

Project code/documentation licensing is separate from source, base-weight and adapter-release obligations. No adapter download is included in the initial source scaffold. Review the [publication policy](PUBLICATION.md) and [serving feasibility](INKLING-B-SERVING-FEASIBILITY.md) before releasing or moving the checkpoint.
