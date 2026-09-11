# Evidence attribution audit v1

Status: bounded diagnosis of the completed known-topic evidence pilot. It preserves the frozen protocol, answers, reviews, receipts, source components, original-language strings, notices, registry decisions, B checkpoint, and private chat unchanged. No generation, training, source promotion, or new evaluation case occurred.

## Observed failure

The post-freeze parent audit found two errors in one Daniel 2:4 lookup answer. It expanded a verse-specific Hebrew-to-Aramaic boundary observation into a Hebrew range that includes Aramaic speech, and it attributed a project-authored English gloss to the upstream OSHB/WLC edition. This answer remains frozen and the predefined review scores are unchanged.

The checked source facts are narrower and internally consistent. The pinned Daniel XML changes its language annotation within Daniel 2:4, and the following verse remains Aramaic-tagged. The selected record limits its boundary observation to Daniel 2:4 and separately identifies the English gloss as project-authored and unapproved. The audit does not independently establish historical originality, vocalization, manuscript coverage, or the cause of the model output.

## Packaging diagnosis

The current renderer preserves the exact selected objects, but it gives the model a flat compact JSON block without field-semantics guidance. Two field groupings plausibly encouraged the mistakes:

- Every selected component repeats a citation locator spanning several Daniel verses beside a verse-specific boundary claim. The locator identifies consulted source locations; it is not the scope of the component claim. A record-level coverage limit likewise describes checking activity, not the language of the whole range. Neither distinction is stated in the current wrapper.
- The reading object places the edition identity, cited source, original representation, English rendering, and rendering author together. The current prompt says to preserve attribution, but does not state that `rendering_author` controls attribution of `english_rendering` or forbid assigning a project gloss to the edition. Repeated long source notices add competing attribution language without changing that field relationship.

These are evidence-backed affordances and a plausible causal account, not proof of causation. One sampled output cannot isolate which field, ordering choice, prompt phrase, or model prior produced either error. Packet and lookup received identical evidence, and their answer differences are sampling variability.

## Minimal versioned change proposed

Add new, versioned guidance to the trusted system message that accompanies the byte-identical v1 `render_model_input(...)` result. The guidance must remain outside the quoted evidence-data field. Keep the v1 renderer and every old artifact unchanged, and run the existing registry, component, citation, source, scholarly-review, notice, and current-use verification on every call before assembling the messages. The guidance should state:

1. A claim is limited to its own component text and limitations. Citation locators identify where a source was consulted; they do not enlarge claim scope. `coverage_limits` describe coverage and constraints, not positive source facts.
2. For a reading, attribute `english_rendering` only to `rendering_author`. Attribute the original representation, edition metadata, and source annotations according to their own fields and citations. Do not say an edition translates or renders an English gloss unless its source fields explicitly establish that authorship.
3. Do not infer language, wording, attestation, or other facts for adjacent verses or ranges from a locator, record coverage, or component proximity. State only relationships expressed by the selected components.
4. Answer in readable English. Internal IDs, commit hashes, and full notice prose remain available in the verified evidence/display metadata and should be repeated in the prose answer only when needed for the question or attribution.

This small wrapper retains exact source components, original strings, full notices, and registry verification. It needs a new version and hash binding so callers cannot confuse guided input with the frozen v1 input. It requires no registry schema or source-record change. It does not show that future answers are fixed; that requires a separately frozen comparison on fresh source families. This audit creates no questions or answer samples.

The machine-readable audit and exact input hashes are private at `runs/evidence-attribution-v1/audit.json`.
