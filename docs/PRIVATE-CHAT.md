# Private chat preview

Implemented September 6, 2026. The conversational model is **full Inkling with the retained original-language adapter B**, trained on the development split of the selected Hebrew/Aramaic OSHB/WLC and Greek SBLGNT editions. The app uses this actual fine-tune for every answer; it does not fall back to an unchanged model. The [training record](INKLING-TRAINING.md) and [latest comparison](INKLING-REVISION-RESULTS-V3.md) explain why B was retained.

This makes the trained model available for ordinary English conversation, focused translation questions, and Bible-based reflections when the question calls for application. It is a research preview. The selected editions are not a complete reconstruction of the earliest recoverable text, and the model retains influences from its original pretraining. Additional early witnesses and historical context remain the [next collection milestone](HISTORICAL-EVIDENCE-MILESTONE.md).

## Run locally

From the project directory, with the existing local environment and Tinker key in `.env`:

```sh
.venv/bin/python -m bibleprep.chat_server
```

Open [the private chat](http://127.0.0.1:8765/). `--port 8766` changes the port; `--budget 5` sets the estimated sampling allowance for that server process. Stop the server with Ctrl+C. Reload the page after a server restart to establish a new local session.

The current workspace already has the prepared sources, runtime and private B checkpoint records. A new clone needs the [source preparation](PRETRAINING-READINESS.md#reproduce-the-preparation), [Inkling runtime and training artifacts](INKLING-TRAINING.md), and the retained private checkpoint records. Those operational records and the adapter are not bundled in the public scaffold. Public-clone inference and adapter export/load reproduction are therefore not yet established. A key alone cannot recreate the trained model.

Only loopback connections are accepted. The provider key stays on the server and is loaded only when an answer is requested. Opening the page does not request model generation. Source lookup runs locally; sending a chat turn requests provider generation. The Ready indicator checks local configuration; it does not verify provider credentials or available funds.

## What passage lookup supplies

The local library contains **31,152 source verse records** from the complete selected editions. Training used their development split, so this lookup inventory is larger than the training split. The library verifies the prepared source bytes against their manifests.

An explicit passage reference adds the original-language excerpt to the model's input. Follow-up questions without a new reference can inherit the latest earlier referenced turn, with that behavior disclosed in the source notes. The interface shows the exact excerpts supplied, their edition, source link, reading-layer notes and any reference-numbering conversion. These cards record input evidence; they do not independently verify every claim in the answer.

Questions without an explicit or inherited reference still receive an answer from the fine-tuned model's learned knowledge. The app discloses that no source excerpt was supplied. It does not yet search for topical passages, browse scholarship, or retrieve historical dossiers automatically.

- **Hebrew/Aramaic:** OSHB/WLC main/ketiv wording, with qere excluded from the supplied excerpt. A conservative STEP-derived map covers 2,021 unambiguous whole-verse English-to-MT correspondences and blocks 14 split, empty or marked rows. Untabulated references keep their coordinates, and every target must exist. This is not a universal alignment for every translation. An explicit adjacent `MT`, `WLC`, `OSHB`, or Hebrew-numbering qualifier requests source coordinates.
- **Greek:** SBLGNT edition coordinates and original editorial brackets are retained. Doubtful and double-bracketed supplemental text remains visibly labeled. Numbering may differ from an English edition; an absent source verse is not filled from another text.
- **Limits:** up to three passage references and forty verses per request, with single-chapter ranges. Unsupported subverse, comma-list, split or cross-chapter references receive a source note instead of an invented alignment. A chapter-only request asks for a verse range. Omitted context is disclosed.

For example, ordinary English Psalm 51:10 maps to WLC Psalm 51:12. The source drawer shows both references. Mapping provenance, changes and attribution are in the [manifest](../manifests/chat-versification-v1.json) and [STEP notice](../licenses/STEP-VERSIFICATION.md). Rebuild it from the pinned public source with:

```sh
.venv/bin/python -m bibleprep.versification --fetch
```

This command performs no model call and changes no training dataset.

## Conversation, cost and privacy

The server permits one model request at a time, with a 24,000-token input ceiling, an 8,192-token output ceiling and a 300-second deadline. Output includes only the model's final answer; hidden reasoning is not displayed or logged. Incomplete final answers are labeled. Overlong conversations are rejected rather than silently shortened.

The default allowance is **$5 estimated sampling per server process**, using the recorded September 6, 2026 input/output prices of $1.87/$4.68 per million tokens. A full-size request reserves about $0.0833 before starting, then reconciles to its returned token estimate where available. An uncertain failure retains the reservation. These are local controls and estimates, not a provider invoice or an account-wide spending limit; restarting starts a fresh allowance. Recheck rates before changing operating assumptions.

The app does not automatically retry model requests. A network interruption while polling can be recovered with **Check for answer**, which only checks the same job. If a provider request becomes uncertain, the model connection is blocked until the server is restarted.

Conversation text is sent to **Thinking Machines / Tinker** for inference. The app writes no chat logs and uses no browser storage or analytics. Browser history for the conversation remains only in the page's memory. The server also holds pending work and recent completed results in memory: on later submission or polling activity, it removes completed results older than fifteen minutes and trims to twenty recent completed results. This is activity-triggered cleanup, not a timed deletion guarantee; with no later activity, results can remain in memory until shutdown.

**New chat** clears the page's conversation and hidden source cards. It does not cancel a provider request already in progress or immediately erase the server's temporary result. Stopping the server clears its result store. User conversations are not collected for training. These statements describe this app's behavior, not the provider's retention policies.

The server uses a random HttpOnly/SameSite local-session cookie, strict host/origin checks, a small static-file allowlist, bounded JSON requests and safe error messages. It does not serve workspace files. This local preview has no public account system, deployment configuration or production multi-user service. Existing checkpoint retention is thirty days; export compatibility, permanent preservation and public custom-adapter hosting remain separate work.

## Verification

Offline checks cover checkpoint selection, native message formatting, final-only output, timeout behavior, request validation, local access controls, budget reservation, worker lifecycle, source integrity and verse-numbering edge cases. Browser smoke checks use constructed questions to exercise real answers, follow-ups and source display. These are engineering checks, not a new comparative benchmark or scholarly accuracy certification. Private execution records remain outside the public scaffold.

The initial live browser check completed **four of four constructed requests**, without retries: a Hebrew translation question, a three-sentence follow-up, an English-to-Hebrew verse-numbering case and a broad forgiveness question. The answer/source drawer correctly exposed Psalm 51:10 → Hebrew 51:12, inherited passages and the absence of supplied sources on the broad question. Source display was checked at a 390 × 844 phone viewport. The maximum reservation for the four requests was under $0.34; actual provider charges were not separately reconciled.

The check also exposed a quality limitation: the translation-focused Micah answer kept *hesed* transliterated before explaining it and added unsolicited modern application. Quotations and historical assertions in the broad answer were not independently certified. These observations are recorded for later evaluation; no prompt or model changes were made in response during this check.

Source preparation update, September 7: [eight historical-evidence research drafts](EVIDENCE-FIRST-PACK.md) now exist outside the chat source library. They remain pending review and use decisions, so the preview’s answers still use the same B checkpoint and original passage lookup described above.
