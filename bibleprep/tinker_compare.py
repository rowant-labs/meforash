"""Bounded native Tinker comparisons, using pinned model-specific renderers.

This module deliberately leaves the earlier gpt-oss experiment unchanged. ChatML
profiles follow the pinned official HF templates. Inkling uses the official
tml-renderers package, whose native completion prefix differs from its HF one.
"""

from __future__ import annotations

import contextlib
import base64
from datetime import datetime, timezone
import importlib.metadata
import importlib.util
import json
import os
from pathlib import Path
import re
import sys
from types import ModuleType

from bibleprep import evaluate as ev
from bibleprep import tinker_evaluate as te


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "manifests/comparison-models.json"
TOKENIZER_ROOT = ROOT / "data/raw/tokenizers"
COOKBOOK_REVISION = "1f962eda3a2cec8de284725f2adc9978e93dfcd3"
PROFILES = {
    "nvidia/NVIDIA-Nemotron-3.5-Lightning-30B-A3B-BF16": "nemotron3_ultra",
    "nvidia/NVIDIA-Nemotron-3-Ultra-550B-A55B-BF16": "nemotron3_ultra",
    "moonshotai/Kimi-K2.6": "kimi_k26",
    "thinkingmachines/Inkling-Small": "tml_v0",
    "thinkingmachines/Inkling": "tml_v0",
    "Qwen/Qwen3.8-27B": "qwen3_8",
}
EFFORTS = {"nemotron3_ultra": {"on", "off", "medium"},
           "kimi_k26": {"on", "off"},
           "qwen3_8": {"low", "medium", "xhigh", "off"},
           "tml_v0": {"low", "medium", "high"}}
TML_EFFORT = {"low": 0.2, "medium": 0.7, "high": 0.9}
CHAT_MARKERS = ("<|im_start|>", "<|im_end|>", "<think>", "</think>")
KIMI_MARKERS = ("<|im_system|>", "<|im_user|>", "<|im_assistant|>", "<|im_middle|>",
                "<|im_end|>", "<think>", "</think>")
KIMI_TOKENIZER_REVISION = "b5aabbfb20227ed42becbf5541dbffd213942c58"
KIMI_SOURCE_HASHES = {
    "tokenization_kimi.py": "2ab1ffb6f5c4380758bd8d9752ff1041c09024182676a4311528fbdf92fb9599",
    "tool_declaration_ts.py": "97e09ed262f1cd38f87584eaa46c5d4d5b3c9725dd299b21642f389040794ebc",
}
UNICODE_PROBES = te.PARITY_PROBES[:-1]


def manifest_path(value=None):
    if value is None:
        return MANIFEST
    try:
        path = Path(value)
        path = (ROOT / path).resolve() if not path.is_absolute() else path.resolve()
        path.relative_to((ROOT / "manifests").resolve())
        if path.suffix != ".json":
            raise ValueError
        return path
    except (TypeError, ValueError) as exc:
        raise ev.EvaluationError("Comparison manifest must be a JSON file inside project manifests.") from exc


