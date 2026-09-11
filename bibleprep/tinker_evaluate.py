"""Native Tinker baseline sampling with the project's bounded evaluation journal."""

from __future__ import annotations

from datetime import datetime, timezone
import contextlib
import importlib.metadata
import json
import multiprocessing
import os
from pathlib import Path
import sys

from bibleprep import evaluate as ev


ROOT = Path(__file__).resolve().parents[1]
TOKENIZER_DIR = ROOT / "data/raw/tokenizers/gpt-oss-120b"
TINKER_URL = "https://tinker.thinkingmachines.dev/services/tinker-prod"
SUPPORTED_MODELS = {"openai/gpt-oss-120b", "openai/gpt-oss-20b"}
SPECIAL = ("<|start|>", "<|channel|>", "<|message|>", "<|end|>", "<|return|>", "<|call|>")
PARITY_PROBES = (
    "English instructions.\nHebrew, Aramaic, and Greek must stay distinct.",
    "בְּרֵאשִׁ֖ית בָּרָ֣א אֱלֹהִ֑ים", "מְנֵ֥א מְנֵ֖א תְּקֵ֥ל וּפַרְסִֽין",
    "Ἐν ἀρχῇ ἦν ὁ λόγος. ⟦ἐφοβοῦντο γάρ⟧ [καὶ]", "שׁ שִׁ שִׁ ἀ α\u0301",
    "".join(SPECIAL),
)


def local_identity():
    """Check existing pinned assets; never download files or inspect credentials."""
    tokenizer_manifest = json.loads((ROOT / "manifests/tokenizer.json").read_text())
    template_manifest = json.loads((ROOT / "manifests/chat-template.json").read_text())
    for item in tokenizer_manifest["files"]:
        if ev.digest((TOKENIZER_DIR / item["path"]).read_bytes()) != item["sha256"]:
            raise ev.EvaluationError("Pinned tokenizer asset failed its checksum check.")
    if ev.digest((TOKENIZER_DIR / "chat_template.jinja").read_bytes()) != template_manifest["sha256"]:
        raise ev.EvaluationError("Pinned chat template failed its checksum check.")
    return {
        "tokenizer_revision": tokenizer_manifest["revision"],
        "tokenizer_sha256": next(item["sha256"] for item in tokenizer_manifest["files"] if item["path"] == "tokenizer.json"),
        "chat_template_sha256": template_manifest["sha256"],
    }


def configure(config):
    config = dict(config)
    if config["model"] not in SUPPORTED_MODELS:
        raise ev.EvaluationError("This baseline adapter only supports the verified gpt-oss models.")
    if config["base_url"].rstrip("/") != TINKER_URL:
        raise ev.EvaluationError("Native Tinker execution requires the official Tinker base URL.")
    if config.get("reasoning_effort") not in {"low", "medium", "high"}:
        raise ev.EvaluationError("An explicit reasoning effort is required.")
    if not ev.finite_nonnegative(config.get("temperature")) or config["temperature"] > 2:
        raise ev.EvaluationError("Temperature must be a finite number between zero and two.")
    if not isinstance(config.get("seed"), int) or not 0 <= config["seed"] <= 2**31 - 1:
        raise ev.EvaluationError("Seed must be a nonnegative 31-bit integer.")
    try:
        datetime.strptime(config["prompt_date"], "%Y-%m-%d")
    except (KeyError, TypeError, ValueError) as exc:
        raise ev.EvaluationError("Prompt date must be YYYY-MM-DD.") from exc
    config.update(local_identity())
    config.update({"transport": "native_tinker", "renderer": "pinned_official_hf_chat_template",
                   "accounting_source": "submitted_prompt_and_returned_sequence_token_counts",
                   "accounting_is_invoice": False, "application_sampling_retries": False,
                   "sdk_internal_submission_retries": "may_occur; count_not_exposed",
                   "request_deadline": "worker_process_terminated_on_timeout"})
    for package in ("tinker", "transformers", "tokenizers", "jinja2"):
        try:
            config[package + "_version"] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            config[package + "_version"] = "not_installed"
    return config


