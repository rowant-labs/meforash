# Open-source release candidate

Current status, September 12, 2026: the reviewed source repository is public at [rowant-labs/meforash](https://github.com/rowant-labs/meforash), and the local branch is synchronized with its `main` branch. GitHub secret scanning and push protection are enabled. Private runtime assets, source downloads, prepared data, local ledgers and model weights remain excluded.

The original September 10 release-candidate snapshot below is retained as a historical record. At that time the project had a shareable code/documentation scaffold and preserved decision history but had not been pushed, committed or connected to a remote.

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

## Historical pre-push checklist

The initial publication used a reviewed file allowlist, privacy-preserving GitHub noreply author metadata, and staged-file checks before the first push. Those checks were point-in-time release work, not a guarantee about later commits.

## Current publication posture

The public `main` history contains the reviewed source, tests, documentation, manifests, source notices and aggregate evaluation records. There are no GitHub Releases and no model-weight artifact in the repository. The ignored `.env`, private run records, raw and processed source texts, prepared datasets, SQLite ledgers, and checkpoint locators are not tracked in the current tree.

A September 12 current-tree scan found no actual credential assignment, private checkpoint locator, personal filesystem path, production database or conversation log in tracked files. The source-only suite passed 601 selected tests and explicitly excluded 94 tests that require private or acquired assets. GitHub secret scanning and push protection were enabled and reported no open alert at the time of review.

These are bounded checks. The local pattern review of all 29 commits classified its matches as synthetic canaries, validators, blank configuration fields or documented placeholders, but it was not a comprehensive personal-information audit or an independent security assessment. GitHub's default secret scanning covers recognized secret types across history; it does not prove that ordinary personal data, an unsupported credential format, generated artifact, issue, wiki page or future commit is safe. Continue reviewing the exact diff and public repository state for every publication.

The [publication policy](PUBLICATION.md) gives the continuing privacy and artifact rules. The [beta readiness record](PRIVATE-BETA-READINESS.md) separates a code release from a hosted application launch.
