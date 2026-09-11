"""Versioned private native-output diagnostics; no calls or writes on import.

Uses the pinned official streaming parser, never a decoded-text fallback. Raw
IDs and all thinking text belong only in mode-0600 private run sidecars. Only
``public_summary`` is suitable for copying into a shareable report.
"""
from __future__ import annotations

import contextlib
import json
import os
from pathlib import Path
import re
import uuid

from bibleprep import evaluate as ev
from bibleprep import evaluate_adapter as adapter
from bibleprep import tinker_compare as comparison
from bibleprep import tinker_evaluate as native

SCHEMA_VERSION = 1
MODEL = "thinkingmachines/Inkling"
PRIVATE_DIRECTORY = "native-diagnostics-v1"
MAX_RETAINED_TOKENS = 65536
ISSUES = frozenset({
    "native_tml_parse_error", "unknown_native_token_id", "tokens_after_turn_end",
    "multiple_turn_ends", "unclosed_header_before_new_message", "stream_without_header",
    "stream_content_type_changed", "stream_completed_content_mismatch",
})
WARNINGS = frozenset({
    "unexpected_tml_author", "unsupported_tml_channel", "unsupported_tml_content",
    "thinking_after_final_text",
    "noncanonical_native_boundaries", "unexpected_special_token_in_content",
})


def token_ids_sha256(tokens):
    """Same canonical UTF-8 JSON-array hash as the frozen native transport."""
    if not isinstance(tokens, list) or len(tokens) > MAX_RETAINED_TOKENS or any(
        not isinstance(t, int) or isinstance(t, bool) or not 0 <= t < 2**32 for t in tokens
    ):
        raise ev.EvaluationError("Invalid or excessively large native token sequence.")
    return ev.digest(ev.json_bytes(tokens))


