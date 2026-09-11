# Invite-only beta backend candidate

September 9, 2026. `bibleprep.beta_server` is an offline-reviewed backend candidate for a small invite-only beta. It has not been deployed, exposed outside loopback, or used to invite anyone. It keeps the current retained Inkling B model and the existing explicit OSHB/SBLGNT passage lookup. Candidate G remains a separate experiment and is not selected here.

The service defaults to `127.0.0.1:8876`, a versioned candidate port separate from the existing preview on 8765. It exposes JSON endpoints for health, invitation login, status, answer submission, polling, and logout. There is no new browser interface in this candidate.

## Authentication and request boundary

An operator supplies a JSON configuration containing only invite IDs, random salts, scrypt digests, enabled state, and per-user/global nano-dollar caps. Plain invite secrets are never written by the backend. `make_invite_record` is an offline helper for creating a hash-only record from a high-entropy secret; the operator must deliver the original secret separately and then discard it from authoring output.

Successful login creates a random session token. Only its SHA-256 digest and expiry are stored. The browser receives a host-only `HttpOnly; SameSite=Strict` cookie. Hosted mode also sets `Secure`. Every POST requires an exact configured `Origin` and matching `Host`; an external bind is rejected unless an explicit HTTPS origin is configured. Unauthorized, wrong-origin, invalid-invite, and over-limit requests do not initialize `ChatModel` or submit provider work.

Invitation secrets should be independently generated random values of at least 24 characters. This candidate uses scrypt with a unique 16-byte salt (`N=16384`, `r=8`, `p=1`, 32-byte output). Invite configuration changes require a new ledger in this initial design; this prevents an accidental cap or identity change from reinterpreting existing accounting.

## Durable limits and privacy

SQLite stores authentication hashes, session expiry, request IDs, timestamps, state, reserved cost, and verified actual cost. It stores no prompt, answer, source excerpt, provider response, credential, or raw error. Completed answers remain briefly in process memory so the authenticated user can poll them. After 15 minutes they become unavailable and are removed on the next submission, poll, or completion; an entirely idle process does not run a periodic eraser. The process retains at most 20 completed results. A restart removes those answers while conservatively preserving unfinished cost reservations. The database and parent directory are set to modes 0600 and 0700. SQLite uses full synchronous writes and a rollback journal.

Before a generation worker starts, one maximum request reservation is committed in a transaction. The ceiling is 24,000 input tokens at $1.87 per million plus 8,192 output tokens at $4.68 per million: 83,218,560 nano-dollars. A complete receipt replaces the reservation with the rounded-up estimated actual cost. An unverified result retains the full reservation. On restart, every unfinished `reserved`, `submitted`, or `running` row becomes `uncertain`, so a restart cannot restore spent allowance.

The ledger enforces both per-invite and global caps. It also enforces a durable minimum interval of 10 seconds and at most 12 accepted requests per rolling hour for each invite. One process-wide generation is allowed at a time. A busy rejection creates no reservation. Login attempts have a small in-memory throttle; invite secrets are expected to be high entropy.

Requests are bounded to 192,000 bytes, JSON must not contain duplicate keys or non-finite values, and the existing chat payload validator limits conversation shape and message count. Provider and local exceptions are reduced to a fixed final-only error. Conversation text remains in process memory only while the request is active and is sent to Tinker to generate the answer. It is not used as training data by this backend.

## Required runtime and private files

The local implementation check used Python 3.13.1 with `tinker==0.27.1`, `tml-renderers==0.1.0`, `transformers==5.16.1`, `tokenizers==0.23.2`, and `torch==2.14.0`. The repository currently installs inference dependencies through `requirements-inference.txt` plus its pinned preparation/runtime dependencies. A hosting build must reproduce the pinned tokenizer/runtime identity checked by `ChatNativeProfile`; simply installing an unpinned SDK is insufficient.

The service needs these project assets at their expected relative paths:

- `bibleprep/chat_model.py`, `bibleprep/chat_sources.py`, and their native rendering/diagnostic dependencies;
- `runs/inkling-original-text-v1/{plan.json,summary.json,checkpoints.json,events.jsonl}` for the exact retained B receipt and private sampler reference;
- `manifests/instruction-target-revision-training-v3.json` for the B provenance binding;
- `manifests/comparison-large-models-v1.json` and its referenced pinned Inkling tokenizer assets;
- `data/processed/oshb/verses.jsonl`, `data/processed/sblgnt/verses.jsonl`, `manifests/oshb.json`, `manifests/sblgnt.json`, and `manifests/chat-versification-v1.json`;
- the OSHB and SBLGNT notices required by their source distributions;
- a server-side `TINKER_API_KEY`, supplied through the host secret manager or a private `.env`, never placed in the invite config or HTTP response;
- a persistent writable directory for the SQLite ledger. Ephemeral instance storage would defeat restart accounting.

At the time of this candidate, the local hashes include the B checkpoint receipt file `cc9ff9ed…`, comparison manifest `87de6c1b…`, processed OSHB verses `221a1687…`, processed SBLGNT verses `fac6138a…`, and versification map `cb3118eb…`. A deployment freeze must record the complete hashes rather than relying on these abbreviated references.

## TLS and proxy assumptions

The Python server does not terminate TLS. Hosted mode assumes one trusted TLS-terminating reverse proxy directly in front of the process. The proxy must preserve the configured `Host` and browser `Origin`, enforce its own request and connection limits, avoid body/query logging, forward only to the private backend port, and use persistent storage for the database. The backend deliberately ignores forwarded-origin headers. The proxy and application must share one public HTTPS origin unless a separately reviewed cross-origin design is added.

No Railway, Supabase, Vercel, container, cloud filesystem, proxy, TLS, multi-process, rolling-deployment, or hosted-network behavior has been tested. This candidate must run as exactly one process and one replica. Multiple processes would each have their own in-memory generation lock; SQLite transactions preserve caps across threads and restarts, but they do not provide a distributed generation lock. On a restart, active ledger entries become uncertain and retain their full reservations.

## Offline verification

Run:

```text
.venv/bin/python -m unittest tests.test_beta_server
```

The focused tests cover hash-only invites, private database permissions, session hashing/expiry, durable conservative restart accounting, caps and rates, lazy model initialization, single-flight behavior, safe errors, worker-start release, origin rejection, authenticated cookies, request bounds, and logout. They use a fake model and local HTTP server. They make no Tinker call and do not establish hosted readiness, model quality, checkpoint recovery, invoice accuracy, or security certification.