def local_identity(model, comparison_manifest=None):
    """Read only explicitly pinned local assets; no network or environment reads."""
    try:
        raw = manifest_path(comparison_manifest).read_bytes()
        manifest = json.loads(raw)
        entries = [item for item in manifest["models"] if item["id"] == model]
        if manifest.get("schema_version") != 1 or len(entries) != 1:
            raise ValueError
        entry = entries[0]
        profile = PROFILES[model]
        if entry["renderer"] != profile or manifest["cookbook_revision"] != COOKBOOK_REVISION:
            raise ValueError
        if not re.fullmatch(r"[0-9a-f]{40}", entry["revision"]):
            raise ValueError
        slug = entry["slug"]
        if not re.fullmatch(r"[a-zA-Z0-9._-]+", slug) or slug in {".", ".."}:
            raise ValueError
        directory = TOKENIZER_ROOT / slug
        names = set()
        for item in entry["files"]:
            name = item["path"]
            if Path(name).is_absolute() or ".." in Path(name).parts or str(Path(name)) != name or name in names or name in {".", ".."}:
                raise ValueError
            names.add(name)
            if ev.digest((directory / name).read_bytes()) != item["sha256"]:
                raise ValueError
        required = {"tokenizer_config.json", "chat_template.jinja"}
        if profile == "kimi_k26":
            required |= {"tiktoken.model", "tokenization_kimi.py", "tool_declaration_ts.py"}
            if entry["revision"] != KIMI_TOKENIZER_REVISION:
                raise ValueError
        else:
            required.add("tokenizer.json")
        if not required <= names:
            raise ValueError
        # from_pretrained must not silently consult an unpinned extra asset.
        if {str(path.relative_to(directory)) for path in directory.rglob("*") if path.is_file()} != names:
            raise ValueError
    except (OSError, ValueError, TypeError, KeyError) as exc:
        raise ev.EvaluationError("Comparison model assets or manifest failed local validation.") from exc
    return entry, {
        "comparison_manifest_sha256": ev.digest(raw),
        "tokenizer_revision": entry["revision"],
        "tokenizer_sha256": next(item["sha256"] for item in entry["files"]
                                 if item["path"] == ("tiktoken.model" if profile == "kimi_k26" else "tokenizer.json")),
        "chat_template_sha256": next(item["sha256"] for item in entry["files"] if item["path"] == "chat_template.jinja"),
        "renderer_profile": profile, "renderer_reference_revision": COOKBOOK_REVISION,
    }, manifest.get("runtime_packages", {})


def package_identity(package, expected):
    """Fingerprint installed official renderer assets without recording local paths."""
    try:
        distribution = importlib.metadata.distribution(package)
        if distribution.version != expected:
            raise ValueError
        files = {}
        for relative in distribution.files or ():
            name = str(relative)
            if name.endswith((".py", ".pyi", ".so", ".tiktoken")) and ".." not in relative.parts:
                files[name] = ev.digest(distribution.locate_file(relative).read_bytes())
        if not files:
            raise ValueError
    except (OSError, ValueError, importlib.metadata.PackageNotFoundError) as exc:
        raise ev.EvaluationError("The pinned native renderer runtime is not installed.") from exc
    return {"version": distribution.version, "files_sha256": ev.digest(ev.json_bytes(files))}