def parse_generated(profile, payload, config, tokens, provider_stop):
    """Return PRIVATE completed/unfinished typed content and structural facts.

    ``completed_final_text`` is formed only from completed native Text messages.
    ``partial_final_text`` comes only from unfinished streaming Text deltas.
    Thinking remains distinct even if no complete final answer was extracted.
    Semantic quality/completeness is deliberately not inferred from any marker.
    """
    output_hash = token_ids_sha256(tokens)
    _, parser = profile.render(payload, config)
    chat = profile.chat
    completed = {"final": [], "thinking": []}
    current = None
    issues = []
    warnings = []
    parsed_tokens = 0
    end_messages = 0
    failed = False
    final_started = False

    def issue(code):
        if code not in issues:
            issues.append(code)

    def warn(code):
        if code not in warnings:
            warnings.append(code)

    # The official parser intentionally accepts some noncanonical tokens as
    # literal text or ignores unframed tokens. Record diagnostic warnings, not
    # new parse failures: official typed messages own content and validity.
    marker = profile.native.encode_special
    special_ids = {marker(name) for name in profile.native.special_tokens()}
    valid_ids = set(profile.pinned.get_vocab().values())
    if any(token not in valid_ids for token in tokens):
        issue("unknown_native_token_id")
    state = "boundary"
    open_content_kind = None
    for token in tokens:
        if state == "boundary":
            if token == marker("message_model"):
                state = "type"
            elif token == marker("content_model_end_sampling"):
                state = "ended"
            else:
                warn("noncanonical_native_boundaries")
        elif state == "type":
            if token in (marker("content_text"), marker("content_thinking")):
                state = "body"
                open_content_kind = "final" if token == marker("content_text") else "thinking"
            elif token in special_ids:
                warn("noncanonical_native_boundaries")
            # Ordinary tokens before the content marker can encode a model
            # author name; the official serializer emits this valid header.
        elif state == "body":
            if token == marker("end_message"):
                state = "boundary"
                open_content_kind = None
            elif token in special_ids:
                warn("unexpected_special_token_in_content")
        else:
            warn("noncanonical_native_boundaries")

    def check_header(author, channel):
        if author.kind != chat.AuthorKind.Model:
            warn("unexpected_tml_author")
        if channel not in (None, chat.MessageChannel.Main, chat.MessageChannel.Final, chat.MessageChannel.Analysis):
            warn("unsupported_tml_channel")

    def kind(content, channel=None):
        if isinstance(content, chat.Thinking) or (isinstance(content, chat.Text) and channel == chat.MessageChannel.Analysis):
            return "thinking"
        if isinstance(content, chat.Text) and channel in (None, chat.MessageChannel.Main, chat.MessageChannel.Final):
            return "final"
        return None

    def consume(updates):
        nonlocal current, end_messages, final_started
        for item in updates:
            update = item.update
            if isinstance(update, chat.StreamingMessageHeader):
                if current is not None:
                    issue("unclosed_header_before_new_message")
                check_header(update.author, update.channel)
                current = {"streams": {}, "model_author": update.author.kind == chat.AuthorKind.Model,
                           "channel": update.channel}
            elif isinstance(update, chat.StreamingContent):
                if current is None:
                    issue("stream_without_header")
                    continue
                content_kind = kind(update.content, current["channel"])
                if content_kind is None:
                    warn("unsupported_tml_content")
                    continue
                if content_kind == "thinking" and final_started:
                    warn("thinking_after_final_text")
                if content_kind == "final":
                    final_started = True
                stream = current["streams"].setdefault(update.content_index, {"kind": content_kind, "chunks": []})
                if stream["kind"] != content_kind:
                    issue("stream_content_type_changed")
                stream["chunks"].append(update.content.text)
            elif isinstance(update, chat.Message):
                check_header(update.author, update.channel_enum)
                if isinstance(update.content, chat.ModelEndSampling):
                    end_messages += 1
                    continue
                content_kind = kind(update.content, update.channel_enum)
                if content_kind is None:
                    warn("unsupported_tml_content")
                    current = None
                    continue
                if content_kind == "thinking" and final_started:
                    warn("thinking_after_final_text")
                if current is not None:
                    streams = current["streams"]
                    streamed = "".join("".join(s["chunks"]) for _, s in sorted(streams.items()))
                    if streamed != update.content.text or any(s["kind"] != content_kind for s in streams.values()):
                        issue("stream_completed_content_mismatch")
                if update.author.kind == chat.AuthorKind.Model:
                    completed[content_kind].append(update.content.text)
                if content_kind == "final":
                    final_started = True
                current = None
            else:
                warn("unsupported_tml_content")

    # Incremental calls preserve previously parsed deltas if a later token is
    # malformed. Exception strings can contain content and are never retained.
    for token in tokens:
        try:
            consume(parser.parse_token(token))
            parsed_tokens += 1
        except profile.parse_error:
            failed = True
            issue("native_tml_parse_error")
            break
    if not failed:
        try:
            consume(parser.flush_updates())
        except profile.parse_error:
            failed = True
            issue("native_tml_parse_error")
    boundary = bool(parser.is_at_message_boundary()) if not failed else False
    partial = {"final": [], "thinking": []}
    open_kinds = set()
    if state == "body" and open_content_kind:
        open_kinds.add(open_content_kind)
    if current is not None and current["model_author"]:
        for _, stream in sorted(current["streams"].items()):
            open_kinds.add(stream["kind"])
            partial[stream["kind"]].append("".join(stream["chunks"]))
    stop_token = profile.stop_tokens[0]
    stop_positions = [i for i, token in enumerate(tokens) if token == stop_token]
    if len(stop_positions) > 1:
        issue("multiple_turn_ends")
    if stop_positions and stop_positions[0] != len(tokens) - 1:
        issue("tokens_after_turn_end")
    turn_end = bool(end_messages and tokens and tokens[-1] == stop_token)
    native_complete = turn_end and boundary and not issues
    provider_stop = provider_stop if provider_stop in {"stop", "length"} else "unknown"
    final_text = "\n".join(completed["final"])
    partial_final = "\n".join(partial["final"])
    thinking_text = "\n".join(completed["thinking"])
    partial_thinking = "\n".join(partial["thinking"])
    finish = "length" if provider_stop == "length" else "incomplete_tml"
    if native_complete and provider_stop == "stop" and final_text.strip():
        finish = "stop"

    def partial_status(content_kind, text):
        if text:
            return "present_before_parse_error" if failed else "present"
        if failed:
            return "unknown_due_to_parse_error"
        if issues:
            return "unknown_due_to_format_error"
        if content_kind in open_kinds:
            return "empty_open_content"
        return "absent"

    framing_header_open = state in {"type", "body"}
    state = ("completed_and_partial" if final_text and partial_final else
             "completed_messages_only" if final_text else "partial_only" if partial_final else
             "unknown_due_to_parse_error" if failed else "unknown_due_to_format_error" if issues else "absent")
    return {
        "schema_version": SCHEMA_VERSION, "parser_profile": "official_tml_streaming_v1",
        "raw_generated_token_ids": list(tokens), "raw_generated_token_ids_sha256": output_hash,
        "raw_id_hash_encoding": "sha256(UTF-8 json.dumps(ids, ensure_ascii=False, sort_keys=True))",
        "generated_token_count": len(tokens), "parsed_token_count": parsed_tokens,
        "completed_final_text": final_text, "partial_final_text": partial_final,
        "completed_thinking_text": thinking_text, "partial_thinking_text": partial_thinking,
        "completed_final_message_count": len(completed["final"]),
        "completed_thinking_message_count": len(completed["thinking"]),
        "completed_final_characters": len(final_text), "partial_final_characters": len(partial_final),
        "completed_thinking_characters": len(thinking_text), "partial_thinking_characters": len(partial_thinking),
        "partial_final_status": partial_status("final", partial_final),
        "partial_thinking_status": partial_status("thinking", partial_thinking),
        "final_content_state": state, "header_open": current is not None or (not boundary and framing_header_open),
        "parser_at_message_boundary": boundary, "stream_extraction_finished_without_error": not failed,
        "turn_end_token_present": bool(stop_positions), "turn_end_observed": turn_end,
        "native_turn_complete": native_complete, "provider_stop_reason": provider_stop,
        "finish_reason": finish, "parse_issues": issues, "diagnostic_warnings": warnings,
        "semantic_answer_completeness": "not_assessed",
        # Neither raw structure nor output-token totals establish language or
        # repeated reasoning. No speculative diagnoses are included.
        "analysis_content_tokens": None,
    }


