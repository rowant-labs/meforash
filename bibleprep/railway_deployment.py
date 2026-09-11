"""Build and verify the private runtime bundle, or serve it on Railway.

This module never downloads assets, calls Tinker, or prints checkpoint values.
The Docker image contains application code; the retained-B receipts, tokenizer,
source data, and distribution notices stay in a separately uploaded volume.
"""
from __future__ import annotations

import argparse
import hashlib
from http.server import BaseHTTPRequestHandler
import json
import os
from pathlib import Path
import shutil
import tempfile
from urllib.parse import urlsplit

from bibleprep import beta_preview, beta_server, chat_model, chat_sources, tinker_compare


BUNDLE_SCHEMA = 1
DEFAULT_VOLUME = "/runtime"
DEFAULT_BUNDLE_DIRECTORY = "meforash-beta-assets-v1"
DEFAULT_INVITE_CONFIG = "private/invites.json"
DEFAULT_DATABASE = "state/beta.sqlite3"
MANIFEST_NAME = "runtime-bundle-manifest.json"

# This is the complete private volume asset allowlist. Application code and the
# reviewed public manifests are built into the image as well; startup requires the
# public manifest copies to be byte-identical to these reviewed bundle copies.
BUNDLE_FILES = (
    ("model_receipt", "runs/inkling-original-text-v1/plan.json"),
    ("model_receipt", "runs/inkling-original-text-v1/summary.json"),
    ("private_model_receipt", "runs/inkling-original-text-v1/checkpoints.json"),
    ("model_receipt", "runs/inkling-original-text-v1/events.jsonl"),
    ("model_manifest", "manifests/instruction-target-revision-training-v3.json"),
    ("model_manifest", "manifests/preparation-inkling-v1.json"),
    ("runtime_manifest", "manifests/comparison-large-models-v1.json"),
    ("source_manifest", "manifests/oshb.json"),
    ("source_manifest", "manifests/sblgnt.json"),
    ("source_manifest", "manifests/chat-versification-v1.json"),
    ("tokenizer", "data/raw/tokenizers/inkling/tokenizer.json"),
    ("tokenizer", "data/raw/tokenizers/inkling/tokenizer_config.json"),
    ("tokenizer", "data/raw/tokenizers/inkling/chat_template.jinja"),
    ("tokenizer", "data/raw/tokenizers/inkling/special_tokens_map.json"),
    ("tokenizer", "data/raw/tokenizers/inkling/tiktoken/tokenizer.model"),
    ("source_data", "data/processed/oshb/verses.jsonl"),
    ("source_data", "data/processed/sblgnt/verses.jsonl"),
    ("source_notice", "licenses/oshb/LICENSE.md"),
    ("source_notice", "licenses/oshb/UPSTREAM-README.md"),
    ("source_notice", "licenses/oshb/XML-HEADER-NOTICES.json"),
    ("source_notice", "licenses/sblgnt/About.md"),
    ("source_notice", "licenses/sblgnt/LICENSE-CC-BY-4.0.txt"),
    ("source_notice", "licenses/sblgnt/NOTICE.md"),
    ("source_notice", "licenses/sblgnt/UPSTREAM-README.md"),
    ("source_notice", "licenses/sblgnt/UPSTREAM-TITLE.xml"),
)
PUBLIC_MANIFESTS = tuple(path for _, path in BUNDLE_FILES if path.startswith("manifests/"))


class DeploymentError(RuntimeError):
    pass


def _json_bytes(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True,
                       separators=(",", ":")) + "\n").encode("utf-8")


def _sha256_file(path):
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
            size += len(chunk)
    return digest.hexdigest(), size


def _safe_file(root, relative, *, must_exist=True):
    root = Path(root)
    relative_path = Path(relative)
    if (relative_path.is_absolute() or not relative_path.parts
            or any(part in {"", ".", ".."} for part in relative_path.parts)
            or relative_path.as_posix() != relative):
        raise DeploymentError("The runtime bundle contains an unsafe path.")
    current = root
    if root.is_symlink():
        raise DeploymentError("A runtime bundle root cannot be a symlink.")
    for part in relative_path.parts:
        current = current / part
        if current.is_symlink():
            raise DeploymentError("Runtime assets cannot use symlinks.")
    if must_exist and (not current.is_file() or current.stat().st_size <= 0):
        raise DeploymentError("A required runtime asset is unavailable.")
    return current


