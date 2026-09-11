# Project charter

Updated 2026-09-05.

## Purpose

Create a conversational model that people can use in English to understand biblical texts close to their earliest recoverable forms and historical settings. Adapt a capable existing open-weight LLM using the whole biblical corpus, and evaluate whether the adaptation improves translation, interpretation, and English question answering.

The project covers broad and specific questions: the meaning of a word or verse, relationships across books, historical context, and possible implications for present-day life. Users should not need to read Greek, Hebrew, or Aramaic, know a verse reference, or understand model training to use it.

## Commitments established by the project owner

- Whole-Bible coverage is the training objective. A small engineering calibration run does not redefine the product as a limited-passage app.
- Actual model adaptation is central. Begin by testing training on original-language texts; translation or instruction examples can be added as measured comparisons.
- The existing model supplies broad language and reasoning abilities. Evaluate those abilities instead of assuming either perfect competence or guaranteed improvement.
- An eventual public conversational application is the product goal.
- Open-source development and inspectable choices are project requirements. Initial development may be private; public development before app launch is also acceptable.
- Keep personal data, credentials, private chats, and internal operational records out of public releases.
- A U.S.-developed model is a preference, not an absolute restriction.

## Working answer contract

Provide a useful English answer first. Supply relevant text and an explanation of important translation choices when they help. Let the user inspect the source edition, evidence, and uncertainty without requiring them to navigate technical machinery.

For historical questions, distinguish the wording of a witness or edition, proposed earlier wording, likely ancient meaning, and later interpretations. For life questions, make the move from historical interpretation to contemporary reflection visible. The historical evidence alone does not determine every present-day moral or practical judgment.

The accepted default follows the question's intent. When a question is clearly life-applicable or points toward personal application, offer Bible-based reflections without a denominational frame. Ground reflections in relevant passages understood in context, and distinguish reflection from the passage's historical meaning. A reflection need not begin with a long historical explanation. Keep specific translation, grammar, or textual questions focused on what was asked; do not automatically append personal advice. The user does not need to choose a mode for this behavior.

Do not claim to speak as God, to recover a lost original with certainty, or to possess spiritual authority because of training. Support personal agency and allow users to disagree. When a question materially involves health, personal safety, or other specialized stakes, a biblical reflection should not be presented as a substitute for appropriate real-world help. The product should be evaluated on these cases as well as ordinary study questions.

## Evidence scope

The full Hebrew/Aramaic biblical corpus and Greek New Testament are the initial base-text scope. Preserve a precise book and edition inventory. Determine the role of Septuagint, deuterocanonical books, other early Jewish and Christian writings, and additional manuscript traditions explicitly before finalizing the training manifest. Distinguish core scripture collections, alternative witnesses/versions, and historical comparanda.

An available Masoretic base text is not an established reconstruction of every earliest Hebrew reading. A modern Greek edition is not itself an ancient manuscript. Record unresolved coverage and licensing gaps rather than silently substituting material or claiming completeness.

## What should be open

Publish code, source manifests and preparation recipes, training settings, prompts, evaluation methods and aggregate results, model cards, reproducibility instructions, limitations, and meaningful decision records. Publish adapters and reusable prepared data when the selected base and source licenses permit it. Record unavailable or nonredistributable materials clearly so others can understand the limits of reproduction.

Successful, unsuccessful, and abandoned experiments should leave concise methodological records. Publish reasoning about project choices, not personal conversation transcripts or raw user data.

## Before the first training run

Finalize the corpus inventory and rights manifest, establish a baseline on both source interpretation and broad English questions, choose a base with a credible adapter-serving path, count tokens, and set a run budget. These are finite preparation tasks; further general research is not a prerequisite to beginning them.