def public_summary(diagnostic, *, raw_ids_retained=False):
    """Allowlist numeric/boolean/status fields; never copy strings of content."""
    result = {"schema_version": SCHEMA_VERSION, "parser_profile": "official_tml_streaming_v1",
              "semantic_answer_completeness": "not_assessed", "raw_generated_token_ids_retained": bool(raw_ids_retained),
              "analysis_content_tokens": None}
    numbers = ("generated_token_count", "parsed_token_count", "completed_final_message_count",
               "completed_thinking_message_count", "completed_final_characters", "partial_final_characters",
               "completed_thinking_characters", "partial_thinking_characters")
    booleans = ("header_open", "parser_at_message_boundary", "stream_extraction_finished_without_error",
                "turn_end_token_present", "turn_end_observed", "native_turn_complete")
    statuses = {
        "provider_stop_reason": {"stop", "length", "unknown"},
        "finish_reason": {"stop", "length", "incomplete_tml"},
        "partial_final_status": {"present", "present_before_parse_error", "unknown_due_to_parse_error", "unknown_due_to_format_error", "empty_open_content", "absent"},
        "partial_thinking_status": {"present", "present_before_parse_error", "unknown_due_to_parse_error", "unknown_due_to_format_error", "empty_open_content", "absent"},
        "final_content_state": {"completed_and_partial", "completed_messages_only", "partial_only", "unknown_due_to_parse_error", "unknown_due_to_format_error", "absent"},
    }
    for key in numbers:
        value = diagnostic.get(key)
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            raise ev.EvaluationError("Invalid diagnostic summary count.")
        result[key] = value
    for key in ("completed_final", "partial_final", "completed_thinking", "partial_thinking"):
        text = diagnostic.get(key + "_text")
        if not isinstance(text, str) or len(text) != result[key + "_characters"]:
            raise ev.EvaluationError("Diagnostic content length does not match its summary.")
    for key in booleans:
        if not isinstance(diagnostic.get(key), bool):
            raise ev.EvaluationError("Invalid diagnostic summary flag.")
        result[key] = diagnostic[key]
    for key, allowed in statuses.items():
        if diagnostic.get(key) not in allowed:
            raise ev.EvaluationError("Invalid diagnostic summary status.")
        result[key] = diagnostic[key]
    if not isinstance(diagnostic.get("parse_issues"), list) or any(i not in ISSUES for i in diagnostic["parse_issues"]):
        raise ev.EvaluationError("Invalid diagnostic issue code.")
    result["parse_issues"] = list(diagnostic["parse_issues"])
    if not isinstance(diagnostic.get("diagnostic_warnings"), list) or any(i not in WARNINGS for i in diagnostic["diagnostic_warnings"]):
        raise ev.EvaluationError("Invalid diagnostic warning code.")
    result["diagnostic_warnings"] = list(diagnostic["diagnostic_warnings"])
    return result