def load_pinned_tokenizer():
    from transformers import PreTrainedTokenizerFast
    return PreTrainedTokenizerFast.from_pretrained(TOKENIZER_DIR, local_files_only=True)


def token_ids(tokenizer, text):
    values = tokenizer.encode(text, add_special_tokens=False)
    return list(values.ids if hasattr(values, "ids") else values)


def vocabulary_hash(tokenizer):
    return ev.digest(ev.json_bytes(tokenizer.get_vocab()))


def assert_tokenizer_parity(pinned, live):
    """Compare the complete token mapping and sensitive Unicode examples."""
    if pinned.get_vocab() != live.get_vocab():
        raise ev.EvaluationError("Provider tokenizer vocabulary differs from the pinned tokenizer.")
    if any(token_ids(pinned, probe) != token_ids(live, probe) for probe in PARITY_PROBES):
        raise ev.EvaluationError("Provider tokenizer encoding differs from the pinned tokenizer.")
    for marker in SPECIAL:
        encoded = token_ids(pinned, marker)
        if len(encoded) != 1 or pinned.decode(encoded, skip_special_tokens=False) != marker:
            raise ev.EvaluationError("A required Harmony marker is not a single verified token.")
    return {"vocabulary_sha256": vocabulary_hash(pinned), "unicode_probes_passed": len(PARITY_PROBES),
            "all_prompt_token_ids_compared": True}


def render_prompt(payload, config, tokenizer):
    date = datetime.strptime(config["prompt_date"], "%Y-%m-%d")
    rendered = tokenizer.apply_chat_template(
        payload["messages"], tokenize=False, add_generation_prompt=True,
        reasoning_effort=config["reasoning_effort"],
        strftime_now=lambda format_string: date.strftime(format_string),
    )
    if not rendered.endswith("<|start|>assistant"):
        raise ev.EvaluationError("The pinned template's assistant generation prefix changed.")
    if "Reasoning: " + config["reasoning_effort"] not in rendered:
        raise ev.EvaluationError("The template did not apply the explicit reasoning setting.")
    if "Current date: " + config["prompt_date"] not in rendered:
        raise ev.EvaluationError("The template did not apply the pinned prompt date.")
    return rendered, token_ids(tokenizer, rendered)


def parse_harmony(tokens, tokenizer, provider_stop):
    """Extract only explicit final-channel text; never relabel analysis as an answer."""
    markers = {name: token_ids(tokenizer, name)[0] for name in SPECIAL}
    start, channel, message, end, returned, call = (markers[name] for name in SPECIAL)
    # The generation prefix is already in the prompt; reconstruct it only for parsing.
    stream = token_ids(tokenizer, "<|start|>assistant") + list(tokens)
    cursor, final_parts, analysis_tokens, issues = 0, [], 0, []
    saw_return, saw_call = False, False
    while cursor < len(stream):
        if stream[cursor] != start:
            issues.append("unexpected_tokens_outside_message")
            break
        try:
            boundary = stream.index(message, cursor + 1)
        except ValueError:
            issues.append("incomplete_message_header")
            break
        header = tokenizer.decode(stream[cursor + 1:boundary], skip_special_tokens=False)
        body_end = boundary + 1
        while body_end < len(stream) and stream[body_end] not in {end, returned, call, start}:
            body_end += 1
        terminal = stream[body_end] if body_end < len(stream) else None
        body = stream[boundary + 1:body_end]
        if header == "assistant<|channel|>final":
            final_parts.append(tokenizer.decode(body, skip_special_tokens=False))
        elif header == "assistant<|channel|>analysis":
            analysis_tokens += len(body)
        else:
            issues.append("unexpected_channel_or_recipient")
        if terminal == returned:
            saw_return = True
        if terminal == call:
            saw_call = True
        if terminal in {returned, call}:
            if body_end + 1 != len(stream):
                issues.append("tokens_after_turn_end")
            break
        if terminal is None:
            issues.append("incomplete_message_body")
            break
        if terminal == start:
            issues.append("missing_message_end")
            break
        cursor = body_end + 1
    if provider_stop == "length":
        finish = "length"
    elif saw_call:
        finish = "tool_calls"
    elif provider_stop == "stop" and saw_return and final_parts and not issues:
        finish = "stop"
    else:
        finish = "incomplete_harmony"
    return {"content": "\n".join(final_parts), "finish_reason": finish,
            "analysis_content_tokens": analysis_tokens, "parse_issues": issues,
            "provider_stop_reason": provider_stop, "turn_end_observed": saw_return}


