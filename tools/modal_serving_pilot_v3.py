"""Versioned v3 Modal pilot (`tools/modal_serving_pilot_v3.py`).

This serves the pinned gpt-oss-20b base with bounded resources.

This module only defines Modal resources. Importing it does not deploy an App,
create a Volume, download weights, or invoke a model. The operator stages this
single public source file in an otherwise empty directory before using Modal.

References:
  https://modal.com/docs/guide/memory-snapshots
  https://modal.com/docs/examples/lfm_snapshot
  https://docs.vllm.ai/en/v0.29.0/features/sleep_mode/
"""

from __future__ import annotations

from contextlib import contextmanager
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import uuid
from typing import Any, Iterator
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

import modal


MODEL_ID = "openai/gpt-oss-20b"
MODEL_REVISION = "6cee5e81ee83917806bbde320786a8fb61efebee"
SERVED_MODEL_NAME = MODEL_ID
VLLM_VERSION = "0.29.0"
VLLM_IMAGE = (
    "vllm/vllm-openai@sha256:"
    "082ca6f035279109041ffd3fe0695cb568b29bc580b35c4f297a66a08b216c1b"
)
EXPECTED_MANIFEST_SHA256 = (
    "5f8255b4762b7dc5fe67c74e79db77e3d560f7d951231e74a5870803b2a136e4"
)

VOLUME_NAME = "meforash-modal-serving-v3-weights"
VOLUME_ROOT = Path("/weights")
MODEL_DIR_NAME = f"openai-gpt-oss-20b-{MODEL_REVISION}"
MODEL_DIR = VOLUME_ROOT / MODEL_DIR_NAME
MANIFEST_PATH = MODEL_DIR / "manifest.json"

VLLM_HOST = "127.0.0.1"
VLLM_PORT = 8000
VLLM_BASE_URL = f"http://{VLLM_HOST}:{VLLM_PORT}"
STARTUP_TIMEOUT_SECONDS = 900
REQUEST_TIMEOUT_SECONDS = 180
FUNCTION_TIMEOUT_SECONDS = 600
SCALEDOWN_WINDOW_SECONDS = 60
MAX_OUTPUT_TOKENS = 2048

_snapshot_value = os.environ.get("MODAL_PILOT_SNAPSHOT", "0")
if _snapshot_value not in {"0", "1"}:
    raise ValueError("MODAL_PILOT_SNAPSHOT must be exactly '0' or '1'")
SNAPSHOT_ENABLED = _snapshot_value == "1"
APP_NAME = (
    "meforash-modal-serving-v3-snapshot"
    if SNAPSHOT_ENABLED
    else "meforash-modal-serving-v3-baseline"
)