def _asset_preflight(root, *, verify_runtime=True):
    """Validate B, tokenizer/runtime identity, and source hashes without a provider call."""
    root = Path(root).resolve()
    chat_model.resolve_b_checkpoint(root)
    chat_sources.PassageLibrary(root)
    if verify_runtime:
        original = tinker_compare.TOKENIZER_ROOT
        try:
            tinker_compare.TOKENIZER_ROOT = root / "data/raw/tokenizers"
            chat_model.ChatNativeProfile()
        finally:
            tinker_compare.TOKENIZER_ROOT = original


def export_bundle(source_root, output, *, verify_runtime=True):
    """Copy only allowlisted runtime assets to a new, hash-manifested directory."""
    source_root = Path(source_root)
    output = Path(output)
    if source_root.is_symlink() or not source_root.is_dir():
        raise DeploymentError("The source project root is unavailable or unsafe.")
    if output.is_symlink() or output.exists():
        raise DeploymentError("Choose a new output path for the private runtime bundle.")
    for _, relative in BUNDLE_FILES:
        _safe_file(source_root, relative)
    _asset_preflight(source_root, verify_runtime=verify_runtime)

    output_parent = output.parent.resolve()
    output_parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=".meforash-bundle-", dir=output_parent))
    try:
        records = []
        for category, relative in BUNDLE_FILES:
            source = _safe_file(source_root, relative)
            target = temporary / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            current = target.parent
            while current != temporary:
                current.chmod(0o700)
                current = current.parent
            shutil.copyfile(source, target, follow_symlinks=False)
            target.chmod(0o600)
            digest, size = _sha256_file(target)
            records.append({"path": relative, "category": category,
                            "bytes": size, "sha256": digest})
        identity = hashlib.sha256(_json_bytes(records)).hexdigest()
        manifest = {
            "schema_version": BUNDLE_SCHEMA,
            "kind": "meforash_retained_b_runtime_assets",
            "bundle_identity_sha256": identity,
            "files": records,
        }
        (temporary / MANIFEST_NAME).write_bytes(_json_bytes(manifest))
        (temporary / MANIFEST_NAME).chmod(0o600)
        output.parent.mkdir(parents=True, exist_ok=True)
        temporary.rename(output)
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    return manifest


def verify_bundle(bundle):
    """Fail closed on missing, extra, linked, noncanonical, or changed assets."""
    bundle = Path(bundle)
    manifest_path = _safe_file(bundle, MANIFEST_NAME)
    try:
        raw = manifest_path.read_bytes()
        manifest = json.loads(raw)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise DeploymentError("The runtime bundle manifest is unreadable.") from exc
    if raw != _json_bytes(manifest):
        raise DeploymentError("The runtime bundle manifest is not canonical.")
    expected_paths = [path for _, path in BUNDLE_FILES]
    records = manifest.get("files")
    if (manifest.get("schema_version") != BUNDLE_SCHEMA
            or manifest.get("kind") != "meforash_retained_b_runtime_assets"
            or not isinstance(records, list)
            or [item.get("path") for item in records if isinstance(item, dict)] != expected_paths
            or len(records) != len(expected_paths)):
        raise DeploymentError("The runtime bundle manifest does not match the allowlist.")
    actual_files = set()
    for path in bundle.rglob("*"):
        if path.is_symlink():
            raise DeploymentError("Runtime assets cannot use symlinks.")
        if path.is_file():
            actual_files.add(path.relative_to(bundle).as_posix())
    if actual_files != set(expected_paths) | {MANIFEST_NAME}:
        raise DeploymentError("The runtime bundle has missing or unapproved files.")
    for (category, relative), record in zip(BUNDLE_FILES, records):
        if set(record) != {"path", "category", "bytes", "sha256"}:
            raise DeploymentError("A runtime bundle file record is malformed.")
        path = _safe_file(bundle, relative)
        digest, size = _sha256_file(path)
        if (record != {"path": relative, "category": category,
                       "bytes": size, "sha256": digest}):
            raise DeploymentError("A runtime asset failed its integrity check.")
    identity = hashlib.sha256(_json_bytes(records)).hexdigest()
    if manifest.get("bundle_identity_sha256") != identity:
        raise DeploymentError("The runtime bundle identity is invalid.")
    return manifest