class NativeTransport:
    """Create a base sampler lazily, after run validation and a cost reservation."""

    def __init__(self):
        self.sampler = None
        self.service = None

    def initialize(self, config, secret):
        from bibleprep.tinker_access import check_access
        access = check_access(secret, timeout_seconds=min(20, config["timeout_seconds"]))
        if access.get("status") != "ready":
            raise ev.EvaluationError("Tinker account access is not ready; run the read-only access check.")
        available = "gpt_oss_120b_available" if config["model"] == "openai/gpt-oss-120b" else "gpt_oss_20b_available"
        if not access.get(available):
            raise ev.EvaluationError("The selected gpt-oss model is not available to this account.")
        import tinker
        from tinker.lib.retry_handler import RetryConfig
        self.types = tinker.types
        self.pinned = load_pinned_tokenizer()
        self.service = tinker.ServiceClient(api_key=secret, base_url=TINKER_URL,
                                            max_retries=0, timeout=config["timeout_seconds"])
        self.sampler = self.service.create_sampling_client(
            base_model=config["model"],
            retry_config=RetryConfig(enable_retry_logic=False, progress_timeout=config["timeout_seconds"]),
        )
        self.live = self.sampler.get_tokenizer()
        self.parity = assert_tokenizer_parity(self.pinned, self.live)
        self.base_model = self.sampler.get_base_model()
        if self.base_model != config["model"]:
            raise ev.EvaluationError("Tinker returned a different base-model identifier.")

    def __call__(self, payload, config, secret):
        if self.sampler is None:
            self.initialize(config, secret)
        rendered, prompt_tokens = render_prompt(payload, config, self.pinned)
        if token_ids(self.live, rendered) != prompt_tokens:
            raise ev.EvaluationError("Live and pinned tokenizers disagree on this complete prompt.")
        if len(prompt_tokens) > config["max_input_tokens"]:
            raise ev.EvaluationError("The exact rendered prompt exceeds the input-token limit.")
        stop_tokens = [token_ids(self.pinned, marker)[0] for marker in ("<|return|>", "<|call|>")]
        params = self.types.SamplingParams(max_tokens=config["max_output_tokens"],
                                           temperature=config["temperature"], seed=config["seed"],
                                           stop=stop_tokens)
        output = self.sampler.sample(prompt=self.types.ModelInput.from_ints(prompt_tokens),
                                     num_samples=1, sampling_params=params).result(timeout=config["timeout_seconds"])
        if len(output.sequences) != 1:
            raise ev.EvaluationError("Tinker returned an unexpected number of sampled sequences.")
        sequence = output.sequences[0]
        tokens = list(sequence.tokens)
        if any(not isinstance(token, int) or isinstance(token, bool) or token < 0 for token in tokens):
            raise ev.EvaluationError("Tinker returned an invalid sampled token sequence.")
        parsed = parse_harmony(tokens, self.pinned, sequence.stop_reason)
        return {
            "model": self.base_model,
            "choices": [{"message": {"role": "assistant", "content": parsed["content"]},
                         "finish_reason": parsed["finish_reason"]}],
            "usage": {"prompt_tokens": len(prompt_tokens), "completion_tokens": len(tokens)},
            "native_tinker": {
                "accounting_source": config["accounting_source"], "accounting_is_invoice": False,
                "prompt_sha256": ev.digest(ev.json_bytes(prompt_tokens)),
                "output_tokens_sha256": ev.digest(ev.json_bytes(tokens)),
                "prompt_cache_hit_tokens": getattr(output, "prompt_cache_hit_tokens", None),
                "analysis_content_tokens": parsed["analysis_content_tokens"],
                "analysis_token_definition": "analysis-channel body tokens only; protocol tokens excluded",
                "provider_stop_reason": parsed["provider_stop_reason"], "parse_issues": parsed["parse_issues"],
                "turn_end_observed": parsed["turn_end_observed"], "tokenizer_parity": self.parity,
                "base_revision": "provider_revision_unpinned", "reasoning_text_retained": False,
                "sdk_internal_submission_retries": "may_occur; count_not_exposed",
            },
        }