def configure(config):
    config = dict(config)
    if config.get("comparison_manifest") is None:
        config.pop("comparison_manifest", None)
    else:
        config["comparison_manifest"] = str(manifest_path(config["comparison_manifest"]).relative_to(ROOT))
    if config.get("model") not in PROFILES:
        raise ev.EvaluationError("This comparison runner only supports its verified model profiles.")
    if config.get("base_url", "").rstrip("/") != te.TINKER_URL:
        raise ev.EvaluationError("Native comparison requires the official Tinker endpoint.")
    entry, identity, runtime = local_identity(config["model"], config.get("comparison_manifest"))
    profile = identity["renderer_profile"]
    effort = config.get("reasoning_effort") or entry["thinking_settings"]["default"]
    if effort not in EFFORTS[profile] or effort not in entry["thinking_settings"]["supported"]:
        raise ev.EvaluationError("The selected model does not support that reasoning setting.")
    if not ev.finite_nonnegative(config.get("temperature")) or config["temperature"] > 2:
        raise ev.EvaluationError("Temperature must be a finite number between zero and two.")
    if not isinstance(config.get("seed"), int) or isinstance(config["seed"], bool) or not 0 <= config["seed"] < 2**31:
        raise ev.EvaluationError("Seed must be a nonnegative 31-bit integer.")
    config.update(identity)
    config.update({"reasoning_effort": effort, "transport": "native_tinker_comparison",
                   "renderer": "official_tml_renderers" if profile == "tml_v0" else "pinned_official_hf_chat_template",
                   "reasoning_settings_are_cross_model_equivalent": False,
                   "accounting_source": "submitted_prompt_and_returned_sequence_token_counts",
                   "accounting_is_invoice": False, "application_sampling_retries": False,
                   "sdk_internal_submission_retries": "may_occur; count_not_exposed",
                   "request_deadline": "worker_process_terminated_on_timeout"})
    for package in ("tinker", "transformers", "tokenizers", "jinja2"):
        try:
            config[package + "_version"] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            config[package + "_version"] = "not_installed"
    if profile == "tml_v0":
        if runtime.get("tml-renderers") != "0.1.0" or not runtime.get("torch"):
            raise ev.EvaluationError("The manifest must pin the official TML runtime versions.")
        config["native_renderer_packages"] = {
            "tml-renderers": package_identity("tml-renderers", runtime["tml-renderers"])
        }
        if importlib.metadata.version("torch") != runtime["torch"]:
            raise ev.EvaluationError("The installed torch version differs from the TML runtime pin.")
        config["torch_version"] = runtime["torch"]
        config["thinking_effort_numeric"] = TML_EFFORT[effort]
        config["hf_chat_template_used"] = False
    if profile == "kimi_k26":
        if not runtime.get("tiktoken"):
            raise ev.EvaluationError("The manifest must pin the Kimi tokenizer runtime version.")
        config["native_tokenizer_packages"] = {"tiktoken": package_identity("tiktoken", runtime["tiktoken"])}
        config["custom_tokenizer_code_sha256"] = {
            item["path"]: item["sha256"] for item in entry["files"] if item["path"].endswith(".py")}
        config["tokenizer_loading"] = "hash_verified_local_python_modules_and_local_vocab; no_remote_code_loader"
        config["tokenizer_vocab_loading"] = "verified_local_bytes; bypass_tiktoken_cache"
    return config


def load_pinned_tokenizer(model, comparison_manifest=None):
    from transformers import PreTrainedTokenizerFast
    entry, _, _ = local_identity(model, comparison_manifest)
    if entry["renderer"] == "kimi_k26":
        # The official cookbook loads Kimi's class directly because AutoTokenizer
        # can select an incompatible backend. Execute only locally checked files,
        # with an empty package search path and its sole relative import preloaded.
        directory = TOKENIZER_ROOT / entry["slug"]
        module_hashes = {item["path"]: item["sha256"] for item in entry["files"] if item["path"].endswith(".py")}
        if module_hashes != KIMI_SOURCE_HASHES:
            raise ev.EvaluationError("The Kimi tokenizer must contain exactly its two reviewed Python module hashes.")
        package_name = "_bibleprep_kimi_" + ev.digest(ev.json_bytes(module_hashes))
        if package_name not in sys.modules:
            package = ModuleType(package_name)
            package.__path__ = []
            sys.modules[package_name] = package
            previous_bytecode_setting = sys.dont_write_bytecode
            try:
                sys.dont_write_bytecode = True
                for name in ("tool_declaration_ts", "tokenization_kimi"):
                    spec = importlib.util.spec_from_file_location(package_name + "." + name, directory / (name + ".py"))
                    module = importlib.util.module_from_spec(spec)
                    sys.modules[spec.name] = module
                    spec.loader.exec_module(module)
            except Exception:
                for name in (package_name, package_name + ".tool_declaration_ts", package_name + ".tokenization_kimi"):
                    sys.modules.pop(name, None)
                raise
            finally:
                sys.dont_write_bytecode = previous_bytecode_setting
        module = sys.modules[package_name + ".tokenization_kimi"]
        expected_vocab_hash = next(item["sha256"] for item in entry["files"] if item["path"] == "tiktoken.model")

        def verified_local_ranks(path):
            if Path(path).resolve() != (directory / "tiktoken.model").resolve():
                raise ev.EvaluationError("The custom tokenizer requested an unpinned vocabulary.")
            data = Path(path).read_bytes()
            if ev.digest(data) != expected_vocab_hash:
                raise ev.EvaluationError("The custom tokenizer vocabulary failed its checksum.")
            ranks = TmlProfile._ranks(data)
            if set(ranks.values()) != set(range(len(ranks))):
                raise ev.EvaluationError("The custom tokenizer vocabulary has invalid token IDs.")
            return ranks

        # Upstream load_tiktoken_bpe can read an unrelated cached file without a
        # content hash. Supply the same parsed ranks from verified local bytes.
        module.load_tiktoken_bpe = verified_local_ranks
        cls = module.TikTokenTokenizer
        return cls.from_pretrained(directory, local_files_only=True)
    return PreTrainedTokenizerFast.from_pretrained(TOKENIZER_ROOT / entry["slug"], local_files_only=True)