def _inside_volume(value, volume, *, existing_file=False):
    path = Path(value)
    if not path.is_absolute() or path.is_symlink():
        raise DeploymentError("Private runtime paths must be absolute non-symlink volume paths.")
    try:
        path.resolve(strict=False).relative_to(volume.resolve(strict=True))
    except (OSError, ValueError) as exc:
        raise DeploymentError("Private runtime paths must stay inside the mounted volume.") from exc
    if existing_file and (not path.is_file() or path.is_symlink()):
        raise DeploymentError("A required private runtime file is unavailable or unsafe.")
    return path


def deployment_settings(environ=None):
    environ = dict(os.environ if environ is None else environ)
    volume = Path(environ.get("RAILWAY_VOLUME_MOUNT_PATH", DEFAULT_VOLUME))
    if not volume.is_absolute() or volume.is_symlink() or not volume.is_dir():
        raise DeploymentError("The Railway volume mount is unavailable or unsafe.")
    bundle = _inside_volume(
        environ.get("MEFORASH_RUNTIME_BUNDLE", str(volume / DEFAULT_BUNDLE_DIRECTORY)), volume)
    invite = _inside_volume(
        environ.get("BIBLE_BETA_INVITE_CONFIG", str(volume / DEFAULT_INVITE_CONFIG)),
        volume, existing_file=True)
    database = _inside_volume(
        environ.get("BIBLE_BETA_DATABASE", str(volume / DEFAULT_DATABASE)), volume)
    if database.exists() and (database.is_symlink() or not database.is_file()):
        raise DeploymentError("The persistent beta ledger path is unsafe.")
    try:
        port = int(environ["PORT"])
    except (KeyError, TypeError, ValueError) as exc:
        raise DeploymentError("Railway must supply a valid PORT.") from exc
    if not 1024 <= port <= 65535:
        raise DeploymentError("Railway must supply a valid PORT.")
    origin = environ.get("BIBLE_BETA_ORIGIN", "")
    parsed = urlsplit(origin)
    if (parsed.scheme != "https" or not parsed.hostname or parsed.username
            or parsed.password or parsed.path not in {"", "/"}
            or parsed.query or parsed.fragment):
        raise DeploymentError("BIBLE_BETA_ORIGIN must be one public HTTPS origin.")
    if not environ.get("TINKER_API_KEY", "").strip():
        raise DeploymentError("The Tinker credential is absent from the runtime environment.")
    streaming_value = environ.get("MEFORASH_STREAMING", "0")
    if streaming_value not in {"0", "1"}:
        raise DeploymentError("MEFORASH_STREAMING must be exactly 0 or 1.")
    return {"volume": volume, "bundle": bundle, "invite": invite,
            "database": database, "port": port, "origin": origin.rstrip("/"),
            "streaming": streaming_value == "1"}


def _port(environ):
    try:
        port = int(environ["PORT"])
    except (KeyError, TypeError, ValueError) as exc:
        raise DeploymentError("Railway must supply a valid PORT.") from exc
    if not 1024 <= port <= 65535:
        raise DeploymentError("Railway must supply a valid PORT.")
    return port


def setup_handler():
    """An inert first-deploy handler used only to unlock Railway volume upload."""
    class SetupHandler(BaseHTTPRequestHandler):
        server_version = "MeforashVolumeSetupV1"

        def log_message(self, format, *args):
            pass

        def _send(self, status, content_type, body):
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("X-Frame-Options", "DENY")
            self.end_headers()
            try:
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError):
                pass

        def do_GET(self):
            if self.path == "/health":
                return self._send(200, "application/json; charset=utf-8",
                                  b'{"status":"setup","model_ready":false}\n')
            return self._send(503, "text/plain; charset=utf-8",
                              b"Meforash beta setup is not ready for visitors.\n")

        def do_POST(self):
            return self._send(503, "text/plain; charset=utf-8",
                              b"Meforash beta setup is not ready for visitors.\n")

        do_PUT = do_POST
        do_PATCH = do_POST
        do_DELETE = do_POST
        do_OPTIONS = do_POST

    return SetupHandler


