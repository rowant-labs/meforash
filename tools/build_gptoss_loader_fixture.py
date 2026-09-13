#!/usr/bin/env python3
"""Build a deterministic, project-owned GPT-OSS PEFT loader fixture.

This performs no training, network, provider, GPU, or model-weight operation.
It uses the pinned tinker-cookbook 0.4.1 converter source already preserved by
the adapter-portability receipt and writes only beneath ignored ``runs/``.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import shutil
import sys
import tempfile
import types
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONVERTER_ROOT = ROOT / "runs/adapter-portability-v1"
CONVERTER_WHEEL = CONVERTER_ROOT / "packages/tinker_cookbook-0.4.1-py3-none-any.whl"
CONVERTER_WHEEL_SHA256 = "1776e82470534e47d8923378ea41d4c7e47a1ffdfcb1982507dfd0289ba9a70b"
DEFAULT_OUTPUT = ROOT / "runs/gptoss-loader-fixture-v1"

MODEL_ID = "openai/gpt-oss-20b"
MODEL_REVISION = "6cee5e81ee83917806bbde320786a8fb61efebee"
UPSTREAM_CONFIG_URL = (
    f"https://huggingface.co/{MODEL_ID}/blob/{MODEL_REVISION}/config.json"
)
RANK = 8
LORA_ALPHA = 16
LAYER = 0
HIDDEN_SIZE = 2880
ATTENTION_OUT = 64 * 64  # num_attention_heads * head_dim
INTERMEDIATE_SIZE = 2880
NUM_EXPERTS = 32


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def deterministic_tensor(torch, shape: tuple[int, ...], salt: int):
    """Small, nonzero BF16 values generated solely from integer positions."""
    count = 1
    for dimension in shape:
        count *= dimension
    values = torch.arange(count, dtype=torch.int64)
    values = ((values * 17 + salt) % 101 - 50).to(torch.float32) / 100_000
    return values.reshape(shape).to(torch.bfloat16)


def load_converter(extracted_source: Path):
    if not CONVERTER_WHEEL.is_file():
        raise FileNotFoundError("pinned adapter-portability converter wheel is missing")
    actual_wheel_hash = sha256(CONVERTER_WHEEL)
    if actual_wheel_hash != CONVERTER_WHEEL_SHA256:
        raise RuntimeError(
            f"converter wheel hash mismatch: {actual_wheel_hash}"
        )
    with zipfile.ZipFile(CONVERTER_WHEEL) as archive:
        archive.extractall(extracted_source)
    sys.path.insert(0, str(extracted_source))
    import tinker_cookbook

    weights = types.ModuleType("tinker_cookbook.weights")
    weights.__package__ = "tinker_cookbook.weights"
    weights.__path__ = [str(extracted_source / "tinker_cookbook" / "weights")]
    sys.modules[weights.__name__] = weights
    adapter = importlib.import_module("tinker_cookbook.weights._adapter")
    if tinker_cookbook.__version__ != "0.4.1":
        raise AssertionError(f"unexpected converter version: {tinker_cookbook.__version__}")
    return adapter.build_lora_adapter


def build(output: Path) -> dict:
    if not __debug__:
        raise RuntimeError("run without Python -O; integrity assertions must remain enabled")
    if output.exists():
        raise FileExistsError(f"output already exists: {output}")

    import torch
    from safetensors.torch import load_file, save_file

    base = output / "base-header"
    source_dir = output / "source-tinker-layout"
    adapter_dir = output / "adapter"
    base.mkdir(parents=True)
    source_dir.mkdir()

    config = {
        "architectures": ["GptOssForCausalLM"],
        "model_type": "gpt_oss",
        "hidden_size": HIDDEN_SIZE,
        "intermediate_size": INTERMEDIATE_SIZE,
        "num_hidden_layers": 24,
        "num_local_experts": NUM_EXPERTS,
        "num_attention_heads": 64,
        "num_key_value_heads": 8,
        "head_dim": 64,
    }
    (base / "config.json").write_text(json.dumps(config, indent=2) + "\n")
    # The converter needs only canonical state-dict names for GPT-OSS. These
    # scalar sentinels are deliberately not represented as model weights.
    save_file(
        {
            f"model.layers.{LAYER}.self_attn.q_proj.weight": torch.zeros(1),
            f"model.layers.{LAYER}.mlp.experts.down_proj": torch.zeros(1),
        },
        str(base / "model.safetensors"),
    )

    source = {
        f"base_model.model.model.layers.{LAYER}.attn.q_proj.lora_A.weight":
            deterministic_tensor(torch, (RANK, HIDDEN_SIZE), 11),
        f"base_model.model.model.layers.{LAYER}.attn.q_proj.lora_B.weight":
            deterministic_tensor(torch, (ATTENTION_OUT, RANK), 23),
        # Tinker's shared-B layout, expanded by the pinned converter to 32
        # independent 2D PEFT expert pairs targeting down_proj.
        f"base_model.model.model.layers.{LAYER}.mlp.experts.w2.lora_A.weight":
            deterministic_tensor(torch, (NUM_EXPERTS, RANK, INTERMEDIATE_SIZE), 37),
        f"base_model.model.model.layers.{LAYER}.mlp.experts.w2.lora_B.weight":
            deterministic_tensor(torch, (1, HIDDEN_SIZE, RANK), 53),
    }
    save_file(source, str(source_dir / "adapter_model.safetensors"))
    (source_dir / "adapter_config.json").write_text(
        json.dumps({"lora_alpha": LORA_ALPHA, "r": RANK}, indent=2) + "\n"
    )
    with tempfile.TemporaryDirectory(prefix="gptoss-fixture-converter-") as scratch:
        build_lora_adapter = load_converter(Path(scratch))
        build_lora_adapter(
            base_model=str(base), adapter_path=str(source_dir), output_path=str(adapter_dir)
        )

    actual = load_file(str(adapter_dir / "adapter_model.safetensors"))
    expected_shapes = {
        f"base_model.model.model.layers.{LAYER}.self_attn.q_proj.lora_A.weight": [RANK, HIDDEN_SIZE],
        f"base_model.model.model.layers.{LAYER}.self_attn.q_proj.lora_B.weight": [ATTENTION_OUT, RANK],
    }
    for expert in range(NUM_EXPERTS):
        prefix = f"base_model.model.model.layers.{LAYER}.mlp.experts.{expert}.down_proj"
        expected_shapes[f"{prefix}.lora_A.weight"] = [RANK, INTERMEDIATE_SIZE]
        expected_shapes[f"{prefix}.lora_B.weight"] = [HIDDEN_SIZE, RANK]
    actual_shapes = {key: list(value.shape) for key, value in sorted(actual.items())}
    assert actual_shapes == dict(sorted(expected_shapes.items()))

    source_q_a = source[f"base_model.model.model.layers.{LAYER}.attn.q_proj.lora_A.weight"]
    source_q_b = source[f"base_model.model.model.layers.{LAYER}.attn.q_proj.lora_B.weight"]
    assert torch.equal(actual[f"base_model.model.model.layers.{LAYER}.self_attn.q_proj.lora_A.weight"], source_q_a)
    assert torch.equal(actual[f"base_model.model.model.layers.{LAYER}.self_attn.q_proj.lora_B.weight"], source_q_b)
    source_down_a = source[f"base_model.model.model.layers.{LAYER}.mlp.experts.w2.lora_A.weight"]
    source_down_b = source[f"base_model.model.model.layers.{LAYER}.mlp.experts.w2.lora_B.weight"][0]
    for expert in range(NUM_EXPERTS):
        prefix = f"base_model.model.model.layers.{LAYER}.mlp.experts.{expert}.down_proj"
        assert torch.equal(actual[f"{prefix}.lora_A.weight"], source_down_a[expert])
        assert torch.equal(actual[f"{prefix}.lora_B.weight"], source_down_b)
    assert all(torch.count_nonzero(tensor).item() > 0 for tensor in actual.values())

    peft_config = json.loads((adapter_dir / "adapter_config.json").read_text())
    assert peft_config["r"] == RANK
    assert peft_config["lora_alpha"] == LORA_ALPHA
    assert peft_config["target_modules"] == ["down_proj", "q_proj"]
    # Replace the temporary local header path with immutable serving metadata.
    peft_config["base_model_name_or_path"] = MODEL_ID
    peft_config["revision"] = MODEL_REVISION
    (adapter_dir / "adapter_config.json").write_text(
        json.dumps(peft_config, indent=2, sort_keys=True) + "\n"
    )

    files = {
        name: {"bytes": (adapter_dir / name).stat().st_size, "sha256": sha256(adapter_dir / name)}
        for name in ("adapter_config.json", "adapter_model.safetensors")
    }
    report = {
        "status": "passed",
        "scope": "project-owned synthetic loader fixture; no training or quality claim",
        "model": {"id": MODEL_ID, "revision": MODEL_REVISION, "config_source": UPSTREAM_CONFIG_URL},
        "converter": {"package": "tinker-cookbook", "version": "0.4.1", "wheel_sha256": CONVERTER_WHEEL_SHA256},
        "dependencies": {"python": ".".join(map(str, sys.version_info[:3])), "torch": torch.__version__, "safetensors": importlib.metadata.version("safetensors")},
        "fixture": {"rank": RANK, "alpha": LORA_ALPHA, "layer": LAYER, "output_tensor_count": len(actual), "shapes": actual_shapes},
        "checks": {"all_values_nonzero_somewhere": True, "exact_value_mapping": True, "exact_shape_mapping": True},
        "files": files,
    }
    (output / "manifest.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    shutil.rmtree(base)
    shutil.rmtree(source_dir)
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    output = args.output.resolve()
    runs = (ROOT / "runs").resolve()
    if runs not in output.parents:
        raise ValueError("output must be a child of ignored runs/")
    report = build(output)
    print(json.dumps({"status": report["status"], "output": str(output), "files": report["files"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