def assert_hf_parity(pinned, live, *, markers=CHAT_MARKERS):
    if pinned.get_vocab() != live.get_vocab():
        raise ev.EvaluationError("Provider and pinned tokenizer vocabularies differ.")
    if any(te.token_ids(pinned, text) != te.token_ids(live, text) for text in UNICODE_PROBES):
        raise ev.EvaluationError("Provider and pinned Unicode tokenization differ.")
    for marker in markers:
        ids = te.token_ids(pinned, marker)
        if len(ids) != 1 or pinned.decode(ids, skip_special_tokens=False) != marker:
            raise ev.EvaluationError("A required chat marker is not a single verified token.")
    return {"vocabulary_sha256": te.vocabulary_hash(pinned), "unicode_probes_passed": len(UNICODE_PROBES),
            "all_prompt_token_ids_compared": True}


def assert_kimi_parity(pinned):
    """Verify the official HF facade against its underlying native encoding.

    The immutable SDK/cookbook reference is verified locally. Neither this
    comparison nor a client-side tokenizer accessor observes server tokenization.
    """
    native_vocab = {
        "".join(pinned.byte_encoder[byte] for byte in pinned.model.decode_single_token_bytes(identifier)): identifier
        for identifier in range(pinned.model.n_vocab)
    }
    if native_vocab != pinned.get_vocab():
        raise ev.EvaluationError("The Kimi HF facade and native vocabulary differ.")
    for text in (*UNICODE_PROBES, *KIMI_MARKERS):
        if te.token_ids(pinned, text) != pinned.model.encode(text, allowed_special="all"):
            raise ev.EvaluationError("The Kimi HF facade and native Unicode tokenization differ.")
    for marker in KIMI_MARKERS:
        ids = te.token_ids(pinned, marker)
        if len(ids) != 1 or pinned.decode(ids, skip_special_tokens=False) != marker:
            raise ev.EvaluationError("A required Kimi chat marker is not a single verified token.")
    return {"vocabulary_sha256": te.vocabulary_hash(pinned), "vocabulary_entries": len(native_vocab),
            "local_unicode_probes_passed": len(UNICODE_PROBES), "all_prompt_token_ids_compared": False,
            "all_prompt_native_vs_facade_token_ids_compared": True, "independent_tokenizer_compared": False,
            "comparison": "pinned_official_custom_tokenizer_local_sanity; native_encoding_vs_its_hf_facade",
            "live_sdk_tokenizer_compared": False, "tokenizer_revision": KIMI_TOKENIZER_REVISION,
            "sdk_tokenizer_accessor": "not_used; official_cookbook_requires_direct_custom_class"}


def checked_messages(payload):
    messages = payload.get("messages")
    if not isinstance(messages, list) or len(messages) != 2:
        raise ev.EvaluationError("Comparison prompts must contain one policy and one user message.")
    if [message.get("role") for message in messages] != ["system", "user"]:
        raise ev.EvaluationError("Comparison prompt roles do not match the baseline.")
    if any(not isinstance(message.get("content"), str) for message in messages):
        raise ev.EvaluationError("Comparison prompts must contain plain text.")
    return [{"role": message["role"], "content": message["content"]} for message in messages]


