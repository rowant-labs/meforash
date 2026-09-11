"""Fetch pinned public sources and tokenizer assets. No model weights or API keys."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import urllib.request

ROOT = Path(__file__).resolve().parents[1]


def git(directory: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(directory), *args], check=True,
                          text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE).stdout.strip()


def checkout(directory: Path, repository: str, revision: str):
    if directory.exists():
        if not (directory / ".git").is_dir():
            raise ValueError(f"Existing source directory is not a Git checkout: {directory.name}")
        if git(directory, "rev-parse", "HEAD") != revision:
            raise ValueError(f"Existing checkout differs from pin: {directory.name}; preserve it and use a fresh directory")
        if git(directory, "status", "--porcelain", "--untracked-files=no"):
            raise ValueError(f"Tracked source files were changed: {directory.name}")
        return
    directory.mkdir(parents=True)
    git(directory, "init", "--quiet")
    git(directory, "remote", "add", "origin", repository)
    git(directory, "fetch", "--quiet", "--depth", "1", "origin", revision)
    git(directory, "checkout", "--quiet", "--detach", "FETCH_HEAD")
    if git(directory, "rev-parse", "HEAD") != revision:
        raise ValueError("Fetched revision does not match pin")


def main():
    for source in ("oshb", "sblgnt"):
        manifest = json.loads((ROOT / f"manifests/{source}.json").read_text())
        revision = manifest.get("revision", manifest.get("pinned_commit"))
        checkout(ROOT / f"data/raw/{source}", manifest["repository"], revision)
        print(f"{source}: pinned checkout verified")
    manifest = json.loads((ROOT / "manifests/tokenizer.json").read_text())
    folder = ROOT / "data/raw/tokenizers/gpt-oss-120b"
    folder.mkdir(parents=True, exist_ok=True)
    entries = list(manifest["files"])
    template_manifest = ROOT / "manifests/chat-template.json"
    if template_manifest.is_file():
        template = json.loads(template_manifest.read_text())
        entries.append({"path": "chat_template.jinja", "url": template["url"], "sha256": template["sha256"]})
    for entry in entries:
        relative = Path(entry["path"])
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError("Tokenizer path must stay within destination")
        path = folder / relative
        if path.exists():
            data = path.read_bytes()
        else:
            request = urllib.request.Request(entry["url"], headers={"User-Agent": "Bible-model-preparation/0.1"})
            data = urllib.request.urlopen(request, timeout=90).read()
        if hashlib.sha256(data).hexdigest() != entry["sha256"]:
            raise ValueError(f"Tokenizer checksum mismatch: {entry['path']}")
        if not path.exists():
            path.write_bytes(data)
    print("tokenizer: pinned file checksums verified; no weights downloaded")


if __name__ == "__main__":
    main()