def _private_directory(run_dir):
    path = Path(run_dir)
    if path.is_symlink():
        raise ev.EvaluationError("Diagnostic run directory must not be a symlink.")
    path = path.resolve()
    try:
        path.relative_to(ev.RUNS_ROOT.resolve())
    except ValueError as exc:
        raise ev.EvaluationError("Diagnostic artifacts must stay inside private runs.") from exc
    directory = path / PRIVATE_DIRECTORY
    if directory.is_symlink():
        raise ev.EvaluationError("Diagnostic directory must not be a symlink.")
    directory.mkdir(mode=0o700, parents=False, exist_ok=True)
    os.chmod(directory, 0o700)
    return directory


def write_private_artifact(run_dir, diagnostic):
    """Write a unique sidecar before returning the response to the run journal."""
    if token_ids_sha256(diagnostic["raw_generated_token_ids"]) != diagnostic["raw_generated_token_ids_sha256"]:
        raise ev.EvaluationError("Raw diagnostic token hash mismatch.")
    directory = _private_directory(run_dir)
    name = uuid.uuid4().hex + ".json"
    raw = ev.json_bytes(diagnostic)
    fd = os.open(directory / name, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as handle:
        handle.write(raw)
        handle.flush()
        os.fsync(handle.fileno())
    return {"file": PRIVATE_DIRECTORY + "/" + name, "sha256": ev.digest(raw)}


def read_private_artifact(run_dir, receipt):
    """Verify the artifact bytes and independently recompute its raw-ID hash."""
    if not isinstance(receipt, dict) or not re.fullmatch(
        PRIVATE_DIRECTORY + r"/[0-9a-f]{32}\.json", receipt.get("file", "")
    ):
        raise ev.EvaluationError("Invalid private diagnostic artifact receipt.")
    path = Path(run_dir) / receipt["file"]
    if path.is_symlink() or path.parent.is_symlink():
        raise ev.EvaluationError("Private diagnostic artifact must not be a symlink.")
    try:
        path.resolve().relative_to(ev.RUNS_ROOT.resolve())
        raw = path.read_bytes()
        if ev.digest(raw) != receipt.get("sha256"):
            raise ValueError
        data = json.loads(raw)
        if data["schema_version"] != SCHEMA_VERSION or token_ids_sha256(data["raw_generated_token_ids"]) != data["raw_generated_token_ids_sha256"]:
            raise ValueError
        if data["generated_token_count"] != len(data["raw_generated_token_ids"]):
            raise ValueError
        public_summary(data, raw_ids_retained=True)
    except (OSError, ValueError, TypeError, KeyError) as exc:
        raise ev.EvaluationError("Private diagnostic artifact failed integrity verification.") from exc
    return data


def verify_private_artifact(response, run_dir):
    """Return safe facts after verifying journal, artifact, and raw-ID binding."""
    try:
        metadata = response["native_tinker"]
        data = read_private_artifact(run_dir, metadata["private_diagnostic_artifact"])
        summary = public_summary(data, raw_ids_retained=True)
        answer = data["completed_final_text"] if not data["parse_issues"] else ""
        if (metadata["output_tokens_sha256"] != data["raw_generated_token_ids_sha256"]
                or metadata["prompt_sha256"] != data["prompt_token_ids_sha256"]
                or metadata["tokenizer_parity"] != data["tokenizer_parity"]
                or metadata["diagnostic_summary"] != summary
                or metadata["provider_stop_reason"] != data["provider_stop_reason"]
                or metadata["parse_issues"] != data["parse_issues"]
                or metadata["turn_end_observed"] != data["turn_end_observed"]
                or response["usage"]["completion_tokens"] != data["generated_token_count"]
                or response["usage"]["prompt_tokens"] != data["prompt_token_count"]
                or ev.answer_details(response) != (answer, data["finish_reason"])):
            raise ValueError
    except (KeyError, TypeError, ValueError, IndexError) as exc:
        raise ev.EvaluationError("Diagnostic response and private artifact do not match.") from exc
    return {**summary, "private_artifact_sha256": metadata["private_diagnostic_artifact"]["sha256"],
            "raw_generated_token_ids_sha256": data["raw_generated_token_ids_sha256"]}


def final_text_for_review(response, run_dir):
    """Private review projection: complete and unfinished final text, no thinking."""
    summary = verify_private_artifact(response, run_dir)
    data = read_private_artifact(run_dir, response["native_tinker"]["private_diagnostic_artifact"])
    malformed = bool(summary["parse_issues"])
    return {
        "completed_final_text": "" if malformed else data["completed_final_text"],
        "partial_final_text": "" if malformed else data["partial_final_text"],
        "native_turn_complete": summary["native_turn_complete"],
        "finish_reason": summary["finish_reason"],
        "partial_final_status": summary["partial_final_status"],
        "final_text_withheld_due_to_malformed_structure": malformed,
        "semantic_answer_completeness": "not_assessed",
    }


class DiagnosticNativeTransport:
    """Base or receipt-verified Inkling sampler; no training client or retries."""

    def __init__(self):
        self.sampler = None
        self.binding = None

    def initialize(self, config, secret):
        if config.get("model") != MODEL:
            raise ev.EvaluationError("This diagnostic worker supports full Inkling only.")
        ev.validate_config(config, execute=False)
        checked = comparison.configure(config)
        for key in ("tokenizer_revision", "tokenizer_sha256", "chat_template_sha256", "native_renderer_packages"):
            if key in config and config[key] != checked.get(key):
                raise ev.EvaluationError("Diagnostic runtime identity differs from the prepared config.")
        if any(key in config for key in ("adapter_sampler_path", "checkpoint_reference_file", "checkpoint_reference_sha256")):
            sampler, fingerprint = adapter.checkpoint_identity(config.get("checkpoint_reference_file", ""))
            if sampler != config.get("adapter_sampler_path") or fingerprint != config.get("checkpoint_reference_sha256"):
                raise ev.EvaluationError("Diagnostic checkpoint receipt does not match the selected sampler.")
        else:
            sampler = None
        self.pinned = comparison.load_pinned_tokenizer(MODEL, config.get("comparison_manifest"))
        self.profile = comparison.TmlProfile(self.pinned, MODEL, config.get("comparison_manifest"))
        _private_directory(config["run_dir"])
        import tinker
        from tinker.lib.retry_handler import RetryConfig
        self.types = tinker.types
        self.service = tinker.ServiceClient(api_key=secret, base_url=native.TINKER_URL,
                                            max_retries=0, timeout=config["timeout_seconds"])
        source = {"model_path": sampler} if sampler is not None else {"base_model": MODEL}
        self.sampler = self.service.create_sampling_client(
            **source, retry_config=RetryConfig(enable_retry_logic=False, progress_timeout=config["timeout_seconds"]))
        self.base_model = self.sampler.get_base_model()
        if self.base_model != MODEL:
            raise ev.EvaluationError("Diagnostic sampler returned a different base model.")
        self.binding = ev.digest(ev.json_bytes(config))

    def __call__(self, payload, config, secret):
        if self.sampler is None:
            self.initialize(config, secret)
        if ev.digest(ev.json_bytes(config)) != self.binding:
            raise ev.EvaluationError("Diagnostic worker settings cannot change between requests.")
        prompt_tokens, _ = self.profile.render(payload, config)
        if len(prompt_tokens) > config["max_input_tokens"]:
            raise ev.EvaluationError("The exact rendered prompt exceeds the input limit.")
        params = self.types.SamplingParams(max_tokens=config["max_output_tokens"], temperature=config["temperature"],
                                           seed=config["seed"], stop=self.profile.stop_tokens)
        output = self.sampler.sample(prompt=self.types.ModelInput.from_ints(prompt_tokens), num_samples=1,
                                     sampling_params=params).result(timeout=config["timeout_seconds"])
        if len(output.sequences) != 1:
            raise ev.EvaluationError("Diagnostic sampling returned an unexpected sequence count.")
        sequence = output.sequences[0]
        diagnostic = parse_generated(self.profile, payload, config, list(sequence.tokens), sequence.stop_reason)
        diagnostic["prompt_token_ids_sha256"] = ev.digest(ev.json_bytes(prompt_tokens))
        diagnostic["prompt_token_count"] = len(prompt_tokens)
        diagnostic["tokenizer_parity"] = self.profile.parity
        artifact = write_private_artifact(config["run_dir"], diagnostic)
        summary = public_summary(diagnostic, raw_ids_retained=True)
        # Thinking/partial final content never travels into ev.run's generic
        # journal or ordinary answer stream. Malformed content is not promoted.
        answer = diagnostic["completed_final_text"] if not diagnostic["parse_issues"] else ""
        return {
            "model": self.base_model,
            "choices": [{"message": {"role": "assistant", "content": answer}, "finish_reason": diagnostic["finish_reason"]}],
            "usage": {"prompt_tokens": len(prompt_tokens), "completion_tokens": diagnostic["generated_token_count"]},
            "native_tinker": {
                "accounting_source": "submitted_prompt_and_returned_sequence_token_counts", "accounting_is_invoice": False,
                "prompt_sha256": diagnostic["prompt_token_ids_sha256"],
                "output_tokens_sha256": diagnostic["raw_generated_token_ids_sha256"],
                "prompt_cache_hit_tokens": getattr(output, "prompt_cache_hit_tokens", None),
                "provider_stop_reason": diagnostic["provider_stop_reason"], "parse_issues": diagnostic["parse_issues"],
                "turn_end_observed": diagnostic["turn_end_observed"], "analysis_content_tokens": None,
                "tokenizer_parity": self.profile.parity, "base_revision": "provider_revision_unpinned",
                "reasoning_text_retained": True, "reasoning_retention_location": "private_diagnostic_sidecar_only",
                "raw_generated_token_ids_retained": True, "private_diagnostic_artifact": artifact,
                "diagnostic_summary": summary, "sdk_internal_submission_retries": "may_occur; count_not_exposed",
            },
        }


def sampling_worker(connection):
    """Compatible with the unchanged BoundedNativeTransport process contract."""
    os.environ["TINKER_TELEMETRY"] = "0"
    with open(os.devnull, "w") as sink, contextlib.redirect_stdout(sink), contextlib.redirect_stderr(sink):
        transport = DiagnosticNativeTransport()
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
