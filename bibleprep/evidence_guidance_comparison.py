"""Prepare deterministic offline inputs for the two-condition guidance comparison.

This module has no native/tokenizer renderer, transport, environment access,
CLI, or file writer.  It prepares inputs only; it does not freeze questions,
authorize generation, or adapt the legacy three-arm evidence pilot.
"""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import re

from bibleprep import evidence_answer_context as answer_context
from bibleprep import evidence_delivery as delivery
from bibleprep.evidence import ROOT


SCHEMA_VERSION = 1
ARTIFACT_KIND = "offline_evidence_guidance_comparison_pair_v1"
CONDITION_IDS = ("B-original", "B-guided")
ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,119}\Z")
COMPONENT_KEY_RE = re.compile(
    r"[A-Za-z0-9][A-Za-z0-9_.-]{0,119}/[A-Za-z0-9][A-Za-z0-9_.-]{0,119}\Z"
)


class EvidenceGuidanceComparisonError(ValueError):
    """Raised when a comparison pair cannot be prepared exactly offline."""


def _canonical_bytes(value):
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise EvidenceGuidanceComparisonError("comparison input must be finite JSON") from exc


def _canonical_sha256(value):
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _text_sha256(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _module_sha256(module, label):
    try:
        return hashlib.sha256(Path(module.__file__).read_bytes()).hexdigest()
    except (OSError, TypeError) as exc:
        raise EvidenceGuidanceComparisonError(f"{label} module binding could not be read") from exc


def _text(value, label):
    if not isinstance(value, str) or not value.strip():
        raise EvidenceGuidanceComparisonError(f"{label} must be nonempty text")


def _component_keys(value, *, allow_empty):
    if not isinstance(value, (list, tuple)):
        raise EvidenceGuidanceComparisonError("selected_component_keys must be a sequence")
    keys = []
    for index, key in enumerate(value):
        if not isinstance(key, str) or not COMPONENT_KEY_RE.fullmatch(key):
            raise EvidenceGuidanceComparisonError(
                f"selected_component_keys[{index}] is invalid"
            )
        keys.append(key)
    if not allow_empty and not keys:
        raise EvidenceGuidanceComparisonError(
            "evidence-bearing cases require selected_component_keys"
        )
    if len(set(keys)) != len(keys):
        raise EvidenceGuidanceComparisonError("selected_component_keys contains duplicates")
    return sorted(keys)


def _candidate_component_keys(verified):
    try:
        records = verified["candidate"]["records"]
        return sorted(
            record["record_id"] + "/" + component["component_id"]
            for record in records
            for component in record["components"]
        )
    except (KeyError, TypeError) as exc:
        raise EvidenceGuidanceComparisonError("verified bundle is malformed") from exc


def _condition(model_input, *, guidance_applied):
    return {
        "guidance_applied": guidance_applied,
        "model_input": copy.deepcopy(model_input),
        "system_prompt_text_sha256": _text_sha256(model_input["system_prompt"]),
        "question_text_sha256": _text_sha256(model_input["question"]),
        "evidence_text_sha256": _text_sha256(model_input["evidence"]),
        "model_input_sha256": _canonical_sha256(model_input),
    }


def prepare_comparison_pair(*, case_id, system_prompt, question,
                            selected_component_keys, verified, registry,
                            notice_manifest, general_control=False, root=ROOT,
                            record_directory=None):
    """Return two paired model inputs plus bindings sufficient for later freezing.

    Evidence-bearing cases freshen the exact verified bundle through
    ``verify_for_use`` and render the original condition separately.  The guided
    condition is always built by ``evidence_answer_context.build_model_input``,
    which performs its own fresh delivery verification.

    General controls have no selected evidence and therefore no delivery bundle:
    the delivery schema intentionally rejects empty candidates.  They retain an
    empty evidence string in both conditions and use the exact exported guidance
    constant in the guided system prompt.  Registry and notice-manifest hashes
    are still bound for the prospective protocol without inventing a source use.
    """
    if not isinstance(case_id, str) or not ID_RE.fullmatch(case_id):
        raise EvidenceGuidanceComparisonError("case_id must be a stable identifier")
    _text(system_prompt, "system_prompt")
    _text(question, "question")
    if answer_context.EVIDENCE_GUIDANCE in system_prompt:
        raise EvidenceGuidanceComparisonError(
            "system_prompt already contains the versioned evidence guidance"
        )
    if type(general_control) is not bool:
        raise EvidenceGuidanceComparisonError("general_control must be boolean")
    if not isinstance(registry, dict) or not isinstance(notice_manifest, dict):
        raise EvidenceGuidanceComparisonError(
            "registry and notice_manifest must be explicit objects"
        )
    selected = _component_keys(selected_component_keys, allow_empty=general_control)

    registry_sha256 = _canonical_sha256(registry)
    notice_manifest_sha256 = _canonical_sha256(notice_manifest)
    verified_candidate_sha256 = None
    verified_registry_sha256 = None

    if general_control:
        if selected:
            raise EvidenceGuidanceComparisonError(
                "general controls must preserve an empty evidence selection"
            )
        if verified is not None:
            raise EvidenceGuidanceComparisonError(
                "general controls must not carry a fabricated evidence bundle"
            )
        original = {
            "system_prompt": system_prompt,
            "question": question,
            "evidence": "",
        }
        guided = {
            "system_prompt": system_prompt + "\n\n" + answer_context.EVIDENCE_GUIDANCE,
            "question": question,
            "evidence": "",
        }
    else:
        if not isinstance(verified, dict):
            raise EvidenceGuidanceComparisonError(
                "evidence-bearing cases require a verified bundle"
            )
        try:
            current = delivery.verify_for_use(
                verified["candidate"],
                registry,
                notice_manifest,
                root=root,
                record_directory=record_directory,
            )
            if _canonical_bytes(current) != _canonical_bytes(verified):
                raise EvidenceGuidanceComparisonError(
                    "verified bundle differs from current use verification"
                )
            bound_keys = _candidate_component_keys(current)
            if selected != bound_keys:
                raise EvidenceGuidanceComparisonError(
                    "selected_component_keys differ from the verified bundle"
                )
            evidence = delivery.render_model_input(
                current,
                registry,
                notice_manifest,
                root=root,
                record_directory=record_directory,
            )
            guided = answer_context.build_model_input(
                system_prompt,
                question,
                current,
                registry,
                notice_manifest,
                root=root,
                record_directory=record_directory,
            )
        except EvidenceGuidanceComparisonError:
            raise
        except (KeyError, TypeError, ValueError) as exc:
            raise EvidenceGuidanceComparisonError(
                "current evidence delivery verification failed"
            ) from exc
        original = {
            "system_prompt": system_prompt,
            "question": question,
            "evidence": evidence,
        }
        if guided["evidence"] != evidence or guided["question"] != question:
            raise EvidenceGuidanceComparisonError(
                "answer-context input differs in question or evidence"
            )
        if guided["system_prompt"] != (
            system_prompt + "\n\n" + answer_context.EVIDENCE_GUIDANCE
        ):
            raise EvidenceGuidanceComparisonError(
                "answer-context input differs outside the versioned guidance"
            )
        verified_candidate_sha256 = current["candidate_sha256"]
        verified_registry_sha256 = current["registry_sha256"]

    if original["question"] != guided["question"]:
        raise EvidenceGuidanceComparisonError("paired questions differ")
    if original["evidence"].encode("utf-8") != guided["evidence"].encode("utf-8"):
        raise EvidenceGuidanceComparisonError("paired evidence bytes differ")

    conditions = {
        CONDITION_IDS[0]: _condition(original, guidance_applied=False),
        CONDITION_IDS[1]: _condition(guided, guidance_applied=True),
    }
    artifact = {
        "schema_version": SCHEMA_VERSION,
        "artifact_kind": ARTIFACT_KIND,
        "status": "prepared_offline_not_frozen",
        "case_id": case_id,
        "general_control": general_control,
        "condition_order": list(CONDITION_IDS),
        "selected_component_keys": selected,
        "conditions": conditions,
        "pair_bindings": {
            "question_text_sha256": _text_sha256(question),
            "evidence_text_sha256": _text_sha256(original["evidence"]),
            "selected_component_keys_sha256": _canonical_sha256(selected),
            "registry_sha256": registry_sha256,
            "notice_manifest_sha256": notice_manifest_sha256,
            "verified_candidate_sha256": verified_candidate_sha256,
            "verified_registry_sha256": verified_registry_sha256,
            "guidance_version": answer_context.GUIDANCE_VERSION,
            "guidance_sha256": answer_context.GUIDANCE_SHA256,
            "comparison_module_sha256": _module_sha256(
                __import__(__name__, fromlist=["_"]), "comparison"
            ),
            "answer_context_module_sha256": _module_sha256(
                answer_context, "answer-context"
            ),
            "delivery_module_sha256": _module_sha256(delivery, "delivery"),
        },
        "pair_invariants": {
            "question_byte_identical": True,
            "evidence_byte_identical": True,
            "only_system_difference_is_versioned_guidance": True,
        },
        "authorization": {
            "artifact_frozen": False,
            "generation_authorized": False,
            "training_authorized": False,
        },
        "model_calls": 0,
        "network_requests": 0,
    }
    return artifact


def verify_comparison_pair(prepared, **inputs):
    """Rebuild a pair from explicit inputs and reject any changed output field."""
    if not isinstance(prepared, dict):
        raise EvidenceGuidanceComparisonError("prepared pair must be an object")
    rebuilt = prepare_comparison_pair(**inputs)
    if _canonical_bytes(prepared) != _canonical_bytes(rebuilt):
        raise EvidenceGuidanceComparisonError(
            "prepared pair differs from deterministic regeneration"
        )
    return copy.deepcopy(rebuilt)