# Sizes come from the pinned Hugging Face repository tree. The large-file OIDs
# are SHA-256 digests and are checked before the immutable manifest is written.
MODEL_FILES: dict[str, dict[str, int | str | None]] = {
    "model-00000-of-00002.safetensors": {
        "size": 4_792_272_488,
        "sha256": "16d0f997dcfc4462089d536bffe51b4bcea2f872f5c430be09ef8ed392312427",
    },
    "model-00001-of-00002.safetensors": {
        "size": 4_798_702_184,
        "sha256": "4fbe328ab445455d6f58dc73852b85873bd626986310abd91cd4d2ce3245eaea",
    },
    "model-00002-of-00002.safetensors": {
        "size": 4_170_342_232,
        "sha256": "a18106b209e9ab35c3406db4f6f12a927364a058b21e9d1373d682e20674b303",
    },
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

prepare_image = modal.Image.debian_slim(python_version="3.12")
serve_image = modal.Image.from_registry(VLLM_IMAGE).entrypoint([]).run_commands("ln -s $(which python3) /usr/bin/python").env(
    {
        "HF_HUB_OFFLINE": "1",
        "TRANSFORMERS_OFFLINE": "1",
        "HF_DATASETS_OFFLINE": "1",
        "VLLM_NO_USAGE_STATS": "1",
        "VLLM_SERVER_DEV_MODE": "1" if SNAPSHOT_ENABLED else "0",
        "MODAL_PILOT_SNAPSHOT": "1" if SNAPSHOT_ENABLED else "0",
    }
)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(8 * 1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _download_url(filename: str) -> str:
    repo = "/".join(quote(part, safe="") for part in MODEL_ID.split("/"))
    revision = quote(MODEL_REVISION, safe="")
    remote_path = quote(filename, safe="/")
    return f"https://huggingface.co/{repo}/resolve/{revision}/{remote_path}?download=true"


def _verify_file(path: Path, spec: dict[str, int | str | None]) -> dict[str, Any]:
    actual_size = path.stat().st_size
    expected_size = int(spec["size"])
    if actual_size != expected_size:
        raise RuntimeError(
            f"size mismatch for {path.name}: got {actual_size}, expected {expected_size}"
        )
    actual_sha256 = _sha256_file(path)
    expected_sha256 = spec["sha256"]
    if expected_sha256 is not None and actual_sha256 != expected_sha256:
        raise RuntimeError(f"SHA-256 mismatch for {path.name}")
    return {"path": path.name, "size": actual_size, "sha256": actual_sha256}


def _validate_index() -> None:
    index = json.loads((MODEL_DIR / "model.safetensors.index.json").read_text())
    referenced = set(index.get("weight_map", {}).values())
    expected = {
        name for name in MODEL_FILES if name.endswith(".safetensors")
    }
    if referenced != expected:
        raise RuntimeError(
            f"weight index references {sorted(referenced)}, expected {sorted(expected)}"
        )


def _manifest_bytes(files: list[dict[str, Any]]) -> bytes:
    manifest = {
        "schema_version": 1,
        "model_id": MODEL_ID,
        "revision": MODEL_REVISION,
        "source": f"https://huggingface.co/{MODEL_ID}/tree/{MODEL_REVISION}",
        "files": sorted(files, key=lambda item: item["path"]),
    }
    return (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _verify_directory_allowlist() -> None:
    allowed = set(MODEL_FILES) | {MANIFEST_PATH.name}
    unexpected = sorted(path.name for path in MODEL_DIR.iterdir() if path.name not in allowed)
    if unexpected:
        raise RuntimeError(f"unexpected files in immutable model directory: {unexpected}")


def _read_and_verify_manifest_full() -> dict[str, Any]:
    """Rehash every file; used only by the CPU preparation function."""

    _verify_directory_allowlist()
    manifest_bytes = MANIFEST_PATH.read_bytes()
    manifest = json.loads(manifest_bytes)
    if manifest.get("model_id") != MODEL_ID or manifest.get("revision") != MODEL_REVISION:
        raise RuntimeError("existing weight manifest has the wrong model identity")
    actual_files = []
    for filename, spec in MODEL_FILES.items():
        path = MODEL_DIR / filename
        if not path.is_file():
            raise RuntimeError(f"manifest is present but {filename} is missing")
        actual_files.append(_verify_file(path, spec))
    expected_bytes = _manifest_bytes(actual_files)
    if manifest_bytes != expected_bytes:
        raise RuntimeError("existing weight manifest does not match the pinned files")
    manifest_sha256 = hashlib.sha256(manifest_bytes).hexdigest()
    if manifest_sha256 != EXPECTED_MANIFEST_SHA256:
        raise RuntimeError("existing weight manifest does not match the v1 verified manifest")
    _validate_index()
    return {
        "status": "verified_existing",
        "model_id": MODEL_ID,
        "revision": MODEL_REVISION,
        "manifest_sha256": manifest_sha256,
        "logical_bytes": sum(item["size"] for item in actual_files),
        "file_count": len(actual_files),
    }


def _read_and_verify_manifest_lightweight() -> dict[str, Any]:
    """Verify serving identity without re-reading the three large weight files."""

    _verify_directory_allowlist()
    manifest_bytes = MANIFEST_PATH.read_bytes()
    manifest_sha256 = hashlib.sha256(manifest_bytes).hexdigest()
    if manifest_sha256 != EXPECTED_MANIFEST_SHA256:
        raise RuntimeError("weight manifest does not match the v1 verified manifest")
    manifest = json.loads(manifest_bytes)
    if (
        manifest.get("schema_version") != 1
        or manifest.get("model_id") != MODEL_ID
        or manifest.get("revision") != MODEL_REVISION
    ):
        raise RuntimeError("weight manifest has the wrong model identity")

    manifest_files = manifest.get("files")
    if not isinstance(manifest_files, list):
        raise RuntimeError("weight manifest files must be a list")
    entries = {
        item.get("path"): item
        for item in manifest_files
        if isinstance(item, dict) and isinstance(item.get("path"), str)
    }
    if set(entries) != set(MODEL_FILES) or len(entries) != len(manifest_files):
        raise RuntimeError("weight manifest file allowlist mismatch")

    logical_bytes = 0
    for filename, spec in MODEL_FILES.items():
        path = MODEL_DIR / filename
        if path.is_symlink() or not path.is_file():
            raise RuntimeError(f"pinned model file is missing or not regular: {filename}")
        actual_size = path.stat().st_size
        expected_size = int(spec["size"])
        entry = entries[filename]
        if actual_size != expected_size or entry.get("size") != expected_size:
            raise RuntimeError(f"size mismatch for {filename}")
        if entry.get("sha256") != spec["sha256"] and spec["sha256"] is not None:
            raise RuntimeError(f"manifest SHA-256 entry mismatch for {filename}")
        logical_bytes += actual_size

    _validate_index()
    return {
        "status": "verified_lightweight",
        "model_id": MODEL_ID,
        "revision": MODEL_REVISION,
        "manifest_sha256": manifest_sha256,
        "logical_bytes": logical_bytes,
        "file_count": len(entries),
    }


@app.function(
    image=prepare_image,
    volumes={str(VOLUME_ROOT): weights_volume},
    cpu=(2.0, 2.0),
    memory=(8192, 8192),
    min_containers=0,
    max_containers=1,
    scaledown_window=SCALEDOWN_WINDOW_SECONDS,
    retries=0,
    timeout=FUNCTION_TIMEOUT_SECONDS,
    startup_timeout=STARTUP_TIMEOUT_SECONDS,
)
def prepare_weights() -> dict[str, Any]:
    """Download and bind only the pinned root model files to the named Volume."""

    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    for filename in MODEL_FILES:
        (MODEL_DIR / f"{filename}.partial").unlink(missing_ok=True)
    (MODEL_DIR / "manifest.json.partial").unlink(missing_ok=True)
    allowed = set(MODEL_FILES) | {MANIFEST_PATH.name}
    unexpected = sorted(path.name for path in MODEL_DIR.iterdir() if path.name not in allowed)
    if unexpected:
        raise RuntimeError(f"unexpected files in immutable model directory: {unexpected}")
    if MANIFEST_PATH.exists():
        return _read_and_verify_manifest_full()

    verified: list[dict[str, Any]] = []
    for filename, spec in MODEL_FILES.items():
        destination = MODEL_DIR / filename
        partial = destination.with_name(destination.name + ".partial")
        partial.unlink(missing_ok=True)
        if not destination.exists():
            request = Request(
                _download_url(filename),
                headers={"User-Agent": "Meforash-Modal-serving-pilot/1.0"},
            )
            try:
                with urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response, partial.open(
                    "wb"
                ) as output:
                    while chunk := response.read(8 * 1024 * 1024):
                        output.write(chunk)
            except (HTTPError, URLError, TimeoutError) as exc:
                partial.unlink(missing_ok=True)
                raise RuntimeError(f"download failed for {filename}: {type(exc).__name__}") from exc
            _verify_file(partial, spec)
            os.replace(partial, destination)
        verified.append(_verify_file(destination, spec))

    _validate_index()
    manifest_bytes = _manifest_bytes(verified)
    manifest_sha256 = hashlib.sha256(manifest_bytes).hexdigest()
    if manifest_sha256 != EXPECTED_MANIFEST_SHA256:
        raise RuntimeError("downloaded files do not reproduce the v1 verified manifest")
    temporary_manifest = MANIFEST_PATH.with_name("manifest.json.partial")
    temporary_manifest.write_bytes(manifest_bytes)
    os.replace(temporary_manifest, MANIFEST_PATH)
    weights_volume.commit()
    return {
        "status": "prepared",
        "model_id": MODEL_ID,
        "revision": MODEL_REVISION,
        "manifest_sha256": manifest_sha256,
        "logical_bytes": sum(item["size"] for item in verified),
        "file_count": len(verified),
    }


def _request_json(
    method: str,
    path: str,
    *,
    payload: dict[str, Any] | None = None,
    timeout: int = REQUEST_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    body = None if payload is None else json.dumps(payload, separators=(",", ":")).encode()
    headers = {"Accept": "application/json"}
    if body is not None:
        headers["Content-Type"] = "application/json"
    request = Request(VLLM_BASE_URL + path, data=body, headers=headers, method=method)
    try:
        with urlopen(request, timeout=timeout) as response:
            raw = response.read()
    except HTTPError as exc:
        detail = exc.read(2048).decode("utf-8", errors="replace")
        raise RuntimeError(f"local vLLM {path} returned HTTP {exc.code}: {detail}") from exc
    except (URLError, TimeoutError) as exc:
        raise RuntimeError(f"local vLLM {path} failed: {type(exc).__name__}") from exc
    return json.loads(raw) if raw else {}


def _public_usage(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    allowed_scalar = {"prompt_tokens", "completion_tokens", "total_tokens"}
    result = {key: value[key] for key in allowed_scalar if isinstance(value.get(key), int)}
    details = value.get("completion_tokens_details")
    if isinstance(details, dict):
        clean_details = {
            key: count
            for key, count in details.items()
            if isinstance(key, str) and isinstance(count, int)
        }
        if clean_details:
            result["completion_tokens_details"] = clean_details
    return result or None


def _iter_completion(
    nonce: str,
    prompt: str,
    *,
    max_tokens: int,
    reasoning_effort: str,
) -> Iterator[dict[str, Any]]:
    if not isinstance(nonce, str) or not nonce or len(nonce) > 128:
        raise ValueError("nonce must be a nonempty string of at most 128 characters")
    if not isinstance(prompt, str) or not prompt or len(prompt) > 32_768:
        raise ValueError("prompt must be a nonempty string of at most 32,768 characters")
    if not isinstance(max_tokens, int) or not 1 <= max_tokens <= MAX_OUTPUT_TOKENS:
        raise ValueError(f"max_tokens must be between 1 and {MAX_OUTPUT_TOKENS}")
    if reasoning_effort not in {"low", "medium", "high"}:
        raise ValueError("reasoning_effort must be low, medium, or high")

    payload = {
        "model": SERVED_MODEL_NAME,
        "messages": [{"role": "user", "content": prompt}],
        "reasoning_effort": reasoning_effort,
        "max_tokens": max_tokens,
        "temperature": 0,
        "seed": 0,
        "stream": True,
        "stream_options": {"include_usage": True},
    }
    request = Request(
        VLLM_BASE_URL + "/v1/chat/completions",
        data=json.dumps(payload, separators=(",", ":")).encode(),
        headers={
            "Accept": "text/event-stream",
            "Content-Type": "application/json",
            "X-Request-ID": nonce,
        },
        method="POST",
    )
    started = time.monotonic()
    first_event_seconds: float | None = None
    first_content_seconds: float | None = None
    finish_reason: str | None = None
    usage: dict[str, Any] | None = None
    response_id: str | None = None
    saw_done = False

    try:
        with urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
            http_status = response.status
            for raw_line in response:
                line = raw_line.decode("utf-8", errors="strict").strip()
                if not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if data == "[DONE]":
                    saw_done = True
                    break
                if not data:
                    continue
                event = json.loads(data)
                elapsed = time.monotonic() - started
                if first_event_seconds is None:
                    first_event_seconds = elapsed
                if isinstance(event.get("id"), str):
                    response_id = event["id"]
                event_usage = _public_usage(event.get("usage"))
                if event_usage is not None:
                    usage = event_usage
                choices = event.get("choices")
                if not isinstance(choices, list):
                    continue
                for choice in choices:
                    if not isinstance(choice, dict):
                        continue
                    if isinstance(choice.get("finish_reason"), str):
                        finish_reason = choice["finish_reason"]
                    delta = choice.get("delta")
                    if not isinstance(delta, dict):
                        continue
                    # Deliberately ignore reasoning/reasoning_content fields. Only
                    # final-channel content is allowed to leave this container.
                    content = delta.get("content")
                    if isinstance(content, str) and content:
                        if first_content_seconds is None:
                            first_content_seconds = elapsed
                        yield {"type": "content", "text": content}
    except HTTPError as exc:
        # Do not propagate a response body that could repeat request content.
        raise RuntimeError(f"local vLLM completion returned HTTP {exc.code}") from exc
    except (URLError, TimeoutError) as exc:
        raise RuntimeError(f"local vLLM completion failed: {type(exc).__name__}") from exc

    elapsed = time.monotonic() - started
    status = "completed" if saw_done and first_content_seconds is not None and finish_reason == "stop" else "incomplete"
    yield {
        "type": "final",
        "status": status,
        "http_status": http_status,
        "response_id": response_id,
        "finish_reason": finish_reason,
        "usage": usage,
        "local_vllm_first_event_seconds": first_event_seconds,
        "local_vllm_first_final_content_seconds": first_content_seconds,
        "local_vllm_total_seconds": elapsed,
    }


_class_options: dict[str, Any] = {}
if SNAPSHOT_ENABLED:
    _class_options = {
        "enable_memory_snapshot": True,
        "experimental_options": {"enable_gpu_snapshot": True},
    }

_start_enter = modal.enter(snap=True) if SNAPSHOT_ENABLED else modal.enter()
_restore_enter = modal.enter(snap=False) if SNAPSHOT_ENABLED else modal.enter()


@app.cls(
    image=serve_image,
    gpu="L4",
    volumes={str(VOLUME_ROOT): weights_volume.read_only()},
    cpu=(2.0, 2.0),
    memory=(32768, 32768),
    min_containers=0,
    max_containers=1,
    scaledown_window=SCALEDOWN_WINDOW_SECONDS,
    retries=0,
    timeout=FUNCTION_TIMEOUT_SECONDS,
    startup_timeout=STARTUP_TIMEOUT_SECONDS,
    **_class_options,
)
@modal.concurrent(max_inputs=1, target_inputs=1)
class Model:
    _process: subprocess.Popen[bytes]

    @contextmanager
    def _timed_startup_phase(self, phase: str) -> Iterator[None]:
        started = time.monotonic()
        try:
            yield
        except BaseException as exc:
            elapsed = time.monotonic() - started
            self._startup_timings[f"{phase}_seconds"] = elapsed
            print(
                json.dumps(
                    {
                        "event": "modal_serving_pilot_v3_phase",
                        "phase": phase,
                        "status": "failed",
                        "monotonic_elapsed_seconds": elapsed,
                        "error_type": type(exc).__name__,
                    },
                    sort_keys=True,
                ),
                flush=True,
            )
            raise
        else:
            elapsed = time.monotonic() - started
            self._startup_timings[f"{phase}_seconds"] = elapsed
            print(
                json.dumps(
                    {
                        "event": "modal_serving_pilot_v3_phase",
                        "phase": phase,
                        "status": "completed",
                        "monotonic_elapsed_seconds": elapsed,
                    },
                    sort_keys=True,
                ),
                flush=True,
            )

    def _wait_ready(self) -> None:
        deadline = time.monotonic() + STARTUP_TIMEOUT_SECONDS
        last_error = "not started"
        while time.monotonic() < deadline:
            return_code = self._process.poll()
            if return_code is not None:
                raise RuntimeError(f"vLLM exited before readiness with code {return_code}")
            try:
                _request_json("GET", "/health", timeout=5)
                return
            except Exception as exc:  # readiness errors are retained only by type
                last_error = type(exc).__name__
                time.sleep(1)
        raise TimeoutError(f"vLLM was not ready within {STARTUP_TIMEOUT_SECONDS}s ({last_error})")

    def _wait_sleep_state(self, expected: bool) -> None:
        deadline = time.monotonic() + STARTUP_TIMEOUT_SECONDS
        while time.monotonic() < deadline:
            if self._process.poll() is not None:
                raise RuntimeError("vLLM exited while changing sleep state")
            try:
                state = _request_json("GET", "/is_sleeping", timeout=5)
                if bool(state.get("is_sleeping")) == expected:
                    return
            except Exception:
                pass
            time.sleep(1)
        raise TimeoutError(f"vLLM did not reach sleeping={expected}")

    def _warm_for_snapshot(self) -> None:
        for index in range(3):
            events = list(
                _iter_completion(
                    f"snapshot-warmup-{index + 1}",
                    "Reply with exactly the word ready.",
                    max_tokens=256,
                    reasoning_effort="low",
                )
            )
            final = events[-1] if events else {}
            if final.get("type") != "final" or final.get("status") != "completed":
                raise RuntimeError("snapshot warmup did not complete")

    @_start_enter
    def start(self) -> None:
        self._startup_timings: dict[str, float] = {}
        with self._timed_startup_phase("verification"):
            if not MANIFEST_PATH.is_file():
                raise RuntimeError("pinned model manifest is missing; run prepare_weights first")
            _read_and_verify_manifest_lightweight()
            actual_vllm_version = importlib.metadata.version("vllm")
            if actual_vllm_version != VLLM_VERSION:
                raise RuntimeError(
                    f"vLLM version mismatch: got {actual_vllm_version}, expected {VLLM_VERSION}"
                )
        command = [
            "vllm",
            "serve",
            str(MODEL_DIR),
            "--tokenizer",
            str(MODEL_DIR),
            "--served-model-name",
            SERVED_MODEL_NAME,
            "--host",
            VLLM_HOST,
            "--port",
            str(VLLM_PORT),
            "--max-model-len",
            "8192",
            "--max-num-seqs",
            "1",
            "--gpu-memory-utilization",
            "0.85",
            "--enforce-eager",
            "--no-enable-log-requests",
            "--generation-config",
            "vllm",
        ]
        if SNAPSHOT_ENABLED:
            command.append("--enable-sleep-mode")
        with self._timed_startup_phase("vllm_start_ready"):
            self._process = subprocess.Popen(command)
            self._wait_ready()
        if SNAPSHOT_ENABLED:
            with self._timed_startup_phase("warmup"):
                self._warm_for_snapshot()
            with self._timed_startup_phase("sleep"):
                _request_json("POST", "/sleep?level=1")
                self._wait_sleep_state(True)
            # This marks only the post-sleep capture boundary. It is not proof
            # that Modal created or later restored a GPU snapshot.
            print(
                json.dumps(
                    {
                        "event": "modal_serving_pilot_v3_snapshot_capture_marker",
                        "phase": "post_sleep",
                        "sleep_confirmed": True,
                    },
                    sort_keys=True,
                ),
                flush=True,
            )

    @_restore_enter
    def restore(self) -> None:
        if not hasattr(self, "_startup_timings"):
            self._startup_timings = {}
        self._boot_token = uuid.uuid4().hex
        with self._timed_startup_phase("restore_wake"):
            if SNAPSHOT_ENABLED:
                _request_json("POST", "/wake_up")
                self._wait_ready()
                self._wait_sleep_state(False)

    def _metadata(self) -> dict[str, Any]:
        manifest_bytes = MANIFEST_PATH.read_bytes()
        gpu = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=name,uuid,memory.total,compute_cap",
                "--format=csv,noheader,nounits",
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        ).stdout.strip()
        return {
            "app_name": APP_NAME,
            "snapshot_enabled": SNAPSHOT_ENABLED,
            "boot_token": self._boot_token,
            "startup_timings": dict(self._startup_timings),
            "gpu": gpu,
            "python_version": sys.version.split()[0],
            "vllm_package_version": importlib.metadata.version("vllm"),
            "vllm_api_version": _request_json("GET", "/version"),
            "models": _request_json("GET", "/v1/models"),
            "model_id": MODEL_ID,
            "served_model_name": SERVED_MODEL_NAME,
            "model_revision": MODEL_REVISION,
            "model_manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
            "vllm_image": VLLM_IMAGE,
            "max_model_len": 8192,
            "max_num_seqs": 1,
            "gpu_memory_utilization": 0.85,
            "enforce_eager": True,
        }

    @modal.method()
    def metadata(self) -> dict[str, Any]:
        """Return bounded runtime identity without reading the process environment."""

        return self._metadata()

    @modal.method()
    def probe(
        self,
        nonce: str,
        prompt: str,
        max_tokens: int = 2048,
        reasoning_effort: str = "low",
    ) -> dict[str, Any]:
        """Return a durable, final-only result suitable for spawn/get reconciliation.

        Local vLLM timings begin only after the Modal container and method are
        running. The caller must measure Modal scheduling/startup-inclusive TTFT.
        """

        content: list[str] = []
        final: dict[str, Any] | None = None
        for event in _iter_completion(
            nonce,
            prompt,
            max_tokens=max_tokens,
            reasoning_effort=reasoning_effort,
        ):
            if event["type"] == "content":
                content.append(event["text"])
            else:
                final = event
        if final is None:
            raise RuntimeError("local vLLM stream ended without a final event")
        return {
            "nonce": nonce,
            "content": "".join(content),
            **final,
            "runtime": self._metadata(),
        }

    @modal.method(is_generator=True)
    def remote_gen(
        self,
        nonce: str,
        prompt: str,
        max_tokens: int = 2048,
        reasoning_effort: str = "low",
    ) -> Iterator[dict[str, Any]]:
        """Yield final text and attach same-container identity to the terminal event."""

        for event in _iter_completion(
            nonce,
            prompt,
            max_tokens=max_tokens,
            reasoning_effort=reasoning_effort,
        ):
            if event.get("type") == "final":
                runtime = self._metadata()
                event = {**event, "nonce": nonce, "runtime": runtime}
                print(
                    json.dumps(
                        {
                            "event": "modal_serving_pilot_v3_stream_complete",
                            "nonce": nonce,
                            "boot_token": runtime["boot_token"],
                        },
                        sort_keys=True,
                    ),
                    flush=True,
                )
            yield event

    @modal.exit()
    def stop(self) -> None:
        process = getattr(self, "_process", None)
        if process is None or process.poll() is not None:
            return
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
