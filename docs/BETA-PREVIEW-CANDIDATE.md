# Invite-only beta browser preview candidate

September 9, 2026. `bibleprep.beta_preview` adds a small browser interface to the accepted invite-only backend candidate. It has not been deployed, exposed outside loopback, or used to invite anyone. The wrapper keeps the retained Inkling B adapter, existing OSHB/SBLGNT passage lookup, hash-only invitations, secure sessions, SQLite accounting, request limits, and one-generation-at-a-time rule from `bibleprep.beta_server`. It does not switch the model or add another API.

The preview defaults to `127.0.0.1:8877`, separate from the JSON-only beta candidate on 8876 and the older private preview on 8765. The wrapper serves only `/`, `/index.html`, `/beta/app.js`, and `/beta/styles.css`, then delegates `/health` and the existing `/api/*` endpoints to the accepted backend handler. Static files are loaded from a fixed non-symlink allowlist at startup, limited to 512,000 bytes each, and returned with a same-origin content security policy, no-store caching, frame denial, MIME sniffing protection, and no-referrer policy. Other static paths return a fixed text-only 404.

## Browser flow and privacy

The sign-in form accepts an invite ID and secret and posts them to the existing `/api/login` endpoint. The backend sets the session cookie as `HttpOnly; SameSite=Strict`; JavaScript never reads it. Hosted mode adds `Secure`. The page stores no data in `localStorage`, `sessionStorage`, cookies, IndexedDB, or a service worker. Conversation turns, the current request ID, and source cards exist only in page memory. Signing out, starting a new chat, or losing the authenticated session clears that page state. Reloading the page also clears it.

After sign-in, the browser posts the current in-memory turns to `/api/chat` and polls the returned request ID through `/api/chat/{request_id}`. The interface disables another submission while it polls. The backend remains the authority for the process-wide generation lock, durable request and cost reservations, rate limits, request size, message validation, result expiry, and safe errors. A result that has expired from backend memory is shown as unavailable and is not retried.

Each asynchronous browser flow is bound to the page-state generation that started it. Starting a new chat or signing out invalidates that generation immediately, before any network wait. A late chat acceptance, poll result, error, or sign-in response is ignored after invalidation and cannot restore cleared turns or source cards.

The page renders questions, answers, notes, and original-language excerpts with `textContent`; it does not interpret answer text as HTML or Markdown. Source links appear only when the backend supplied an HTTPS `github.com` URL without embedded credentials. Source cards identify the edition, language, numbering, original text, and attribution returned by the existing passage library. They show input evidence supplied to the model, not independent verification of every answer claim.

The interface states that questions are sent to Thinking Machines / Tinker for generation, conversation text is not written to disk by this backend, and no conversation is used for training. The authenticated status view identifies the retained B model, processing provider, available source-record count, storage behavior, and any conservatively reserved uncertain requests. Provider credentials, checkpoint locators, invite hashes, internal errors, and cost-ledger details are not rendered.

## Running the candidate locally

Use the same private hash-only invitation configuration, persistent SQLite location, retained-B receipt, tokenizer assets, source data, source notices, and Python dependencies listed in `docs/BETA-BACKEND-CANDIDATE.md`. Add the three public browser assets under `web/beta/` and run:

```text
.venv/bin/python -m bibleprep.beta_preview \
  --invite-config <private-hash-only-config.json> \
  --database <persistent-private-beta.sqlite3>
```

The default URL is `http://127.0.0.1:8877/`. This wrapper should be run instead of the JSON-only candidate when the browser interface is wanted; both must not be started against the same ledger as separate processes. The one-process, one-replica constraint remains unchanged.

An external bind requires an explicit HTTPS origin. The Python process does not terminate TLS. Hosted use still assumes one directly connected TLS proxy that preserves the configured `Host` and browser `Origin`, forwards only to the private application port, applies connection limits, and avoids request or query logging. The backend rejects cross-origin POSTs and sets a secure host-only session cookie in hosted mode. Proxy, TLS, container, cloud filesystem, multi-process, rolling-deployment, and hosted-network behavior remain unverified.

## Offline verification

Run:

```text
.venv/bin/python -m unittest tests.test_beta_preview
```

The focused tests use a fake model and local HTTP server. They cover the static allowlist and security headers, unauthorized API behavior without model initialization, invite login and the authenticated status response, exact chat submission and polling through the existing backend, returned source data, logout and cookie clearing, loopback versus hosted origin rules, unsafe asset rejection, browser-persistence exclusions, and JavaScript syntax. A Node fake-DOM test also holds fetches open to prove that late chat acceptance and poll responses cannot change a cleared or signed-out page. Its completed-response case checks mapped requested references, editorial status and notes, source notes, `hbo` and `arc` right-to-left handling, and `grc` Greek labeling.

This candidate makes no provider call and does not establish model quality, security certification, checkpoint portability, hosted readiness, deployment readiness, or public-release approval. No invitation has been created or delivered by this work.
