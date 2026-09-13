# Railway deployment package for the invite-only beta

September 12 concurrency follow-up: see [concurrent beta serving](CONCURRENT-BETA.md). The service remains one process and one replica, with a bounded internal model-worker pool. Production is configured with `MEFORASH_MODEL_WORKERS=3`, `MEFORASH_QUEUE_LIMIT=12`, and `MEFORASH_QUEUE_TIMEOUT_SECONDS=120`; omitted settings retain one worker. Do not add Railway replicas to obtain concurrency. The historical single-flight checks below describe the earlier release.

September 10, 2026. This package makes the retained Inkling B browser beta concrete for a single Railway service and persistent volume. It has not been deployed and no invitation or provider request was sent. Candidate G is not used.

## Security boundary

The Docker image contains application code, the three fixed browser assets, and public manifests. It excludes `.env`, all run directories, all processed source data, all local tokenizer files, private invitation configuration, the SQLite ledger, evaluation material, reports, and development records.

The private volume supplies an allowlisted runtime bundle. `bibleprep.railway_deployment` accepts exactly the four retained-B receipt files, five Inkling tokenizer files, two processed verse files, six required manifests, and the OSHB/SBLGNT distribution notices. Export rejects a symlink anywhere in a source path and refuses to overwrite an existing destination. Startup rejects missing, extra, linked, noncanonical, or hash-changed bundle files. It then repeats the existing B receipt verification, source-integrity checks, tokenizer hash checks, renderer identity checks, and exact installed runtime-version checks before opening the listening socket.

The bundle manifest contains relative paths, sizes, categories, and SHA-256 values. It does not copy a credential or invitation secret. The B `checkpoints.json` receipt contains a private provider locator, so the entire bundle and its manifest remain private even though the manifest does not expose file contents.

## Create and check the private bundle locally

Choose an output path outside the repository and outside any public sync location:

```text
.venv/bin/python -m bibleprep.railway_deployment export \
  --output /private/path/meforash-beta-assets-v1

.venv/bin/python -m bibleprep.railway_deployment verify \
  --bundle /private/path/meforash-beta-assets-v1
```

The export command reads the existing frozen files and makes no network or provider call. Its success line prints only a file count. The verify command prints the bundle identity, not individual receipt contents.

Create the hash-only invite configuration separately with the existing `make_invite_record` workflow. Put it at `private/invites.json` on the volume. Never put a plain invite secret in that JSON. The ledger will be created at `state/beta.sqlite3`.

## Railway service settings

Use one service, one process, one replica, and one region. Attach one persistent volume at `/runtime`; Railway documents that volumes are mounted only when the service starts. Railway currently requires an active deployment before its volume file command will upload. For the initial deployment only, set `MEFORASH_SETUP_ONLY=1`. This mode reads no volume file or credential, initializes no model or source library, serves `{"status":"setup","model_ready":false}` at `/health`, and returns 503 for every visitor and API path.

After that inert deployment is healthy, upload and inspect the private files with the project, service, and environment selected:

```text
railway volume files --volume <volume-name> upload \
  /private/path/meforash-beta-assets-v1 /meforash-beta-assets-v1
railway volume files --volume <volume-name> upload \
  /private/path/invites.json /private/invites.json
railway volume files --volume <volume-name> list /meforash-beta-assets-v1
```

Do not use `--overwrite` for the first upload. If the target already exists, inspect it and prepare a separately named bundle rather than replacing a running beta's assets in place.

Then add the production variables below, remove `MEFORASH_SETUP_ONLY`, and redeploy. Leaving setup mode set keeps the model disabled even if the bundle and credentials are present.

Set these service variables in Railway's secret/settings UI:

```text
TINKER_API_KEY=<server-side secret>
BIBLE_BETA_ORIGIN=https://<the exact Railway beta domain>
RAILWAY_RUN_UID=0
```