def serve_setup(environ):
    port = _port(environ)
    server = beta_server.BetaHTTPServer(("0.0.0.0", port), setup_handler())
    print("Meforash volume setup mode is active; model service is disabled.", flush=True)
    try:
        server.serve_forever(poll_interval=0.25)
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


def offline_preflight(bundle, *, image_root=None, verify_runtime=True):
    """Verify a mounted bundle and image/public-manifest agreement."""
    bundle = Path(bundle).resolve()
    manifest = verify_bundle(bundle)
    image_root = Path(image_root or Path(__file__).resolve().parents[1]).resolve()
    for relative in PUBLIC_MANIFESTS:
        image_file = _safe_file(image_root, relative)
        bundle_file = _safe_file(bundle, relative)
        if _sha256_file(image_file) != _sha256_file(bundle_file):
            raise DeploymentError("The image and runtime bundle manifests differ.")
    _asset_preflight(bundle, verify_runtime=verify_runtime)
    return manifest


def install_tokenizer_mount(bundle, *, image_root=None):
    """Expose verified tokenizer bytes at the legacy path used by spawned workers."""
    bundle = Path(bundle).resolve()
    image_root = Path(image_root or Path(__file__).resolve().parents[1]).resolve()
    source = bundle / "data/raw/tokenizers"
    if not source.is_dir() or source.is_symlink():
        raise DeploymentError("The verified tokenizer directory is unavailable.")
    parent = image_root / "data/raw"
    target = parent / "tokenizers"
    parent.mkdir(parents=True, exist_ok=True)
    if target.is_symlink() and target.resolve() == source:
        return target
    if target.exists() or target.is_symlink():
        raise DeploymentError("The image tokenizer mount point must start empty.")
    target.symlink_to(source, target_is_directory=True)
    if target.resolve() != source:
        raise DeploymentError("The image tokenizer mount point could not be verified.")
    return target


def serve(environ=None):
    environ = dict(os.environ if environ is None else environ)
    if environ.get("MEFORASH_SETUP_ONLY") == "1":
        return serve_setup(environ)
    settings = deployment_settings(environ)
    offline_preflight(settings["bundle"])
    # Sampling uses multiprocessing spawn. The fixed image path therefore must
    # resolve in both the parent and a freshly imported child process.
    install_tokenizer_mount(settings["bundle"])
    invite_config = beta_server.load_invite_config(settings["invite"])
    store = beta_server.BetaStore(settings["database"], invite_config)
    access = beta_server.AccountAccess.from_environ(store.path, environ)
    app = beta_server.BetaApplication(
        store=store, root=settings["bundle"], access=access,
        streaming=settings["streaming"])
    handler = beta_preview.handler_for(
        app, origin=settings["origin"], secure_cookie=True,
        asset_root=beta_preview.ASSET_ROOT,
        trust_real_ip=environ.get("MEFORASH_TRUST_RAILWAY_REAL_IP") == "1")
    server = beta_server.BetaHTTPServer(("0.0.0.0", settings["port"]), handler)
    print("Meforash beta is listening behind its HTTPS proxy.", flush=True)
    try:
        server.serve_forever(poll_interval=0.25)
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        app.close()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    export = subparsers.add_parser("export", help="create the private allowlisted bundle")
    export.add_argument("--source-root", default=str(Path(__file__).resolve().parents[1]))
    export.add_argument("--output", required=True)
    verify = subparsers.add_parser("verify", help="verify an existing bundle offline")
    verify.add_argument("--bundle", required=True)
    subparsers.add_parser("serve", help="verify the Railway volume and start the beta")
    args = parser.parse_args(argv)
    try:
        if args.command == "export":
            manifest = export_bundle(args.source_root, args.output)
            print(f"Created verified private runtime bundle with {len(manifest['files'])} files.")
        elif args.command == "verify":
            manifest = offline_preflight(args.bundle)
            print(f"Verified retained-B runtime bundle {manifest['bundle_identity_sha256']}.")
        else:
            serve()
    except (DeploymentError, chat_model.ChatModelError, chat_sources.SourceLookupError,
            beta_server.BetaError, OSError, ValueError):
        parser.exit(1, "Meforash deployment preflight failed; no service was started.\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
