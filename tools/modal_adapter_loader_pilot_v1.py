"""Isolated Modal resource for the project-owned GPT-OSS LoRA loader probe.

Importing this module creates no remote resources. Stage this file together with
``fixture/adapter_config.json``, ``fixture/adapter_model.safetensors`` and
``fixture/manifest.json`` in an otherwise empty directory before invoking Modal.
The fixture is constructed test data; this module performs no training and uses
no provider credential other than the operator's Modal account.
"""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

import modal


MODEL_ID = "openai/gpt-oss-20b"
MODEL_REVISION = "6cee5e81ee83917806bbde320786a8fb61efebee"
SERVED_MODEL_NAME = MODEL_ID
ADAPTER_NAME = "meforash-loader-fixture-v1"
UNKNOWN_ADAPTER_NAME = "meforash-loader-fixture-v1-unknown"
VLLM_VERSION = "0.29.0"
VLLM_IMAGE = "vllm/vllm-openai@sha256:082ca6f035279109041ffd3fe0695cb568b29bc580b35c4f297a66a08b216c1b"
EXPECTED_MODEL_MANIFEST_SHA256 = "5f8255b4762b7dc5fe67c74e79db77e3d560f7d951231e74a5870803b2a136e4"
EXPECTED_FIXTURE_FILES = {
    "adapter_config.json": {"size": 469, "sha256": "606b0b3f906d4ad1217de5725e671717e29815d5284d88a00fe734bfd25b6291"},
    "adapter_model.safetensors": {"size": 3_069_904, "sha256": "fe03f9c6880180460f57a335ea7fe80b96363a5448dfc1f19fe04cc6aa9deaf8"},
}
EXPECTED_TENSOR_COUNT = 66
EXPECTED_RANK = 8

APP_NAME = "meforash-modal-adapter-loader-v1"
VOLUME_NAME = "meforash-modal-adapter-loader-v1-weights"
VOLUME_ROOT = Path("/weights")
MODEL_DIR = VOLUME_ROOT / f"openai-gpt-oss-20b-{MODEL_REVISION}"
MODEL_MANIFEST_PATH = MODEL_DIR / "manifest.json"
ADAPTER_DIR = VOLUME_ROOT / "fixture"
ADAPTER_MANIFEST_PATH = ADAPTER_DIR / "manifest.json"
LOG_PATH = Path("/tmp/vllm-adapter-loader-v1.log")
VLLM_BASE_URL = "http://127.0.0.1:8000"
STARTUP_TIMEOUT_SECONDS = 900
FUNCTION_TIMEOUT_SECONDS = 600
REQUEST_TIMEOUT_SECONDS = 180

MODEL_FILES: dict[str, dict[str, int | str | None]] = {
    "model-00000-of-00002.safetensors": {"size": 4_792_272_488, "sha256": "16d0f997dcfc4462089d536bffe51b4bcea2f872f5c430be09ef8ed392312427"},
    "model-00001-of-00002.safetensors": {"size": 4_798_702_184, "sha256": "4fbe328ab445455d6f58dc73852b85873bd626986310abd91cd4d2ce3245eaea"},
    "model-00002-of-00002.safetensors": {"size": 4_170_342_232, "sha256": "a18106b209e9ab35c3406db4f6f12a927364a058b21e9d1373d682e20674b303"},
    "model.safetensors.index.json": {"size": 36_355, "sha256": None},
    "config.json": {"size": 1_806, "sha256": None},
    "generation_config.json": {"size": 177, "sha256": None},
    "chat_template.jinja": {"size": 16_738, "sha256": None},
    "tokenizer.json": {"size": 27_868_174, "sha256": None},
    "tokenizer_config.json": {"size": 4_200, "sha256": None},
    "special_tokens_map.json": {"size": 98, "sha256": None},
    "LICENSE": {"size": 11_357, "sha256": None},
    "README.md": {"size": 7_095, "sha256": None},
    "USAGE_POLICY": {"size": 200, "sha256": None},
}