Railway supplies `PORT` and `RAILWAY_VOLUME_MOUNT_PATH`. The service refuses a missing or non-HTTPS origin, a port outside 1024–65535, a missing Tinker variable, or private paths outside the mounted volume. `RAILWAY_RUN_UID=0` is currently required because Railway mounts volumes as root. Keep the image otherwise minimal and do not expose SSH or another application port.

Optional path overrides are `MEFORASH_RUNTIME_BUNDLE`, `BIBLE_BETA_INVITE_CONFIG`, and `BIBLE_BETA_DATABASE`; each must be an absolute nonsymlink path inside the mounted volume. Do not set them unless the uploaded layout differs.

The health check is `/health`. It proves the bundle, sources, receipt, runtime, invite configuration, and ledger initialized before routing begins. It does not call Tinker or verify account access. The first authenticated generation verifies the credential through normal provider use.

The inference transport starts a fresh child process. Startup creates one narrow symlink in the ephemeral image at `/app/data/raw/tokenizers` pointing to the already verified tokenizer directory on the volume, so the child resolves the same bytes at the existing native-profile path. Startup refuses to replace anything already present at that mount point. No symlink is accepted inside the private bundle.

Before enabling a public Railway domain, confirm the deployment settings still show one replica and one region, the volume is attached, and overlap is zero. The backend has a process-local generation lock and is not approved for multiple replicas. A volume deployment has a brief restart gap; this is appropriate for the small beta.

Railway's current documentation says legacy `railway.toml` config remains supported only for existing services and new services use Infrastructure as Code or dashboard settings. The included `railway.toml` is therefore an exact reviewable mirror, not proof that a newly created service will apply it. Reproduce its Dockerfile, start command, health check, restart, overlap, and drain settings in the dashboard if Railway ignores the file.

## Linux dependency finding

The container uses Python 3.13.1 on Debian bookworm and the existing 45-package inference lock, plus exact pins for the four CPU Torch dependencies absent from that lock, `tml-renderers==0.1.0`, and the official SHA-256-pinned `torch==2.14.0+cpu` CPython 3.13 Linux x86-64 wheel. PyPI currently publishes Linux x86-64 wheels for tokenizers and the compiled transitive packages, and an ABI3 Linux x86-64 wheel for `tml-renderers`. An offline resolver check found binary Linux candidates for every package in the existing inference lock.

The general PyPI Linux Torch wheel is about 555 MB and declares CUDA 13 dependencies. This deployment deliberately uses the official CPU wheel instead. The serving-only native profile accepts that one Linux local-version build while preserving the recorded `2.14.0` release identity; tokenizer vocabulary and rendering parity remain independently checked.

The local Docker client had no running daemon, so the image itself has not been built. Treat Linux wheel discovery and resolver output as feasibility evidence, then require a successful Railway or Linux Docker build with `pip check`, followed by the offline bundle preflight, before exposing a domain.

## Verification before invitations

Run the focused local checks:

```text
.venv/bin/python -m unittest tests.test_railway_deployment \
  tests.test_beta_server tests.test_beta_preview tests.test_chat_model \
  tests.test_chat_sources
```

After the image builds and the volume is populated, inspect startup logs for the single generic listening message and a successful Railway health check. Logs must not contain the Tinker key, invite digests, checkpoint locator, prompts, answers, or raw provider exceptions. Test login, one short authenticated question, polling, logout, restart accounting, and result loss across restart before issuing any invitation.

No publication, domain enablement, deployment, credential entry, invitation delivery, provider call, or multi-replica operation is performed by this package.

## Railway references checked

- Railway volumes and runtime mount behavior: <https://docs.railway.com/volumes>
- Railway volume file upload: <https://docs.railway.com/cli/volume>
- Dockerfile detection: <https://docs.railway.com/builds/dockerfiles>
- Health checks and the injected `PORT`: <https://docs.railway.com/deployments/healthchecks>
- Start-command behavior: <https://docs.railway.com/deployments/start-command>
- Config-as-code status and fields: <https://docs.railway.com/config-as-code/reference>
