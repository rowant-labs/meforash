# Open-source release candidate

September 10, 2026. The project has a shareable code/documentation scaffold and preserved decision history. It has **not** been pushed to a remote repository. The local Git repository has no commits, branches, tags, tracked files or configured remotes; there is no existing commit history to sanitize. New commits still need privacy-preserving author metadata and a review of the exact staged files.

## What a source release includes

Release authored code, tests, documentation, source manifests, license notices and aggregate experimental results under the project's Apache-2.0 license. Preserve the unsuccessful and inconclusive experiments as part of the decision record. The source editions, third-party assets and base model have their own licenses; the project's code license does not relicense them.

Keep actual environment files, credentials, checkpoint locators, private run/review records, personal planning notes, source downloads and prepared datasets out of the initial source release. Include the safe `.env.example`. Candidate G target data and model weights require their own artifact-release review; training-use review does not establish redistribution approval.

## Reproduction boundary

An isolated export of the prior 267 publication-candidate files exercised 484 tests under full discovery, with no assertion failures, fourteen test/setup errors and one optional-source skip. The errors were caused by missing source texts, pinned tokenizer assets or private historical prepared rows. Consequently a clean code export is not a complete reproduction of the private training/evaluation environment.

The new source-only command is:

```sh
python -m bibleprep.test_source_release
```

In the latest pre-run isolated export of291 source files, this command passed **540 tests**, with **94 asset-dependent tests explicitly excluded**. The earlier exports remain preserved. Two preliminary local attempts are also preserved: one corrected private runtime-directory permissions, and one encountered a transient local HTTP connection reset before the successful run. It reports both counts. Excluded tests are not counted as passes. Full discovery remains available after the required source/tokenizer preparation and permitted experiment artifacts are present:

```sh
python -m unittest <explicit tests.test_* module list>
```

Use the pinned dependency files and the existing preparation instructions. No credentials are necessary for ordinary source-only checks. Training and inference require separately configured provider access and model checkpoints. The saved provider base revision is unpinned, and exact external adapter conversion/restoration has not been demonstrated; do not claim a fully reproducible public model release.

## Before the first push

Create the final file allowlist and review its hashes, secret/personal-information scan results, local links, license notices and model/source cards. Review the exact Git index rather than adding the entire working directory. Confirm the chosen repository name and privacy-preserving commit identity before creating commits; inspect the first commit and then publish only the reviewed material. No invitation messages, release uploads or repository visibility changes have occurred.

The [publication policy](PUBLICATION.md) gives the continuing privacy and artifact rules. The [beta readiness record](PRIVATE-BETA-READINESS.md) separates a code release from a hosted application launch.