app = modal.App(APP_NAME)
weights_volume = modal.Volume.from_name(VOLUME_NAME, create_if_missing=True)
prepare_image = modal.Image.debian_slim(python_version="3.12").add_local_dir(
    "fixture", remote_path="/root/fixture", copy=True
)
serve_image = modal.Image.from_registry(VLLM_IMAGE).entrypoint([]).run_commands(
    "ln -s $(which python3) /usr/bin/python"
).env({"HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1", "HF_DATASETS_OFFLINE": "1", "VLLM_NO_USAGE_STATS": "1"})


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(8 * 1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _verify_file(path: Path, spec: dict[str, int | str | None]) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise RuntimeError(f"missing or non-regular file: {path.name}")
    if path.stat().st_size != spec["size"]:
        raise RuntimeError(f"size mismatch: {path.name}")
    actual = _sha256(path)
    if spec["sha256"] is not None and actual != spec["sha256"]:
        raise RuntimeError(f"SHA-256 mismatch: {path.name}")
    return {"path": path.name, "size": path.stat().st_size,
            "bytes": path.stat().st_size, "sha256": actual}


def _model_url(filename: str) -> str:
    repo = "/".join(quote(part, safe="") for part in MODEL_ID.split("/"))
    return f"https://huggingface.co/{repo}/resolve/{quote(MODEL_REVISION, safe='')}/{quote(filename, safe='/')}?download=true"


def _model_manifest_bytes(files: list[dict[str, Any]]) -> bytes:
    value = {"schema_version": 1, "model_id": MODEL_ID, "revision": MODEL_REVISION,
             "source": f"https://huggingface.co/{MODEL_ID}/tree/{MODEL_REVISION}",
             "files": sorted(({"path": item["path"], "size": item["size"], "sha256": item["sha256"]}
                              for item in files), key=lambda item: item["path"])}
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()


def _verify_fixture(directory: Path) -> dict[str, Any]:
    allowed = set(EXPECTED_FIXTURE_FILES) | {"manifest.json"}
    actual = {p.name for p in directory.iterdir()}
    if actual != allowed:
        raise RuntimeError(f"fixture allowlist mismatch: {sorted(actual ^ allowed)}")
    files = [_verify_file(directory / name, spec) for name, spec in EXPECTED_FIXTURE_FILES.items()]
    manifest = json.loads((directory / "manifest.json").read_text())
    if manifest.get("files") != {item["path"]: {"bytes": item["bytes"], "sha256": item["sha256"]} for item in files}:
        raise RuntimeError("fixture manifest file map does not match verified files")
    fixture = manifest.get("fixture")
    if not isinstance(fixture, dict) or fixture.get("rank") != EXPECTED_RANK or fixture.get("output_tensor_count") != EXPECTED_TENSOR_COUNT:
        raise RuntimeError("fixture manifest rank or tensor count mismatch")
    config = json.loads((directory / "adapter_config.json").read_text())
    required_config = {"base_model_name_or_path": MODEL_ID, "revision": MODEL_REVISION, "r": EXPECTED_RANK,
                       "peft_type": "LORA", "task_type": "CAUSAL_LM", "target_modules": ["down_proj", "q_proj"]}
    for key, expected in required_config.items():
        if config.get(key) != expected:
            raise RuntimeError(f"adapter config mismatch: {key}")
    return {"manifest_sha256": _sha256(directory / "manifest.json"), "files": files,
            "tensor_count": EXPECTED_TENSOR_COUNT, "rank": EXPECTED_RANK, "layout": "2d_per_expert"}


def _verify_model_lightweight() -> dict[str, Any]:
    allowed = set(MODEL_FILES) | {"manifest.json"}
    actual = {p.name for p in MODEL_DIR.iterdir()}
    if actual != allowed:
        raise RuntimeError("model directory allowlist mismatch")
    raw = MODEL_MANIFEST_PATH.read_bytes()
    if hashlib.sha256(raw).hexdigest() != EXPECTED_MODEL_MANIFEST_SHA256:
        raise RuntimeError("model manifest hash mismatch")
    manifest = json.loads(raw)
    if manifest.get("model_id") != MODEL_ID or manifest.get("revision") != MODEL_REVISION:
        raise RuntimeError("model identity mismatch")
    for name, spec in MODEL_FILES.items():
        path = MODEL_DIR / name
        if path.is_symlink() or not path.is_file() or path.stat().st_size != spec["size"]:
            raise RuntimeError(f"model file mismatch: {name}")
    return {"manifest_sha256": EXPECTED_MODEL_MANIFEST_SHA256, "file_count": len(MODEL_FILES)}


@app.function(image=prepare_image, volumes={str(VOLUME_ROOT): weights_volume}, cpu=(2.0, 2.0),
              memory=(8192, 8192), min_containers=0, max_containers=1, retries=0,
              timeout=FUNCTION_TIMEOUT_SECONDS, startup_timeout=STARTUP_TIMEOUT_SECONDS)
def prepare_weights() -> dict[str, Any]:
    """Prepare the pinned public base and copy only the staged project fixture."""
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    if MODEL_MANIFEST_PATH.exists():
        model_files = [_verify_file(MODEL_DIR / name, spec) for name, spec in MODEL_FILES.items()]
        if hashlib.sha256(MODEL_MANIFEST_PATH.read_bytes()).hexdigest() != EXPECTED_MODEL_MANIFEST_SHA256:
            raise RuntimeError("existing model manifest hash mismatch")
        model_status = "verified_existing"
    else:
        model_files = []
        for name, spec in MODEL_FILES.items():
            target = MODEL_DIR / name
            partial = MODEL_DIR / (name + ".partial")
            partial.unlink(missing_ok=True)
            if not target.exists():
                request = Request(_model_url(name), headers={"User-Agent": "Meforash-adapter-loader-v1/1.0"})
                try:
                    with urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response, partial.open("wb") as output:
                        while chunk := response.read(8 * 1024 * 1024):
                            output.write(chunk)
                except (HTTPError, URLError, TimeoutError) as exc:
                    partial.unlink(missing_ok=True)
                    raise RuntimeError(f"download failed: {name}") from exc
                _verify_file(partial, spec)
                os.replace(partial, target)
            model_files.append(_verify_file(target, spec))
        raw = _model_manifest_bytes(model_files)
        if hashlib.sha256(raw).hexdigest() != EXPECTED_MODEL_MANIFEST_SHA256:
            raise RuntimeError("prepared model does not reproduce pinned manifest")
        MODEL_MANIFEST_PATH.write_bytes(raw)
        model_status = "prepared"

    staged = Path("/root/fixture")
    fixture = _verify_fixture(staged)
    if ADAPTER_DIR.exists():
        existing = _verify_fixture(ADAPTER_DIR)
        if existing != fixture:
            raise RuntimeError("existing fixture identity mismatch")
        fixture_status = "verified_existing"
    else:
        ADAPTER_DIR.mkdir()
        for name in sorted(set(EXPECTED_FIXTURE_FILES) | {"manifest.json"}):
            (ADAPTER_DIR / name).write_bytes((staged / name).read_bytes())
        _verify_fixture(ADAPTER_DIR)
        fixture_status = "staged"
    weights_volume.commit()
    return {"status": "prepared", "model_status": model_status, "fixture_status": fixture_status,
            "model_id": MODEL_ID, "revision": MODEL_REVISION,
            "model_manifest_sha256": EXPECTED_MODEL_MANIFEST_SHA256, "fixture": fixture}


def _request(path: str, payload: dict[str, Any] | None = None, *, allow_http_error: bool = False) -> tuple[int, dict[str, Any]]:
    body = None if payload is None else json.dumps(payload, separators=(",", ":")).encode()
    request = Request(VLLM_BASE_URL + path, data=body,
                      headers={"Accept": "application/json", "Content-Type": "application/json"},
                      method="GET" if body is None else "POST")
    try:
        with urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
            return response.status, json.loads(response.read() or b"{}")
    except HTTPError as exc:
        if not allow_http_error:
            raise RuntimeError(f"local vLLM {path} returned HTTP {exc.code}") from exc
        try:
            value = json.loads(exc.read(4096) or b"{}")
        except json.JSONDecodeError:
            value = {}
        return exc.code, value


def _final_text(response: dict[str, Any]) -> str:
    choices = response.get("choices")
    if not isinstance(choices, list) or len(choices) != 1 or not isinstance(choices[0], dict):
        raise RuntimeError("completion choices missing")
    message = choices[0].get("message")
    if not isinstance(message, dict) or not isinstance(message.get("content"), str):
        raise RuntimeError("final content missing")
    return message["content"]


def _final_receipt(response: dict[str, Any], expected_model: str) -> dict[str, Any]:
    choices = response.get("choices")
    choice = choices[0] if isinstance(choices, list) and len(choices) == 1 and isinstance(choices[0], dict) else {}
    text = _final_text(response)
    if not text or choice.get("finish_reason") != "stop" or response.get("model") != expected_model:
        raise RuntimeError(f"incomplete or identity-mismatched response for {expected_model}")
    content_logprobs = choice.get("logprobs", {}).get("content") if isinstance(choice.get("logprobs"), dict) else None
    scalar_logprobs = [item.get("logprob") for item in content_logprobs
                       if isinstance(item, dict) and isinstance(item.get("logprob"), (int, float))] if isinstance(content_logprobs, list) else []
    return {"model": expected_model, "final_content": text, "finish_reason": "stop",
            "usage": response.get("usage"),
            "final_token_logprob_count": len(scalar_logprobs),
            "final_token_logprob_sum": sum(scalar_logprobs) if scalar_logprobs else None}


@app.cls(image=serve_image, gpu="L4", volumes={str(VOLUME_ROOT): weights_volume.read_only()},
         cpu=(2.0, 2.0), memory=(32768, 32768), min_containers=0, max_containers=1,
         retries=0, timeout=FUNCTION_TIMEOUT_SECONDS, startup_timeout=STARTUP_TIMEOUT_SECONDS)
@modal.concurrent(max_inputs=1, target_inputs=1)
class Model:
    @modal.enter()
    def start(self) -> None:
        self.fixture = _verify_fixture(ADAPTER_DIR)
        _verify_model_lightweight()
        if importlib.metadata.version("vllm") != VLLM_VERSION:
            raise RuntimeError("vLLM package version mismatch")
        LOG_PATH.unlink(missing_ok=True)
        self.log_file = LOG_PATH.open("wb")
        adapter_spec = json.dumps({"name": ADAPTER_NAME, "path": str(ADAPTER_DIR),
                                   "base_model_name": MODEL_ID, "is_3d_lora_weight": False}, separators=(",", ":"))
        command = ["vllm", "serve", str(MODEL_DIR), "--tokenizer", str(MODEL_DIR),
                   "--served-model-name", SERVED_MODEL_NAME, "--host", "127.0.0.1", "--port", "8000",
                   "--max-model-len", "1024", "--max-num-seqs", "1", "--max-num-batched-tokens", "2048",
                   "--gpu-memory-utilization", "0.85", "--enforce-eager", "--generation-config", "vllm",
                   "--enable-lora", "--max-loras", "1", "--max-lora-rank", "8",
                   "--enable-mixed-moe-lora-format", "--lora-modules", adapter_spec,
                   "--moe-backend", "marlin", "--linear-backend", "marlin",
                   "--compilation-config", '{"cudagraph_specialize_lora":false}', "--no-enable-log-requests"]
        self.process = subprocess.Popen(command, stdout=self.log_file, stderr=subprocess.STDOUT)
        deadline = time.monotonic() + STARTUP_TIMEOUT_SECONDS
        while time.monotonic() < deadline:
            if self.process.poll() is not None:
                self.log_file.flush()
                print(LOG_PATH.read_text(errors="replace")[-16_384:], flush=True)
                raise RuntimeError("vLLM exited during startup")
            try:
                if _request("/health")[0] == 200:
                    return
            except Exception:
                pass
            time.sleep(1)
        raise TimeoutError("vLLM did not become ready")

    @modal.method()
    def probe(self) -> dict[str, Any]:
        """Run one fixed base/adapter probe and return a private final-only receipt."""
        prompt = "Reply with one short sentence explaining why fixed test fixtures aid reproducibility."
        common = {"messages": [{"role": "user", "content": prompt}], "temperature": 0, "seed": 0,
                  "reasoning_effort": "low", "max_tokens": 512, "logprobs": True, "top_logprobs": 1}
        models_status, models = _request("/v1/models")
        base_started = time.monotonic()
        base_status, base = _request("/v1/chat/completions", {"model": SERVED_MODEL_NAME, **common})
        base_seconds = time.monotonic() - base_started
        adapter_started = time.monotonic()
        adapter_status, adapter = _request("/v1/chat/completions", {"model": ADAPTER_NAME, **common})
        adapter_seconds = time.monotonic() - adapter_started
        unknown_status, _ = _request("/v1/chat/completions", {"model": UNKNOWN_ADAPTER_NAME, **common}, allow_http_error=True)
        if unknown_status != 404:
            raise RuntimeError("unknown adapter alias did not fail closed")
        self.log_file.flush()
        log_text = LOG_PATH.read_text(errors="replace")
        failure_patterns = [r"(?i)unexpected key", r"(?i)missing key", r"(?i)ignored key", r"(?i)shape mismatch",
                            r"(?i)failed to load.*lora", r"(?i)unsupported.*lora"]
        hits = [pattern for pattern in failure_patterns if re.search(pattern, log_text)]
        if hits:
            raise RuntimeError(f"fail-closed loader log check matched {hits}")
        listed = models.get("data")
        aliases = sorted(item.get("id") for item in listed if isinstance(item, dict) and isinstance(item.get("id"), str)) if isinstance(listed, list) else []
        if SERVED_MODEL_NAME not in aliases or ADAPTER_NAME not in aliases or UNKNOWN_ADAPTER_NAME in aliases:
            raise RuntimeError("model listing identity check failed")
        gpu = subprocess.run(["nvidia-smi", "--query-gpu=name,uuid,memory.total,memory.used,memory.free", "--format=csv,noheader,nounits"],
                             check=True, capture_output=True, text=True, timeout=10).stdout.strip()
        base_receipt = _final_receipt(base, SERVED_MODEL_NAME)
        adapter_receipt = _final_receipt(adapter, ADAPTER_NAME)
        return {"schema_version": 1, "status": "loaded_unverified", "scope": "loader_mechanics_only",
                "base": {**base_receipt, "http_status": base_status, "elapsed_seconds": base_seconds},
                "adapter": {**adapter_receipt, "http_status": adapter_status, "elapsed_seconds": adapter_seconds},
                "unknown_alias": {"model": UNKNOWN_ADAPTER_NAME, "http_status": unknown_status, "rejected": True},
                "models_listing": {"http_status": models_status, "ids": aliases},
                "tensor_accounting": {"status": "runtime_accounting_unverified",
                                      "on_disk_expected": EXPECTED_TENSOR_COUNT, "on_disk_verified": EXPECTED_TENSOR_COUNT,
                                      "runtime_loaded_key_count": None,
                                      "complete_runtime_key_accounting": False,
                                      "accounting_limit": "vLLM HTTP serving exposes no positive per-key load receipt; startup succeeded and loader logs were screened fail-closed",
                                      "log_failure_patterns_matched": []},
                "loader_log": {"bytes": LOG_PATH.stat().st_size, "sha256": _sha256(LOG_PATH),
                               "screened_failure_patterns": failure_patterns},
                "runtime": {"app_name": APP_NAME, "volume_name": VOLUME_NAME, "vllm_version": VLLM_VERSION,
                            "vllm_image": VLLM_IMAGE, "model_id": MODEL_ID, "model_revision": MODEL_REVISION,
                            "model_manifest_sha256": EXPECTED_MODEL_MANIFEST_SHA256, "fixture": self.fixture,
                            "gpu": gpu, "python_version": sys.version.split()[0], "max_model_len": 1024,
                            "max_num_seqs": 1, "snapshots_enabled": False, "native_quantization": "gpt_oss_mxfp4",
                            "moe_backend": "marlin", "linear_backend": "marlin", "max_lora_rank": 8,
                            "mixed_moe_lora_format": True, "is_3d_lora_weight": False}}

    @modal.exit()
    def stop(self) -> None:
        process = getattr(self, "process", None)
        if process is not None and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
        log_file = getattr(self, "log_file", None)
        if log_file is not None:
            log_file.close()
