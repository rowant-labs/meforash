"""Evaluate a private Inkling checkpoint with the frozen baseline chat protocol."""
from __future__ import annotations

import contextlib
import json
import os
from pathlib import Path
import re
import sys

from bibleprep import evaluate as ev
from bibleprep import tinker_compare as comparison
from bibleprep import tinker_evaluate as native


def checkpoint_identity(path):
    candidate = Path(path)
    if candidate.is_symlink():
        raise ev.EvaluationError("Checkpoint reference must be a regular private run file.")
    resolved = candidate.resolve()
    try:
        resolved.relative_to(ev.RUNS_ROOT.resolve())
        raw = resolved.read_bytes()
        data = json.loads(raw)
        sampler = data["sampler_path"]
        if not isinstance(sampler, str) or not re.fullmatch(r"tinker://[A-Za-z0-9._:/-]+", sampler):
            raise ValueError
    except (ValueError, KeyError, OSError, TypeError) as exc:
        raise ev.EvaluationError("Invalid checkpoint reference inside private runs.") from exc
    return sampler, ev.digest(raw)


class AdapterTransport(comparison.NativeComparisonTransport):
    def initialize(self, config, secret):
        import tinker
        from tinker.lib.retry_handler import RetryConfig
        self.types = tinker.types
        self.pinned = comparison.load_pinned_tokenizer(config["model"], config.get("comparison_manifest"))
        self.tml = comparison.TmlProfile(self.pinned, config["model"], config.get("comparison_manifest"))
        self.parity = self.tml.parity
        self.service = tinker.ServiceClient(api_key=secret, base_url=native.TINKER_URL,
                                            max_retries=0, timeout=config["timeout_seconds"])
        # model_path is essential: base_model alone would silently evaluate the
        # unchanged model instead of the trained adapter.
        self.sampler = self.service.create_sampling_client(
            model_path=config["adapter_sampler_path"],
            retry_config=RetryConfig(enable_retry_logic=False, progress_timeout=config["timeout_seconds"]))
        self.base_model = self.sampler.get_base_model()
        if self.base_model != "thinkingmachines/Inkling":
            raise ev.EvaluationError("The checkpoint belongs to a different base model.")


def worker(connection):
    os.environ["TINKER_TELEMETRY"] = "0"
    with open(os.devnull, "w") as sink, contextlib.redirect_stdout(sink), contextlib.redirect_stderr(sink):
        transport = AdapterTransport()
        try:
            while True:
                request = connection.recv()
                if request is None:
                    break
                try:
                    connection.send({"ok": True, "response": transport(*request)})
                except Exception:
                    connection.send({"ok": False})
                    break
        except (EOFError, BrokenPipeError):
            pass
        finally:
            connection.close()


def run(config, checkpoint_file, *, execute=False, transport=None):
    if config.get("model") != "thinkingmachines/Inkling":
        raise ev.EvaluationError("This adapter evaluation supports full Inkling only.")
    sampler, fingerprint = checkpoint_identity(checkpoint_file)
    config = comparison.configure(config)
    config.update(adapter_sampler_path=sampler, checkpoint_reference_sha256=fingerprint,
                  transport="native_tinker_inkling_adapter", model_state="original_text_lora_adapter")
    bounded = native.BoundedNativeTransport(worker=worker) if transport is None else None
    try:
        # Resume is deliberately unavailable; uncertain generations require review.
        result = ev.run(config, execute=execute, resume=False, transport=transport or bounded)
        # ev.run's private manifest retains checkpoint identity, but stdout must not.
        return {key: value for key, value in result.items() if key != "config"}
    finally:
        if bounded is not None:
            bounded.close()


def main(argv=None):
    parser = comparison.parser()
    parser.description = __doc__
    parser.set_defaults(model="thinkingmachines/Inkling", reasoning_effort="medium",
                        dataset=str(comparison.ROOT / "evals/comparison-large-v1.jsonl"),
                        comparison_manifest="manifests/comparison-large-models-v1.json",
                        max_output_tokens=8192, max_input_tokens=6000, max_cases=24,
                        timeout_seconds=240)
    parser.add_argument("--checkpoint-file", required=True)
    args = vars(parser.parse_args(argv))
    execute, resume = args.pop("execute"), args.pop("resume")
    checkpoint = args.pop("checkpoint_file")
    if resume:
        parser.error("Adapter evaluation does not automatically resume uncertain calls.")
    try:
        summary = run(args, checkpoint, execute=execute)
    except Exception:
        print("Adapter evaluation stopped; inspect the private run record before retrying.", file=sys.stderr)
        return 2
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