def render_hf_prompt(payload, config, tokenizer):
    messages = checked_messages(payload)
    profile = config["renderer_profile"]
    effort = config["reasoning_effort"]
    kwargs = {"enable_thinking": effort != "off"}
    if profile == "kimi_k26":
        kwargs = {"thinking": effort != "off", "preserve_thinking": False}
    if profile == "nemotron3_ultra" and effort == "medium":
        kwargs["medium_effort"] = True
    if profile == "qwen3_8":
        kwargs.update(reasoning_effort="medium" if effort == "off" else effort, preserve_thinking=True)
    rendered = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True, **kwargs)
    if profile == "kimi_k26":
        suffix = "<|im_assistant|>assistant<|im_middle|><think>" + ("</think>" if effort == "off" else "")
    else:
        suffix = "<|im_start|>assistant\n" + ("<think>\n" if effort != "off" else (
            "<think></think>" if profile == "nemotron3_ultra" else "<think>\n\n</think>\n\n"))
    if not rendered.endswith(suffix):
        raise ev.EvaluationError("The official template's generation prefix changed.")
    for message in messages:
        if message["content"].strip() not in rendered:
            raise ev.EvaluationError("A baseline message was not preserved by the official template.")
    return rendered, te.token_ids(tokenizer, rendered)


def parse_chatml(tokens, tokenizer, provider_stop, *, thinking, marker_names=CHAT_MARKERS):
    """Read only the post-thinking answer, requiring the native turn terminator."""
    markers = {name: te.token_ids(tokenizer, name)[0] for name in marker_names}
    end = markers["<|im_end|>"]
    ids = list(tokens)
    issues = []
    saw_end = end in ids
    if saw_end:
        boundary = ids.index(end)
        if boundary != len(ids) - 1:
            issues.append("tokens_after_turn_end")
        ids = ids[:boundary]
    analysis_count = 0
    if thinking:
        close = markers["</think>"]
        if close not in ids:
            return {"content": "", "finish_reason": "length" if provider_stop == "length" else "incomplete_chat_format",
                    "analysis_content_tokens": len(ids), "parse_issues": ["thinking_did_not_close"],
                    "provider_stop_reason": provider_stop, "turn_end_observed": saw_end}
        boundary = ids.index(close)
        analysis_count = boundary
        ids = ids[boundary + 1:]
    if any(marker in ids for marker in markers.values()):
        # Malformed framing could otherwise expose a new thinking block.
        issues.append("unexpected_chat_marker_in_final")
        content = ""
    else:
        content = tokenizer.decode(ids, skip_special_tokens=False).strip()
    if "<tool_call>" in content or "<|tool_call" in content or "<|media_" in content:
        issues.append("unexpected_tool_call")
        content = ""
    if provider_stop == "length":
        finish = "length"
    elif provider_stop == "stop" and saw_end and content and not issues:
        finish = "stop"
    else:
        finish = "incomplete_chat_format"
    return {"content": content, "finish_reason": finish, "analysis_content_tokens": analysis_count,
            "parse_issues": issues, "provider_stop_reason": provider_stop, "turn_end_observed": saw_end}


