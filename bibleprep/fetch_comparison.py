"""Fetch pinned public comparison tokenizers, without weights or credentials."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
import urllib.error
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
ASSET_NAMES = frozenset({
    "tokenizer.json", "tokenizer_config.json", "chat_template.jinja",
    "special_tokens_map.json", "tiktoken/tokenizer.model",
    "tiktoken.model", "tokenization_kimi.py", "tool_declaration_ts.py",
})
MAX_ASSET_BYTES = 64 * 1024 * 1024
MAX_MANIFEST_BYTES = 256 * 1024


def _public_hf_url(url: str) -> bool:
    parsed = urllib.parse.urlsplit(url)
    host = parsed.hostname or ""
    return (parsed.scheme == "https" and parsed.username is None
            and parsed.password is None and parsed.port is None
            and not parsed.fragment
            and (host == "huggingface.co" or host.endswith(".huggingface.co")
                 or host == "hf.co" or host.endswith(".hf.co")))


class PublicAssetRedirect(urllib.request.HTTPRedirectHandler):
    """Permit Hugging Face's public storage redirects, never arbitrary hosts."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not _public_hf_url(newurl):
            raise ValueError("Tokenizer asset redirected outside public Hugging Face storage")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _validated_models(manifest: dict) -> list[dict]:
    if not isinstance(manifest, dict) or manifest.get("schema_version") != 1:
        raise ValueError("Unsupported comparison manifest schema")
    models = manifest.get("models")
    if not isinstance(models, list) or not 1 <= len(models) <= 32:
        raise ValueError("Comparison manifest must contain 1 to 32 models")
    ids, slugs = set(), set()
    for model in models:
        if not isinstance(model, dict):
            raise ValueError("Comparison model entry must be an object")
        model_id, slug = model.get("id"), model.get("slug")
        repository, revision = model.get("tokenizer_repository"), model.get("revision")
        if not isinstance(model_id, str) or not re.fullmatch(r"[\w.-]+/[\w.-]+", model_id, re.ASCII):
            raise ValueError("Comparison model ID must identify an owner and model")
        if not isinstance(slug, str) or not re.fullmatch(r"[a-z0-9][a-z0-9._-]{0,99}", slug):
            raise ValueError("Comparison model slug must be a safe directory name")
        if model_id in ids or slug in slugs:
            raise ValueError("Comparison model IDs and slugs must be unique")
        ids.add(model_id)
        slugs.add(slug)
        if not isinstance(repository, str) or not re.fullmatch(r"[\w.-]+/[\w.-]+", repository, re.ASCII):
            raise ValueError("Tokenizer repository must identify a Hugging Face owner and repository")
        if any(part in {".", ".."} for part in repository.split("/")):
            raise ValueError("Tokenizer repository contains an unsafe path component")
        if not isinstance(revision, str) or not re.fullmatch(r"[0-9a-f]{40}", revision):
            raise ValueError("Tokenizer revision must be an immutable 40-character commit")
        entries = model.get("files")
        if not isinstance(entries, list) or not 1 <= len(entries) <= len(ASSET_NAMES):
            raise ValueError("Comparison model must list only supported tokenizer assets")
        seen = set()
        for entry in entries:
            if not isinstance(entry, dict):
                raise ValueError("Tokenizer asset must be an object")
            name, digest, size = entry.get("path"), entry.get("sha256"), entry.get("bytes")
            if not isinstance(name, str) or name not in ASSET_NAMES or name in seen:
                raise ValueError("Tokenizer asset path is unsupported or duplicated")
            seen.add(name)
            if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
                raise ValueError("Tokenizer asset requires a SHA-256 digest")
            if type(size) is not int or not 0 < size <= MAX_ASSET_BYTES:
                raise ValueError("Tokenizer asset byte count is outside the download bound")
            expected_url = f"https://huggingface.co/{repository}/resolve/{revision}/{name}"
            if entry.get("url") != expected_url:
                raise ValueError("Tokenizer URL must exactly match its repository, commit, and filename")
    return models


def _verify(data: bytes, entry: dict) -> None:
    if len(data) != entry["bytes"]:
        raise ValueError(f"Tokenizer byte count mismatch: {entry['path']}")
    if hashlib.sha256(data).hexdigest() != entry["sha256"]:
        raise ValueError(f"Tokenizer checksum mismatch: {entry['path']}")


def _download(entry: dict) -> bytes:
    request = urllib.request.Request(entry["url"], headers={
        "User-Agent": "Bible-model-preparation/0.1",
        "Accept-Encoding": "identity",
    })
    opener = urllib.request.build_opener(PublicAssetRedirect())
    with opener.open(request, timeout=90) as response:
        if not _public_hf_url(response.geturl()):
            raise ValueError("Tokenizer response came from an unsupported origin")
        data = response.read(entry["bytes"] + 1)
    _verify(data, entry)
    return data


def _atomic_write(path: Path, data: bytes) -> None:
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix=".tokenizer-", delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def fetch_assets(manifest_path: Path, destination_root: Path,
                 selected_slugs: list[str] | None = None) -> list[dict]:
    """Verify existing assets or download missing ones from a validated manifest.

    Validation happens before writes or requests. Changed local files are preserved
    and rejected, so an unexpected checksum never silently replaces local work.
    """
    if manifest_path.stat().st_size > MAX_MANIFEST_BYTES:
        raise ValueError("Comparison manifest exceeds the size bound")
    models = _validated_models(json.loads(manifest_path.read_text(encoding="utf-8")))
    if selected_slugs:
        unknown = set(selected_slugs) - {model["slug"] for model in models}
        if unknown:
            raise ValueError("Requested model slug is absent from the comparison manifest")
        models = [model for model in models if model["slug"] in selected_slugs]
    if destination_root.is_symlink():
        raise ValueError("Tokenizer destination must not be a symbolic link")
    destination_root.mkdir(parents=True, exist_ok=True)
    results = []
    for model in models:
        directory = destination_root / model["slug"]
        if directory.is_symlink():
            raise ValueError("Tokenizer model directory must not be a symbolic link")
        directory.mkdir(exist_ok=True)
        for entry in model["files"]:
            path = directory / entry["path"]
            parent = directory
            for part in Path(entry["path"]).parts[:-1]:
                parent = parent / part
                if parent.is_symlink():
                    raise ValueError("Tokenizer asset directory must not be a symbolic link")
                parent.mkdir(exist_ok=True)
            if path.is_symlink():
                raise ValueError("Tokenizer asset must not be a symbolic link")
            if path.exists():
                with path.open("rb") as handle:
                    _verify(handle.read(entry["bytes"] + 1), entry)
                status = "verified"
            else:
                data = _download(entry)
                _verify(data, entry)
                _atomic_write(path, data)
                status = "downloaded"
            results.append({"model": model["slug"], "path": entry["path"],
                            "status": status, "bytes": entry["bytes"]})
    return results


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path,
                        default=ROOT / "manifests/comparison-models.json",
                        help="Pinned comparison manifest (default: original model comparison)")
    parser.add_argument("--model", action="append", dest="models", metavar="SLUG",
                        help="Fetch one manifest model; repeat to select several (default: all)")
    args = parser.parse_args(argv)
    try:
        results = fetch_assets(args.manifest,
                               ROOT / "data/raw/tokenizers", args.models)
    except (OSError, ValueError, urllib.error.URLError):
        print("Comparison assets failed validation or download; no credentials or model calls were used.")
        return 1
    for result in results:
        print(f"{result['model']}/{result['path']}: {result['status']}")
    print("Comparison tokenizer checksums verified; no weights downloaded or model calls made.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
