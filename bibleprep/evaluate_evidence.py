"""Plan a constructed three-arm evidence comparison without model access.

This module validates exact evidence dependencies and writes an offline slot
inventory.  It deliberately contains no inference transport, tokenizer import,
environment lookup, execution switch, review integration, or scoring code.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import html
import json
import math
import os
from pathlib import Path
import re

from bibleprep import evidence as evidence_module
from bibleprep import evidence_eligibility as eligibility_module
from bibleprep.evidence import PRIVATE_DRAFTS, ROOT, confined_path, sha256, strict_load
from bibleprep.evidence_eligibility import build_projection, canonical_sha256


SCHEMA_VERSION = 1
ARMS = ("B-memory", "B-packet", "B-lookup")
ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,79}")
COMPONENT_KEY_RE = re.compile(
    r"[A-Za-z0-9][A-Za-z0-9_.-]{0,119}/[A-Za-z0-9][A-Za-z0-9_.-]{0,119}"
)
SHA256_RE = re.compile(r"[a-f0-9]{64}")
PRIVATE_PREFIXES = ("runs", "data/evidence")


def _schema_one(value, label):
    if isinstance(value, bool) or not isinstance(value, int) or value != SCHEMA_VERSION:
        raise ValueError(f"Unsupported {label} schema_version")


def _require_keys(value, expected, label):
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")
    actual = set(value)
    expected = set(expected)
    if actual != expected:
        raise ValueError(
            f"{label} fields differ: missing={sorted(expected - actual)} "
            f"extra={sorted(actual - expected)}"
        )


def _identifier(value, label):
    if not isinstance(value, str) or not ID_RE.fullmatch(value):
        raise ValueError(f"{label} must be a stable identifier of at most 80 characters")


def _text(value, label, *, allow_empty=False):
    if not isinstance(value, str) or (not allow_empty and not value.strip()):
        raise ValueError(f"{label} must be a {'string' if allow_empty else 'nonempty string'}")


def _text_list(value, label, *, allow_empty=True):
    if (not isinstance(value, list) or (not allow_empty and not value)
            or any(not isinstance(item, str) or not item.strip() for item in value)):
        qualifier = "" if allow_empty else "nonempty "
        raise ValueError(f"{label} must be a {qualifier}list of nonempty strings")


def _component_keys(value, label, *, allow_empty=True):
    if not isinstance(value, list) or (not allow_empty and not value):
        raise ValueError(f"{label} must be a {'possibly empty' if allow_empty else 'nonempty'} list")
    if any(not isinstance(item, str) or not COMPONENT_KEY_RE.fullmatch(item) for item in value):
        raise ValueError(f"{label} contains an invalid record/component key")
    if len(set(value)) != len(value):
        raise ValueError(f"{label} contains duplicate component keys")


def _number(value, label, *, minimum=None, maximum=None, integer=False):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"{label} must be a finite number")
    if integer and not isinstance(value, int):
        raise ValueError(f"{label} must be an integer")
    if minimum is not None and value < minimum:
        raise ValueError(f"{label} must be at least {minimum}")
    if maximum is not None and value > maximum:
        raise ValueError(f"{label} must be at most {maximum}")


def _validate_cases(document):
    _require_keys(document, {"schema_version", "suite_id", "fixture_kind", "cases"}, "cases")
    _schema_one(document["schema_version"], "cases")
    _identifier(document["suite_id"], "cases.suite_id")
    if document["fixture_kind"] != "constructed":
        raise ValueError("Only constructed fixtures are accepted by this offline planner")
    if not isinstance(document["cases"], list) or not document["cases"]:
        raise ValueError("cases.cases must be a nonempty list")
    seen = set()
    prepared = []
    for index, case in enumerate(document["cases"]):
        label = f"cases.cases[{index}]"
        _require_keys(case, {
            "case_id", "question", "category", "general_control",
            "packet_component_keys", "lookup_key", "private",
        }, label)
        _identifier(case["case_id"], label + ".case_id")
        if case["case_id"] in seen:
            raise ValueError(f"Duplicate case_id: {case['case_id']}")
        seen.add(case["case_id"])
        _text(case["question"], label + ".question")
        _identifier(case["category"], label + ".category")
        if not isinstance(case["general_control"], bool):
            raise ValueError(label + ".general_control must be boolean")
        _component_keys(
            case["packet_component_keys"], label + ".packet_component_keys",
            allow_empty=case["general_control"],
        )
        if case["general_control"]:
            if case["packet_component_keys"] or case["lookup_key"] is not None:
                raise ValueError("General controls must declare no packet components and a null lookup_key")
        else:
            _identifier(case["lookup_key"], label + ".lookup_key")
        private = case["private"]
        _require_keys(private, {
            "expected_answer", "scoring_criteria", "reviewer_instructions", "provenance",
        }, label + ".private")
        _text(private["expected_answer"], label + ".private.expected_answer")
        _text_list(private["scoring_criteria"], label + ".private.scoring_criteria", allow_empty=False)
        _text_list(private["reviewer_instructions"], label + ".private.reviewer_instructions")
        _text_list(private["provenance"], label + ".private.provenance", allow_empty=False)
        prepared.append(case)
    return prepared


def _validate_settings(document):
    _require_keys(document, {
        "schema_version", "settings_id", "checkpoint_id", "system_prompt", "sampling",
        "request_order", "stop_rule",
    }, "settings")
    _schema_one(document["schema_version"], "settings")
    _identifier(document["settings_id"], "settings.settings_id")
    _identifier(document["checkpoint_id"], "settings.checkpoint_id")
    _text(document["system_prompt"], "settings.system_prompt")
    if document["request_order"] != "case_then_arm":
        raise ValueError("settings.request_order must be case_then_arm")
    if document["stop_rule"] != "stop_after_uncertain_or_incomplete":
        raise ValueError("settings.stop_rule must be stop_after_uncertain_or_incomplete")
    sampling = document["sampling"]
    _require_keys(sampling, {
        "effort", "temperature", "seed", "max_tokens", "input_token_limit", "deadline_seconds",
    }, "settings.sampling")
    _number(sampling["effort"], "settings.sampling.effort", minimum=0, maximum=1)
    _number(sampling["temperature"], "settings.sampling.temperature", minimum=0)
    _number(sampling["seed"], "settings.sampling.seed", integer=True)
    _number(sampling["max_tokens"], "settings.sampling.max_tokens", minimum=1, integer=True)
    _number(
        sampling["input_token_limit"], "settings.sampling.input_token_limit",
        minimum=1, integer=True,
    )
    _number(sampling["deadline_seconds"], "settings.sampling.deadline_seconds", minimum=0.001)


def _validate_policy(document):
    _require_keys(document, {"schema_version", "policy_id", "kind", "mappings"}, "policy")
    _schema_one(document["schema_version"], "policy")
    _identifier(document["policy_id"], "policy.policy_id")
    if document["kind"] != "deterministic_exact_component_key_fixture":
        raise ValueError("Only the deterministic exact component-key fixture policy is supported")
    if not isinstance(document["mappings"], list):
        raise ValueError("policy.mappings must be a list")
    result = {}
    for index, mapping in enumerate(document["mappings"]):
        label = f"policy.mappings[{index}]"
        _require_keys(mapping, {"lookup_key", "component_keys"}, label)
        _identifier(mapping["lookup_key"], label + ".lookup_key")
        if mapping["lookup_key"] in result:
            raise ValueError(f"Duplicate lookup_key: {mapping['lookup_key']}")
        _component_keys(mapping["component_keys"], label + ".component_keys")
        result[mapping["lookup_key"]] = mapping["component_keys"]
    return result


def _projection_components(projection):
    result = {}
    for record in projection["records"]:
        for component in record["components"]:
            key = record["record_id"] + "/" + component["component_id"]
            if key in result:
                raise ValueError(f"Duplicate projected component key: {key}")
            result[key] = (record, component)
    return result


def _public_citation(citation):
    """Keep factual citation data while removing hashes and local workflow data."""
    return {
        key: citation[key]
        for key in (
            "id", "source_id", "kind", "author_or_institution", "title", "locator", "url",
            "publication_date", "accessed_on", "pinned_version",
        )
    }


def _evidence_bundle(component_keys, components):
    records = {}
    provenance = []
    for key in component_keys:
        record, component = components[key]
        record_entry = records.setdefault(record["record_id"], {
            "coverage_limits": copy.deepcopy(record["coverage_limits"]),
            "components": [],
        })
        record_entry["components"].append({
            "content": [copy.deepcopy(item["value"]) for item in component["content"]],
            "citations": [_public_citation(item) for item in component["citations"]],
        })
        provenance.append({
            "component_key": key,
            "record_sha256": record["record_sha256"],
            "component_sha256": component["content_sha256"],
            "citation_dependencies": copy.deepcopy(component["citation_dependencies"]),
            "source_dependencies": [
                {
                    "citation_id": item["citation_id"],
                    "source_id": item["source_id"],
                    "content_sha256": item["content_sha256"],
                }
                for item in component["source_dependencies"]
            ],
        })
    context = {"records": list(records.values())}
    evidence_text = "" if not component_keys else json.dumps(
        context, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    return evidence_text, provenance


def _slot(case, arm, settings, component_keys, components, status, retrieval_status):
    evidence_text, provenance = _evidence_bundle(component_keys, components)
    model_input = {
        "system_prompt": settings["system_prompt"],
        "question": case["question"],
        "evidence": evidence_text,
    }
    return {
        "slot_id": case["case_id"] + "--" + arm.lower(),
        "case_id": case["case_id"],
        "arm": arm,
        "category": case["category"],
        "general_control": case["general_control"],
        "status": status,
        "retrieval_status": retrieval_status,
        "question": case["question"],
        "question_sha256": canonical_sha256(case["question"]),
        "settings": copy.deepcopy(settings["sampling"]),
        "settings_sha256": canonical_sha256(settings),
        "model_input": model_input,
        "model_input_sha256": canonical_sha256(model_input),
        "evidence_content": evidence_text,
        "evidence_content_sha256": hashlib.sha256(evidence_text.encode("utf-8")).hexdigest(),
        "evidence_component_keys": list(component_keys),
        "evidence_provenance": provenance,
        "private_case_sha256": canonical_sha256(case["private"]),
    }


def _file_bindings(value):
    if value is None:
        return {}
    _require_keys(value, {"cases", "settings", "policy", "registry", "projection"},
                  "input_file_sha256")
    for key, digest in value.items():
        if not isinstance(digest, str) or not SHA256_RE.fullmatch(digest):
            raise ValueError(f"input_file_sha256.{key} must be a lowercase SHA-256")
    return dict(value)


def build_offline_plan(*, root, cases, settings, policy, registry, saved_projection,
                       record_directory=None, input_file_sha256=None):
    """Validate inputs and return a deterministic, non-executable slot plan."""
    root = Path(root).resolve()
    prepared_cases = _validate_cases(cases)
    _validate_settings(settings)
    lookup = _validate_policy(policy)
    file_hashes = _file_bindings(input_file_sha256)

    if not isinstance(registry, dict) or "schema_version" not in registry:
        raise ValueError("registry must contain schema_version")
    if not isinstance(saved_projection, dict) or "schema_version" not in saved_projection:
        raise ValueError("saved projection must contain schema_version")
    _schema_one(registry["schema_version"], "registry")
    _schema_one(saved_projection["schema_version"], "saved projection")

    rebuilt = build_projection(
        registry, "app_display", root, record_directory or root / PRIVATE_DRAFTS
    )
    if canonical_sha256(saved_projection) != canonical_sha256(rebuilt):
        raise ValueError(
            "Saved app_display projection is stale or differs from the exact rebuilt projection"
        )
    if saved_projection.get("selected_use") != "app_display":
        raise ValueError("Saved projection is not for app_display model-input use")
    components = _projection_components(rebuilt)

    case_details = []
    global_reasons = []
    if not components:
        global_reasons.append("eligible_app_display_projection_is_empty")
    for case in prepared_cases:
        missing_packet = sorted(set(case["packet_component_keys"]) - set(components))
        if case["general_control"]:
            lookup_keys = []
        else:
            if case["lookup_key"] not in lookup:
                raise ValueError(f"No exact fixture lookup mapping for case {case['case_id']}")
            lookup_keys = lookup[case["lookup_key"]]
        missing_lookup = sorted(set(lookup_keys) - set(components))
        reasons = []
        if missing_packet:
            reasons.append("packet_components_unavailable:" + ",".join(missing_packet))
        if missing_lookup:
            reasons.append("lookup_components_unavailable:" + ",".join(missing_lookup))
        case_details.append((case, lookup_keys, reasons))
        global_reasons.extend(f"{case['case_id']}:{reason}" for reason in reasons)

    engineering_ready = not global_reasons
    planned_slots = []
    for case, lookup_keys, reasons in case_details:
        blocked = bool(reasons) or not components
        for arm in ARMS:
            if blocked:
                status = "blocked_evidence_not_ready"
            elif case["general_control"]:
                status = "repeat_control_planned"
            else:
                status = "planned_offline"
            if arm == "B-memory":
                selected = []
                retrieval_status = "not_applicable_memory"
            elif arm == "B-packet":
                selected = case["packet_component_keys"] if not reasons else []
                retrieval_status = "fixed_packet" if not reasons else "blocked"
            else:
                selected = lookup_keys if not reasons else []
                if reasons:
                    retrieval_status = "blocked"
                elif case["general_control"]:
                    retrieval_status = "not_applicable_control"
                else:
                    retrieval_status = "exact_fixture_hit" if lookup_keys else "exact_fixture_miss"
            planned_slots.append(
                _slot(case, arm, settings, selected, components, status, retrieval_status)
            )

    module_path = Path(__file__).resolve()
    return {
        "schema_version": SCHEMA_VERSION,
        "planner_kind": "constructed_offline_evidence_inventory",
        "suite_id": cases["suite_id"],
        "engineering_readiness": {
            "status": "ready" if engineering_ready else "not_ready",
            "reasons": sorted(set(global_reasons)),
        },
        "execution_readiness": {
            "status": "not_ready",
            "open_requirements": [
                "live_native_runner_and_transport_are_not_implemented",
                "question_protocol_and_slot_inventory_are_not_frozen",
                "current_provider_pricing_and_cost_bound_are_not_recorded",
                "concrete_execution_permission_is_not_recorded",
                "checkpoint_identity_retention_and_native_template_are_not_verified_here",
                "native_tokenizer_input_limit_is_not_verified_here",
                "source_inference_provider_use_basis_requires_human_verification",
                "masked_review_and_collection_integration_are_not_implemented_here",
            ],
        },
        "bindings": {
            "module_sha256": sha256(module_path),
            "evidence_module_sha256": sha256(Path(evidence_module.__file__).resolve()),
            "eligibility_module_sha256": sha256(Path(eligibility_module.__file__).resolve()),
            "record_schema_plan_sha256": sha256(root / evidence_module.PLAN),
            "cases_content_sha256": canonical_sha256(cases),
            "settings_content_sha256": canonical_sha256(settings),
            "policy_content_sha256": canonical_sha256(policy),
            "registry_content_sha256": canonical_sha256(registry),
            "saved_projection_content_sha256": canonical_sha256(saved_projection),
            "rebuilt_projection_content_sha256": canonical_sha256(rebuilt),
            "registry_declared_sha256": rebuilt["registry_sha256"],
            "input_file_sha256": file_hashes,
        },
        "logical_checkpoint_reference": {
            "checkpoint_id": settings["checkpoint_id"],
            "verified_for_execution": False,
        },
        "lookup_policy": {
            "policy_id": policy["policy_id"],
            "kind": policy["kind"],
            "production_retriever": False,
        },
        "request_order": settings["request_order"],
        "stop_rule": settings["stop_rule"],
        "case_count": len(prepared_cases),
        "planned_slot_count": len(planned_slots),
        "planned_slots": planned_slots,
        "model_calls": 0,
        "network_requests": 0,
    }


def _md(value):
    return html.escape(str(value), quote=True).replace("\n", " ")


def render_markdown(plan):
    lines = [
        "# Offline evidence comparison plan",
        "",
        f"Suite: `{_md(plan['suite_id'])}`  ",
        f"Engineering readiness: `{plan['engineering_readiness']['status']}`  ",
        f"Execution readiness: `{plan['execution_readiness']['status']}`  ",
        f"Cases: {plan['case_count']}  ",
        f"Planned slots: {plan['planned_slot_count']}",
        "",
        "This artifact is a constructed offline inventory. It made no model or network calls.",
        "",
        "## Readiness",
        "",
    ]
    reasons = plan["engineering_readiness"]["reasons"]
    lines.extend(["- " + _md(item) for item in reasons] or ["- Constructed dependencies are internally ready."])
    lines.extend(["", "Execution remains unavailable because:"])
    lines.extend("- " + _md(item) for item in plan["execution_readiness"]["open_requirements"])
    lines.extend(["", "## Planned slots", "", "| Slot | Arm | Status | Evidence |", "| --- | --- | --- | --- |"])
    for slot in plan["planned_slots"]:
        lines.append(
            f"| `{_md(slot['slot_id'])}` | `{slot['arm']}` | `{slot['status']}` | "
            f"`{slot['retrieval_status']}` |"
        )
    lines.extend([
        "", "## Bound implementation", "",
        f"Module SHA-256: `{plan['bindings']['module_sha256']}`  ",
        f"Registry SHA-256: `{plan['bindings']['registry_declared_sha256']}`  ",
        f"Projection SHA-256: `{plan['bindings']['rebuilt_projection_content_sha256']}`",
        "",
    ])
    return "\n".join(lines)


def _mkdir_private(path, root):
    relative = path.relative_to(root)
    current = root
    for part in relative.parts:
        current = current / part
        if current.exists():
            if not current.is_dir() or current.is_symlink():
                raise ValueError(f"Private output ancestor is unsafe: {current}")
        else:
            os.mkdir(current, 0o700)


def _exclusive_text(path):
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    return os.fdopen(os.open(path, flags, 0o600), "w", encoding="utf-8")


def write_plan(plan, output_directory, root=ROOT):
    """Write plan JSON and Markdown to a fresh ignored private runs directory."""
    root = Path(root).resolve()
    destination = confined_path(root, output_directory, ("runs",))
    if destination.exists():
        raise FileExistsError(destination)
    _mkdir_private(destination.parent, root)
    os.mkdir(destination, 0o700)
    json_path = destination / "plan.json"
    markdown_path = destination / "plan.md"
    with _exclusive_text(json_path) as output:
        json.dump(plan, output, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False)
        output.write("\n")
    with _exclusive_text(markdown_path) as output:
        output.write(render_markdown(plan))
    return {
        "output_directory": destination.relative_to(root).as_posix(),
        "json_sha256": sha256(json_path),
        "markdown_sha256": sha256(markdown_path),
    }


def _private_file(root, value, label):
    path = confined_path(root, value, PRIVATE_PREFIXES)
    if not path.is_file() or path.is_symlink():
        raise ValueError(f"{label} is missing or unsafe")
    return path


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", type=Path, required=True)
    parser.add_argument("--settings", type=Path, required=True)
    parser.add_argument("--policy", type=Path, required=True)
    parser.add_argument("--registry", type=Path, required=True)
    parser.add_argument("--projection", type=Path, required=True)
    parser.add_argument("--directory", type=Path, default=Path(PRIVATE_DRAFTS))
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        paths = {
            name: _private_file(ROOT, getattr(args, name), name)
            for name in ("cases", "settings", "policy", "registry", "projection")
        }
        record_directory = confined_path(ROOT, args.directory, ("data/evidence",))
        if not record_directory.is_dir() or record_directory.is_symlink():
            raise ValueError("record directory is missing or unsafe")
        values = {name: strict_load(path) for name, path in paths.items()}
        plan = build_offline_plan(
            root=ROOT,
            cases=values["cases"],
            settings=values["settings"],
            policy=values["policy"],
            registry=values["registry"],
            saved_projection=values["projection"],
            record_directory=record_directory,
            input_file_sha256={name: sha256(path) for name, path in paths.items()},
        )
        receipt = write_plan(plan, args.out, ROOT)
        print(json.dumps({
            "status": "offline_plan_written",
            "engineering_readiness": plan["engineering_readiness"],
            "execution_readiness": plan["execution_readiness"]["status"],
            **receipt,
        }, indent=2, sort_keys=True))
        return 0
    except (OSError, ValueError) as error:
        parser.error(str(error))


if __name__ == "__main__":
    raise SystemExit(main())