class TmlProfile:
    """Official native TML renderer with pinned HF vocabulary cross-checks.

    SDK 0.27.1's Inkling tokenizer accessor imports an unpublished package. This
    deliberately records a native-package/HF comparison, not live-SDK parity.
    """

    def __init__(self, pinned, model, comparison_manifest=None):
        from importlib.resources import files
        from tml_renderers import chat, tokenizers, v0
        entry, _, _ = local_identity(model, comparison_manifest)
        bundled = files("tml_renderers").joinpath("data/o200k_base.tiktoken")
        if not bundled.is_file():
            # The development package can fall back to network downloads; refuse it.
            raise ev.EvaluationError("The official native tokenizer must have bundled local vocabulary assets.")
        self.native = tokenizers.o200k_base_chat()
        self.renderer = v0.Renderer(self.native)
        self.chat = chat
        self.parse_error = v0.ParseError
        self.pinned = pinned
        self.stop_tokens = list(self.renderer.stop())
        native_vocab = self._ranks(bundled.read_bytes())
        for name in self.native.special_tokens():
            marker = "<|" + name + "|>"
            native_vocab[marker.encode("utf-8")] = self.native.encode_special(name)
        hf_vocab = self._ranks((TOKENIZER_ROOT / entry["slug"] / "tiktoken/tokenizer.model").read_bytes())
        if native_vocab != hf_vocab:
            raise ev.EvaluationError("Official native and pinned HF token vocabularies differ.")
        canonical = sorted((base64.b64encode(raw).decode("ascii"), identifier) for raw, identifier in native_vocab.items())
        vocabulary_hash = ev.digest(json.dumps(canonical, separators=(",", ":")).encode())
        if vocabulary_hash != entry["native_tokenizer"]["canonical_vocabulary_sha256"]:
            raise ev.EvaluationError("The native TML vocabulary differs from the pinned canonical hash.")
        if any(list(self.native.encode_ordinary(text)) != te.token_ids(pinned, text) for text in UNICODE_PROBES):
            raise ev.EvaluationError("Official native and pinned HF Unicode tokenization differ.")
        for name in self.native.special_tokens():
            marker = "<|" + name + "|>"
            if te.token_ids(pinned, marker) != [self.native.encode_special(name)]:
                raise ev.EvaluationError("An official TML special token differs from the pinned HF tokenizer.")
        if self.stop_tokens != [self.native.encode_special("content_model_end_sampling")]:
            raise ev.EvaluationError("The native TML turn-end protocol changed.")
        self.parity = {"vocabulary_sha256": vocabulary_hash, "vocabulary_entries": len(native_vocab),
                       "unicode_probes_passed": len(UNICODE_PROBES), "all_prompt_token_ids_compared": True,
                       "comparison": "official_native_tml_package_vs_pinned_hf_assets",
                       "live_sdk_tokenizer_compared": False,
                       "sdk_tokenizer_accessor": "not_used; version_0.27.1_requires_unpublished_package"}

    @staticmethod
    def _ranks(data):
        ranks = {}
        for line in data.splitlines():
            token, identifier = line.split()
            raw = base64.b64decode(token, validate=True)
            if raw in ranks:
                raise ev.EvaluationError("A native tokenizer vocabulary has duplicate entries.")
            ranks[raw] = int(identifier)
        return ranks

    def render(self, payload, config):
        messages = self.chat.OpenAIMessage.from_oss_messages(checked_messages(payload))
        spans, parser = self.renderer.render_for_completion_with_effort(messages, TML_EFFORT[config["reasoning_effort"]])
        prompt_tokens = []
        for span in spans:
            if not isinstance(span.span, self.chat.EncodedTextTokenSpan):
                raise ev.EvaluationError("The text comparison unexpectedly produced nontext input.")
            prompt_tokens.extend(span.span.tokens)
        # The native renderer owns protocol tokens; HF is an independent encoding
        # check, never a replacement for native prompt framing.
        rendered = self.native.decode(prompt_tokens)
        if te.token_ids(self.pinned, rendered) != prompt_tokens:
            raise ev.EvaluationError("Native and pinned HF tokenizers differ on this complete TML prompt.")
        if not rendered.endswith("<|end_message|>") or rendered.endswith("<|message_model|>"):
            raise ev.EvaluationError("The native TML generation boundary changed.")
        return prompt_tokens, parser

    def parse(self, tokens, parser, provider_stop):
        result = {"content": "", "finish_reason": "length" if provider_stop == "length" else "incomplete_tml",
                  "analysis_content_tokens": None, "parse_issues": [],
                  "provider_stop_reason": provider_stop, "turn_end_observed": False}
        try:
            messages = parser.parse_tokens(tokens)
        except self.parse_error:
            result["parse_issues"] = ["native_tml_parse_error"]
            return result
        texts = []
        for index, message in enumerate(messages):
            if message.author.kind != self.chat.AuthorKind.Model:
                result["parse_issues"].append("unexpected_tml_author")
                continue
            if isinstance(message.content, self.chat.ModelEndSampling):
                result["turn_end_observed"] = True
                if index != len(messages) - 1:
                    result["parse_issues"].append("messages_after_turn_end")
            elif isinstance(message.content, self.chat.Thinking):
                if texts:
                    result["parse_issues"].append("thinking_after_final_text")
            elif isinstance(message.content, self.chat.Text):
                texts.append(message.content.text)
            else:
                result["parse_issues"].append("unexpected_tml_content")
        if not tokens or tokens[-1] not in self.stop_tokens:
            result["turn_end_observed"] = False
        # Native parsing does not expose original token offsets for each content
        # part. Leave the reasoning subtotal unavailable; total usage is exact.
        result["analysis_content_tokens"] = None
        if not result["parse_issues"]:
            result["content"] = "\n".join(texts)
        if provider_stop == "stop" and result["turn_end_observed"] and result["content"].strip() and not result["parse_issues"]:
            result["finish_reason"] = "stop"
        return result