def _sampling_worker_loop(connection):
    """Private worker; exceptions cross the pipe only as authored categories."""
    transport = NativeTransport()
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


def sampling_worker(connection):
    # SDK logs can contain provider exception bodies. Only sanitized pipe replies leave
    # this worker; model answers themselves are redacted by the shared journal writer.
    os.environ["TINKER_TELEMETRY"] = "0"
    with open(os.devnull, "w") as sink, contextlib.redirect_stdout(sink), contextlib.redirect_stderr(sink):
        _sampling_worker_loop(connection)


class BoundedNativeTransport:
    """A process deadline covers SDK setup, tokenizers, retries, queues, and sampling."""

    def __init__(self, worker=sampling_worker):
        self.worker = worker
        self.process = self.connection = None
        self.failed = False

    def close(self):
        if self.process is not None:
            if self.process.is_alive():
                self.process.terminate()
                self.process.join(timeout=2)
                if self.process.is_alive():
                    self.process.kill()
                    self.process.join(timeout=2)
            else:
                self.process.join(timeout=0)
            self.process = None
        if self.connection is not None:
            self.connection.close()
            self.connection = None

    def __call__(self, payload, config, secret):
        if self.failed:
            raise ev.EvaluationError("An uncertain native sampling operation cannot be retried automatically.")
        if self.process is None:
            context = multiprocessing.get_context("spawn")
            self.connection, child = context.Pipe()
            self.process = context.Process(target=self.worker, args=(child,), daemon=True)
            self.process.start()
            child.close()
        try:
            # The credential travels through a local pipe, never command-line arguments.
            self.connection.send((payload, config, secret))
            if not self.connection.poll(config["timeout_seconds"]):
                raise TimeoutError("Native sampling exceeded its complete-operation deadline.")
            reply = self.connection.recv()
            if not isinstance(reply, dict) or not reply.get("ok"):
                raise ev.EvaluationError("Native Tinker sampling failed; completion and billing require inspection.")
            return reply["response"]
        except Exception:
            self.failed = True
            self.close()
            raise


def run(config, *, execute=False, resume=False, transport=None):
    config = configure(config)
    native = BoundedNativeTransport() if transport is None else None
    try:
        return ev.run(config, execute=execute, resume=resume, transport=transport or native)
    finally:
        if native is not None:
            native.close()


def parser():
    result = ev.parser()
    result.description = __doc__
    result.set_defaults(base_url=TINKER_URL, api_key_env="TINKER_API_KEY", reasoning_effort="low",
                        max_output_tokens=4096, timeout_seconds=120,
                        run_dir=str(ev.RUNS_ROOT / ("tinker-baseline-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ"))))
    result.add_argument("--temperature", type=float, default=0.0)
    result.add_argument("--seed", type=int, default=20260905)
    result.add_argument("--prompt-date", default=datetime.now(timezone.utc).strftime("%Y-%m-%d"))
    return result


def main(argv=None):
    args = vars(parser().parse_args(argv))
    execute, resume = args.pop("execute"), args.pop("resume")
    try:
        summary = run(args, execute=execute, resume=resume)
    except Exception as exc:
        message = str(exc) if isinstance(exc, ev.EvaluationError) else "Local dependencies or pinned evaluation assets could not be loaded safely."
        print("Evaluation stopped: " + message, file=sys.stderr)
        return 2
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