class NativeComparisonTransport:
    """Pure base-model sampling; no training clients or adapters are created."""

    def __init__(self):
        self.sampler = None

    def initialize(self, config, secret):
        from bibleprep.tinker_access import check_access
        if check_access(secret, timeout_seconds=min(20, config["timeout_seconds"])).get("status") != "ready":
            raise ev.EvaluationError("Tinker account access is not ready.")
        import tinker
        from tinker.lib.retry_handler import RetryConfig
        self.types = tinker.types
        self.pinned = load_pinned_tokenizer(config["model"], config.get("comparison_manifest"))
        self.service = tinker.ServiceClient(api_key=secret, base_url=te.TINKER_URL,
                                            max_retries=0, timeout=config["timeout_seconds"])
        self.sampler = self.service.create_sampling_client(
            base_model=config["model"],
            retry_config=RetryConfig(enable_retry_logic=False, progress_timeout=config["timeout_seconds"]))
        self.base_model = self.sampler.get_base_model()
        if self.base_model != config["model"]:
            raise ev.EvaluationError("Tinker returned a different base model.")
        if config["renderer_profile"] == "tml_v0":
            self.tml = TmlProfile(self.pinned, config["model"], config.get("comparison_manifest"))
            self.parity = self.tml.parity
        elif config["renderer_profile"] == "kimi_k26":
            # SDK 0.27.1 names this same immutable tokenizer revision, but its
            # AutoTokenizer accessor is incompatible with this Transformers path.
            # Do not label a local asset check as live provider-tokenizer parity.
            self.live = self.pinned
            self.parity = assert_kimi_parity(self.pinned)
        else:
            self.live = self.sampler.get_tokenizer()
            self.parity = assert_hf_parity(self.pinned, self.live)

    def __call__(self, payload, config, secret):
        if self.sampler is None:
            self.initialize(config, secret)
        if config["renderer_profile"] == "tml_v0":
            prompt_tokens, parser = self.tml.render(payload, config)
            stop_tokens = self.tml.stop_tokens
        else:
            rendered, prompt_tokens = render_hf_prompt(payload, config, self.pinned)
            reference_tokens = (self.pinned.model.encode(rendered, allowed_special="all")
                                if config["renderer_profile"] == "kimi_k26" else te.token_ids(self.live, rendered))
            if reference_tokens != prompt_tokens:
                raise ev.EvaluationError("The tokenizer comparison differs on this complete prompt.")
            stop_tokens = [te.token_ids(self.pinned, "<|im_end|>")[0]]
        if len(prompt_tokens) > config["max_input_tokens"]:
            raise ev.EvaluationError("The exact rendered prompt exceeds the input limit.")
        params = self.types.SamplingParams(max_tokens=config["max_output_tokens"], temperature=config["temperature"],
                                           seed=config["seed"], stop=stop_tokens)
        output = self.sampler.sample(prompt=self.types.ModelInput.from_ints(prompt_tokens), num_samples=1,
                                     sampling_params=params).result(timeout=config["timeout_seconds"])
        if len(output.sequences) != 1:
            raise ev.EvaluationError("Tinker returned an unexpected sampled sequence count.")
        sequence = output.sequences[0]
        tokens = list(sequence.tokens)
        if any(not isinstance(token, int) or isinstance(token, bool) or token < 0 for token in tokens):
            raise ev.EvaluationError("Tinker returned invalid sampled tokens.")
        parsed = (self.tml.parse(tokens, parser, sequence.stop_reason) if config["renderer_profile"] == "tml_v0"
                  else parse_chatml(tokens, self.pinned, sequence.stop_reason, thinking=config["reasoning_effort"] != "off",
                                    marker_names=KIMI_MARKERS if config["renderer_profile"] == "kimi_k26" else CHAT_MARKERS))
        return {"model": self.base_model,
                "choices": [{"message": {"role": "assistant", "content": parsed["content"]},
                             "finish_reason": parsed["finish_reason"]}],
                "usage": {"prompt_tokens": len(prompt_tokens), "completion_tokens": len(tokens)},
                "native_tinker": {
                    "accounting_source": config["accounting_source"], "accounting_is_invoice": False,
                    "prompt_sha256": ev.digest(ev.json_bytes(prompt_tokens)),
                    "output_tokens_sha256": ev.digest(ev.json_bytes(tokens)),
                    "prompt_cache_hit_tokens": getattr(output, "prompt_cache_hit_tokens", None),
                    "analysis_content_tokens": parsed["analysis_content_tokens"],
                    "analysis_token_definition": "generated pre-final tokens for ChatML; unavailable for native TML; all generated tokens counted in usage",
                    "provider_stop_reason": parsed["provider_stop_reason"], "parse_issues": parsed["parse_issues"],
                    "turn_end_observed": parsed["turn_end_observed"], "tokenizer_parity": self.parity,
                    "base_revision": "provider_revision_unpinned", "reasoning_text_retained": False,
                    "sdk_internal_submission_retries": "may_occur; count_not_exposed"}}


def sampling_worker(connection):
    os.environ["TINKER_TELEMETRY"] = "0"
    with open(os.devnull, "w") as sink, contextlib.redirect_stdout(sink), contextlib.redirect_stderr(sink):
        transport = NativeComparisonTransport()
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


def run(config, *, execute=False, resume=False, transport=None):
    config = configure(config)
    native = te.BoundedNativeTransport(worker=sampling_worker) if transport is None else None
    try:
        return ev.run(config, execute=execute, resume=resume, transport=transport or native)
    finally:
        if native is not None:
            native.close()


def parser():
    result = ev.parser()
    result.description = __doc__
    for action in result._actions:
        if action.dest == "reasoning_effort":
            action.choices = ("on", "off", "low", "medium", "high", "xhigh")
    result.set_defaults(model="nvidia/NVIDIA-Nemotron-3.5-Lightning-30B-A3B-BF16",
                        base_url=te.TINKER_URL, api_key_env="TINKER_API_KEY", reasoning_effort=None,
                        max_output_tokens=4096, timeout_seconds=180, max_cases=16, evidence_mode="provided",
                        run_dir=str(ev.RUNS_ROOT / ("tinker-comparison-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ"))))
    result.add_argument("--temperature", type=float, default=0.0)
    result.add_argument("--seed", type=int, default=20260905)
    result.add_argument("--comparison-manifest", default=None)
    return result


def main(argv=None):
    args = vars(parser().parse_args(argv))
    execute, resume = args.pop("execute"), args.pop("resume")
    try:
        summary = run(args, execute=execute, resume=resume)
    except Exception as exc:
        message = str(exc) if isinstance(exc, ev.EvaluationError) else "Comparison dependencies or local assets could not be loaded safely."
        print("Comparison stopped: " + message, file=sys.stderr)
        return 2
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
