"""Pure mechanical validation for the Candidate G source and row plan.

This module validates caller-supplied JSON-like objects only.  It does not read
source files, decide license or scholarly truth, author prompts or targets,
prepare training data, contact a provider, or authorize training.
"""
from __future__ import annotations

from collections import Counter
import math
import re


SCHEMA_VERSION = 1
LANGUAGES = ("hbo", "grc", "arc")
TRAIN_GROUPS = {"direct": 40, "boundary": 24, "intent": 16, "rehearsal": 16}
VALIDATION_GROUPS = {"direct": 12, "boundary": 6, "intent": 6}
FAMILY_LANGUAGE_QUOTAS = {
    "training": {"hbo": 22, "grc": 14, "arc": 4},
    "validation": {"hbo": 6, "grc": 4, "arc": 2},
}
SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")
ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,159}\Z")
FORBIDDEN_AUTHORING_KEYS = frozenset({
    "answer", "answer_text", "completion", "final_text", "messages", "prompt",
    "question", "questions", "reasoning", "target", "target_text", "targets",
})


class CandidateGPlanError(ValueError):
    """Raised when a Candidate G planning artifact is mechanically invalid."""


def _json(value, label):
    if value is None or isinstance(value, (str, bool, int)):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise CandidateGPlanError(f"{label} contains a non-finite number")
        return
    if isinstance(value, list):
        for index, item in enumerate(value):
            _json(item, f"{label}[{index}]")
        return
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise CandidateGPlanError(f"{label} has a non-string key")
            _json(item, f"{label}.{key}")
        return
    raise CandidateGPlanError(f"{label} is not finite JSON data")


def _exact(value, keys, label):
    if not isinstance(value, dict):
        raise CandidateGPlanError(f"{label} must be an object")
    expected = set(keys)
    actual = set(value)
    if actual != expected:
        raise CandidateGPlanError(
            f"{label} fields differ; missing={sorted(expected - actual)}, "
            f"extra={sorted(actual - expected)}"
        )


def _text(value, label):
    if not isinstance(value, str) or not value.strip():
        raise CandidateGPlanError(f"{label} must be nonempty text")


def _id(value, label):
    if not isinstance(value, str) or not ID_RE.fullmatch(value):
        raise CandidateGPlanError(f"{label} must be a stable identifier")


def _sha(value, label):
    if not isinstance(value, str) or not SHA256_RE.fullmatch(value):
        raise CandidateGPlanError(f"{label} must be a lowercase SHA-256")


def _texts(value, label, *, empty=False):
    if (not isinstance(value, list) or (not empty and not value)
            or any(not isinstance(item, str) or not item.strip() for item in value)):
        raise CandidateGPlanError(f"{label} must be a list of nonempty strings")


def _language(value, label):
    if value not in LANGUAGES:
        raise CandidateGPlanError(f"{label} must be the ISO code hbo, grc, or arc")


def _chapter(value, label):
    if not isinstance(value, str) or not re.fullmatch(r"[1-9][0-9]*", value):
        raise CandidateGPlanError(
            f"{label} must be a canonical positive decimal without leading zeroes"
        )


def _forbid_authored_content(value, label="plan"):
    if isinstance(value, dict):
        for key, item in value.items():
            if key.lower() in FORBIDDEN_AUTHORING_KEYS:
                raise CandidateGPlanError(
                    f"{label}.{key} is forbidden before question/target authoring"
                )
            _forbid_authored_content(item, f"{label}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _forbid_authored_content(item, f"{label}[{index}]")


def _chapter_key(value):
    return value["book"], value["chapter"]


def _validate_prior_exposure(value, label):
    _exact(value, {
        "in_b_raw_text", "in_prior_english_training", "in_prior_evaluation",
        "in_project_research", "validation_exposure_exception",
    }, label)
    for key in (
            "in_b_raw_text", "in_prior_english_training", "in_prior_evaluation",
            "in_project_research"):
        if type(value[key]) is not bool:
            raise CandidateGPlanError(f"{label}.{key} must be boolean")
    exception = value["validation_exposure_exception"]
    if exception is not None:
        _text(exception, label + ".validation_exposure_exception")


def _validate_source_inventory(inventory):
    _json(inventory, "source_inventory")
    _exact(inventory, {
        "schema_version", "artifact_kind", "status", "scope", "source_layers",
        "training_families", "validation_families", "rehearsal_rows", "exclusions",
        "constraints", "counts", "validation_checks",
    }, "source_inventory")
    if inventory["schema_version"] != SCHEMA_VERSION:
        raise CandidateGPlanError("Unsupported source inventory schema_version")
    if inventory["artifact_kind"] != "candidate_g_source_inventory_v1":
        raise CandidateGPlanError("Unexpected source inventory artifact_kind")
    if inventory["status"] != "planning_inventory_unapproved":
        raise CandidateGPlanError("Source inventory must remain unapproved planning material")
    _text(inventory["scope"], "source_inventory.scope")
    _texts(inventory["constraints"], "source_inventory.constraints")
    _texts(inventory["validation_checks"], "source_inventory.validation_checks")

    layers = {}
    layer_keys = {
        "source_id", "local_path", "content_sha256", "language", "layer", "edition",
        "pinned_version", "source_refs", "rights_fact_sha256", "rights_notice_path",
        "rights_notice_sha256", "permission_ref", "training_input_recommendation",
        "limits", "review_status", "expert_certified", "language_boundary_ref",
    }
    if not isinstance(inventory["source_layers"], list) or not inventory["source_layers"]:
        raise CandidateGPlanError("source_inventory.source_layers must be nonempty")
    for index, layer in enumerate(inventory["source_layers"]):
        label = f"source_inventory.source_layers[{index}]"
        _exact(layer, layer_keys, label)
        for field in ("source_id", "layer", "permission_ref"):
            _id(layer[field], f"{label}.{field}")
        for field in ("local_path", "edition", "pinned_version", "rights_notice_path"):
            _text(layer[field], f"{label}.{field}")
        for field in ("content_sha256", "rights_fact_sha256", "rights_notice_sha256"):
            _sha(layer[field], f"{label}.{field}")
        _language(layer["language"], label + ".language")
        _texts(layer["source_refs"], label + ".source_refs")
        _texts(layer["limits"], label + ".limits", empty=True)
        if layer["training_input_recommendation"] != (
                "conditionally_eligible_for_training_input_planning"):
            raise CandidateGPlanError(
                f"{label} is pending or lacks the exact training-input planning decision"
            )
        if layer["review_status"] != "reviewed_nonexpert" or (
                layer["expert_certified"] is not False):
            raise CandidateGPlanError(f"{label} must disclose reviewed nonexpert status")
        boundary = layer["language_boundary_ref"]
        if boundary is not None:
            _text(boundary, label + ".language_boundary_ref")
        if layer["language"] == "arc" and boundary is None:
            raise CandidateGPlanError(f"{label} requires an Aramaic language boundary ref")
        key = (layer["source_id"], layer["layer"], layer["language"])
        if key in layers:
            raise CandidateGPlanError(f"Duplicate source layer identity: {key}")
        layers[key] = layer

    family_keys = {
        "family_id", "language", "book", "chapter", "source_span", "source_id",
        "source_path", "source_sha256", "source_layer", "source_refs",
        "permission_ref", "language_boundary_ref", "prior_exposure",
    }

    def families(field, expected_count, validation):
        values = inventory[field]
        if not isinstance(values, list) or len(values) != expected_count:
            raise CandidateGPlanError(f"source_inventory.{field} must have {expected_count} entries")
        output = {}
        chapter_ids = set()
        aramaic_exceptions = 0
        for index, family in enumerate(values):
            label = f"source_inventory.{field}[{index}]"
            _exact(family, family_keys, label)
            _id(family["family_id"], label + ".family_id")
            if family["family_id"] in output:
                raise CandidateGPlanError(f"Duplicate family_id: {family['family_id']}")
            _language(family["language"], label + ".language")
            for name in ("book", "source_span", "source_path"):
                _text(family[name], f"{label}.{name}")
            _chapter(family["chapter"], label + ".chapter")
            chapter_id = _chapter_key(family)
            if chapter_id in chapter_ids:
                raise CandidateGPlanError(
                    f"Duplicate canonical chapter identity in {field}: {chapter_id}"
                )
            chapter_ids.add(chapter_id)
            for name in ("source_id", "source_layer", "permission_ref"):
                _id(family[name], f"{label}.{name}")
            _sha(family["source_sha256"], label + ".source_sha256")
            _texts(family["source_refs"], label + ".source_refs")
            _validate_prior_exposure(family["prior_exposure"], label + ".prior_exposure")
            layer = layers.get((family["source_id"], family["source_layer"], family["language"]))
            if layer is None:
                raise CandidateGPlanError(f"{label} references an unexpected source/language layer")
            for family_name, layer_name in (
                    ("source_path", "local_path"), ("source_sha256", "content_sha256"),
                    ("permission_ref", "permission_ref"),
                    ("language_boundary_ref", "language_boundary_ref")):
                if family[family_name] != layer[layer_name]:
                    raise CandidateGPlanError(f"{label}.{family_name} mismatches source layer")
            if not set(family["source_refs"]).issubset(layer["source_refs"]):
                raise CandidateGPlanError(f"{label}.source_refs are not bound to source layer")
            exposure = family["prior_exposure"]
            exception = exposure["validation_exposure_exception"]
            if not validation and exception is not None:
                raise CandidateGPlanError(f"{label} training family cannot claim validation exception")
            if validation and family["language"] in {"hbo", "grc"}:
                if exposure["in_prior_english_training"] or exposure["in_prior_evaluation"]:
                    raise CandidateGPlanError(
                        f"{label} Hebrew/Greek validation family has protected prior exposure"
                    )
                if exception is not None:
                    raise CandidateGPlanError(f"{label} has an unnecessary validation exception")
            if validation and family["language"] == "arc":
                if not (exposure["in_prior_english_training"] or exposure["in_prior_evaluation"]):
                    raise CandidateGPlanError(
                        f"{label} Aramaic exception must disclose actual prior exposure"
                    )
                if exception is None:
                    raise CandidateGPlanError(
                        f"{label} requires a documented Aramaic validation exposure exception"
                    )
                aramaic_exceptions += 1
            output[family["family_id"]] = family
        if validation and aramaic_exceptions != 2:
            raise CandidateGPlanError("Exactly two Aramaic validation exposure exceptions are required")
        return output

    train_families = families("training_families", 40, False)
    validation_families = families("validation_families", 12, True)
    if set(train_families) & set(validation_families):
        raise CandidateGPlanError("Training and validation family IDs overlap")

    rehearsal_keys = {
        "rehearsal_row_id", "old_row_id", "old_split", "old_dataset_path",
        "prepared_path", "full_row_sha256", "family_id", "language", "book",
        "chapter", "source_span", "source_id", "source_path", "source_sha256",
        "source_layer", "source_refs", "permission_ref", "language_boundary_ref",
    }
    rehearsals = {}
    if not isinstance(inventory["rehearsal_rows"], list) or len(
            inventory["rehearsal_rows"]) != 16:
        raise CandidateGPlanError("source_inventory.rehearsal_rows must have 16 entries")
    old_ids = set()
    for index, row in enumerate(inventory["rehearsal_rows"]):
        label = f"source_inventory.rehearsal_rows[{index}]"
        _exact(row, rehearsal_keys, label)
        for name in ("rehearsal_row_id", "old_row_id", "family_id", "source_id",
                     "source_layer", "permission_ref"):
            _id(row[name], f"{label}.{name}")
        if row["rehearsal_row_id"] in rehearsals or row["old_row_id"] in old_ids:
            raise CandidateGPlanError("Duplicate rehearsal or old row ID")
        if row["old_split"] != "train":
            raise CandidateGPlanError(f"{label} must bind an eligible old train row, not validation")
        for name in ("old_dataset_path", "prepared_path", "book",
                     "source_span", "source_path"):
            _text(row[name], f"{label}.{name}")
        _chapter(row["chapter"], label + ".chapter")
        for name in ("full_row_sha256", "source_sha256"):
            _sha(row[name], f"{label}.{name}")
        _language(row["language"], label + ".language")
        _texts(row["source_refs"], label + ".source_refs")
        layer = layers.get((row["source_id"], row["source_layer"], row["language"]))
        if layer is None:
            raise CandidateGPlanError(f"{label} references an unexpected source/language layer")
        for row_name, layer_name in (
                ("source_path", "local_path"), ("source_sha256", "content_sha256"),
                ("permission_ref", "permission_ref"),
                ("language_boundary_ref", "language_boundary_ref")):
            if row[row_name] != layer[layer_name]:
                raise CandidateGPlanError(f"{label}.{row_name} mismatches source layer")
        if not set(row["source_refs"]).issubset(layer["source_refs"]):
            raise CandidateGPlanError(f"{label}.source_refs are not bound to source layer")
        rehearsals[row["rehearsal_row_id"]] = row
        old_ids.add(row["old_row_id"])

    exclusion_keys = {
        "exclusion_id", "source_id", "family_id", "source_path", "book", "chapter",
        "reason", "applies_to",
    }
    exclusions = []
    exclusion_ids = set()
    if not isinstance(inventory["exclusions"], list):
        raise CandidateGPlanError("source_inventory.exclusions must be a list")
    for index, exclusion in enumerate(inventory["exclusions"]):
        label = f"source_inventory.exclusions[{index}]"
        _exact(exclusion, exclusion_keys, label)
        _id(exclusion["exclusion_id"], label + ".exclusion_id")
        if exclusion["exclusion_id"] in exclusion_ids:
            raise CandidateGPlanError("Duplicate exclusion_id")
        for name in ("source_id", "family_id"):
            if exclusion[name] is not None:
                _id(exclusion[name], f"{label}.{name}")
        for name in ("source_path", "book", "chapter"):
            if exclusion[name] is not None:
                _text(exclusion[name], f"{label}.{name}")
        if all(exclusion[name] is None for name in (
                "source_id", "family_id", "source_path", "book", "chapter")):
            raise CandidateGPlanError(f"{label} must have an exclusion selector")
        _text(exclusion["reason"], label + ".reason")
        if (not isinstance(exclusion["applies_to"], list)
                or not exclusion["applies_to"]
                or not set(exclusion["applies_to"]).issubset({"training", "validation"})):
            raise CandidateGPlanError(f"{label}.applies_to is invalid")
        exclusions.append(exclusion)
        exclusion_ids.add(exclusion["exclusion_id"])

    _exact(inventory["counts"], {
        "source_layers", "training_families", "validation_families", "rehearsal_rows",
    }, "source_inventory.counts")
    actual_counts = {
        "source_layers": len(layers), "training_families": len(train_families),
        "validation_families": len(validation_families), "rehearsal_rows": len(rehearsals),
    }
    if inventory["counts"] != actual_counts:
        raise CandidateGPlanError("source_inventory.counts mismatch actual inventory")
    return layers, train_families, validation_families, rehearsals, exclusions


def _validate_permissions(permission_inventory, layers):
    _json(permission_inventory, "permission_inventory")
    _exact(permission_inventory, {
        "schema_version", "artifact_kind", "status", "decisions",
    }, "permission_inventory")
    if permission_inventory["schema_version"] != SCHEMA_VERSION:
        raise CandidateGPlanError("Unsupported permission inventory schema_version")
    if permission_inventory["artifact_kind"] != "candidate_g_training_input_permissions_v1":
        raise CandidateGPlanError("Unexpected permission inventory artifact_kind")
    if permission_inventory["status"] != "reviewed_for_input_planning":
        raise CandidateGPlanError("Permission inventory status is not input-planning review")
    keys = {
        "permission_ref", "declared_use", "decision", "source_id", "source_path",
        "source_sha256", "source_layer", "language", "rights_fact_sha256",
        "basis_refs", "limits", "review_status", "expert_certified",
    }
    decisions = {}
    if not isinstance(permission_inventory["decisions"], list):
        raise CandidateGPlanError("permission_inventory.decisions must be a list")
    for index, decision in enumerate(permission_inventory["decisions"]):
        label = f"permission_inventory.decisions[{index}]"
        _exact(decision, keys, label)
        for name in ("permission_ref", "source_id", "source_layer"):
            _id(decision[name], f"{label}.{name}")
        if decision["permission_ref"] in decisions:
            raise CandidateGPlanError("Duplicate permission_ref")
        _text(decision["source_path"], label + ".source_path")
        _sha(decision["source_sha256"], label + ".source_sha256")
        _sha(decision["rights_fact_sha256"], label + ".rights_fact_sha256")
        _language(decision["language"], label + ".language")
        _texts(decision["basis_refs"], label + ".basis_refs")
        _texts(decision["limits"], label + ".limits", empty=True)
        if decision["declared_use"] != "training_input":
            raise CandidateGPlanError(f"{label} is app-only or otherwise not training_input")
        if decision["decision"] != "conditional_input_eligible_for_plan":
            raise CandidateGPlanError(f"{label} is pending or not conditionally input-eligible")
        if decision["review_status"] != "reviewed_nonexpert" or (
                decision["expert_certified"] is not False):
            raise CandidateGPlanError(f"{label} must disclose reviewed nonexpert status")
        layer = layers.get((decision["source_id"], decision["source_layer"], decision["language"]))
        if layer is None or decision["permission_ref"] != layer["permission_ref"]:
            raise CandidateGPlanError(f"{label} does not bind a declared source layer")
        comparisons = {
            "source_path": "local_path", "source_sha256": "content_sha256",
            "rights_fact_sha256": "rights_fact_sha256",
        }
        for decision_name, layer_name in comparisons.items():
            if decision[decision_name] != layer[layer_name]:
                raise CandidateGPlanError(f"{label}.{decision_name} mismatches source/rights fact")
        decisions[decision["permission_ref"]] = decision
    for layer in layers.values():
        if layer["permission_ref"] not in decisions:
            raise CandidateGPlanError("Every source layer requires an exact training-input decision")
    return decisions


def _matches_exclusion(item, split, exclusion):
    if split not in exclusion["applies_to"]:
        return False
    selectors = ("source_id", "family_id", "source_path", "book", "chapter")
    return all(exclusion[name] is None or item.get(name) == exclusion[name]
               for name in selectors)


def validate_plan(plan, source_inventory, permission_inventory):
    """Validate and summarize an un-authored Candidate G source/row plan.

    Success establishes schema, count, linkage, split, hash, declared-permission,
    exposure, and exclusion consistency only.  It is not confirmation of file
    bytes, source accuracy, license interpretation, target quality, or readiness
    or authorization to train.
    """
    _json(plan, "plan")
    _forbid_authored_content(plan)
    _exact(plan, {
        "schema_version", "artifact_kind", "status", "scope", "training_ready",
        "training_authorized", "questions_authored", "targets_authored",
        "training_rows", "validation_rows", "language_family_quotas", "constraints",
    }, "plan")
    if plan["schema_version"] != SCHEMA_VERSION:
        raise CandidateGPlanError("Unsupported plan schema_version")
    if plan["artifact_kind"] != "candidate_g_source_row_plan_v1":
        raise CandidateGPlanError("Unexpected plan artifact_kind")
    if plan["status"] != "planning_only_unapproved":
        raise CandidateGPlanError("Plan must remain planning-only and unapproved")
    _text(plan["scope"], "plan.scope")
    _texts(plan["constraints"], "plan.constraints")
    for flag in ("training_ready", "training_authorized", "questions_authored", "targets_authored"):
        if plan[flag] is not False:
            raise CandidateGPlanError(f"plan.{flag} must remain false")
    _exact(plan["language_family_quotas"], {"training", "validation"},
           "plan.language_family_quotas")
    if plan["language_family_quotas"] != FAMILY_LANGUAGE_QUOTAS:
        raise CandidateGPlanError("Plan language family quotas differ from settled inventory quotas")

    layers, train_families, val_families, rehearsals, exclusions = (
        _validate_source_inventory(source_inventory)
    )
    permissions = _validate_permissions(permission_inventory, layers)

    for family, split in [*( (x, "training") for x in train_families.values()),
                          *( (x, "validation") for x in val_families.values())]:
        if any(_matches_exclusion(family, split, exclusion) for exclusion in exclusions):
            raise CandidateGPlanError(
                f"Family {family['family_id']} matches a protected exclusion"
            )

    train_chapters = {_chapter_key(family) for family in train_families.values()}
    train_chapters.update(_chapter_key(row) for row in rehearsals.values())
    validation_chapters = {_chapter_key(family) for family in val_families.values()}
    overlap = sorted(train_chapters & validation_chapters)
    if overlap:
        raise CandidateGPlanError(f"Training/rehearsal and validation chapters overlap: {overlap}")

    family_counts = {
        "training": Counter(f["language"] for f in train_families.values()),
        "validation": Counter(f["language"] for f in val_families.values()),
    }
    for split in ("training", "validation"):
        if dict(family_counts[split]) != FAMILY_LANGUAGE_QUOTAS[split]:
            raise CandidateGPlanError(f"{split} family language quota mismatch")

    row_keys = {
        "row_id", "split", "group", "family_id", "language", "book", "chapter",
        "source_span", "source_id", "source_path", "source_sha256", "source_layer",
        "source_refs", "permission_ref", "language_boundary_ref", "rehearsal_row_id",
        "full_row_sha256",
    }
    seen_row_ids = set()
    used_new_train = Counter()
    used_validation = Counter()
    used_rehearsals = Counter()

    def rows(field, split, expected, groups):
        values = plan[field]
        if not isinstance(values, list) or len(values) != expected:
            raise CandidateGPlanError(f"plan.{field} must have {expected} entries")
        group_counts = Counter()
        language_counts = Counter()
        for index, row in enumerate(values):
            label = f"plan.{field}[{index}]"
            _exact(row, row_keys, label)
            _id(row["row_id"], label + ".row_id")
            if row["row_id"] in seen_row_ids:
                raise CandidateGPlanError(f"Duplicate row_id: {row['row_id']}")
            seen_row_ids.add(row["row_id"])
            if row["split"] != split or row["group"] not in groups:
                raise CandidateGPlanError(f"{label} split/group is invalid")
            _language(row["language"], label + ".language")
            for name in ("family_id", "source_id", "source_layer", "permission_ref"):
                _id(row[name], f"{label}.{name}")
            for name in ("book", "source_span", "source_path"):
                _text(row[name], f"{label}.{name}")
            _chapter(row["chapter"], label + ".chapter")
            _sha(row["source_sha256"], label + ".source_sha256")
            _texts(row["source_refs"], label + ".source_refs")
            if row["language_boundary_ref"] is not None:
                _text(row["language_boundary_ref"], label + ".language_boundary_ref")
            if row["group"] == "rehearsal":
                if split != "train":
                    raise CandidateGPlanError("Validation rows cannot be rehearsal rows")
                if row["rehearsal_row_id"] is None or row["full_row_sha256"] is None:
                    raise CandidateGPlanError(f"{label} lacks exact rehearsal binding")
                _id(row["rehearsal_row_id"], label + ".rehearsal_row_id")
                _sha(row["full_row_sha256"], label + ".full_row_sha256")
                rehearsal = rehearsals.get(row["rehearsal_row_id"])
                if rehearsal is None:
                    raise CandidateGPlanError(f"{label} references unknown rehearsal row")
                expected_values = {key: rehearsal[key] for key in (
                    "family_id", "language", "book", "chapter", "source_span", "source_id",
                    "source_path", "source_sha256", "source_layer", "source_refs",
                    "permission_ref", "language_boundary_ref", "full_row_sha256",
                )}
                if any(row[key] != value for key, value in expected_values.items()):
                    raise CandidateGPlanError(f"{label} mutates an exact old rehearsal row binding")
                if any(_matches_exclusion(row, "training", ex) for ex in exclusions):
                    raise CandidateGPlanError(f"{label} matches a protected exclusion")
                used_rehearsals[row["rehearsal_row_id"]] += 1
            else:
                if row["rehearsal_row_id"] is not None or row["full_row_sha256"] is not None:
                    raise CandidateGPlanError(f"{label} new row has rehearsal-only fields")
                families_for_split = train_families if split == "train" else val_families
                family = families_for_split.get(row["family_id"])
                if family is None:
                    raise CandidateGPlanError(f"{label} references an unexpected split family")
                expected_values = {key: family[key] for key in (
                    "family_id", "language", "book", "chapter", "source_span", "source_id",
                    "source_path", "source_sha256", "source_layer", "source_refs",
                    "permission_ref", "language_boundary_ref",
                )}
                if any(row[key] != value for key, value in expected_values.items()):
                    raise CandidateGPlanError(f"{label} has stale or mismatched family/source binding")
                if any(_matches_exclusion(row, "training" if split == "train" else "validation", ex)
                       for ex in exclusions):
                    raise CandidateGPlanError(f"{label} matches a protected exclusion")
                (used_new_train if split == "train" else used_validation)[row["family_id"]] += 1
            if row["permission_ref"] not in permissions:
                raise CandidateGPlanError(f"{label} lacks exact training-input permission")
            group_counts[row["group"]] += 1
            language_counts[row["language"]] += 1
        if dict(group_counts) != groups:
            raise CandidateGPlanError(f"plan.{field} group counts mismatch: {dict(group_counts)}")
        return dict(language_counts)

    train_languages = rows("training_rows", "train", 96, TRAIN_GROUPS)
    validation_languages = rows(
        "validation_rows", "validation", 24, VALIDATION_GROUPS
    )
    if used_new_train != Counter({family_id: 2 for family_id in train_families}):
        raise CandidateGPlanError("Each of 40 new training families must supply exactly two rows")
    if used_validation != Counter({family_id: 2 for family_id in val_families}):
        raise CandidateGPlanError("Each of 12 validation families must supply exactly two rows")
    if used_rehearsals != Counter({row_id: 1 for row_id in rehearsals}):
        raise CandidateGPlanError("Each exact old rehearsal row must be used once")

    return {
        "schema_version": SCHEMA_VERSION,
        "artifact_kind": "candidate_g_plan_mechanical_validation_v1",
        "status": "mechanically_valid_plan_not_training_ready",
        "counts": {
            "training_rows": 96, "validation_rows": 24,
            "new_training_families": 40, "validation_families": 12,
            "rehearsal_rows": 16,
        },
        "training_group_counts": dict(TRAIN_GROUPS),
        "validation_group_counts": dict(VALIDATION_GROUPS),
        "family_language_quotas": FAMILY_LANGUAGE_QUOTAS,
        "row_language_counts": {
            "training": train_languages, "validation": validation_languages,
        },
        "checks": {
            "chapter_disjoint_including_rehearsal": True,
            "protected_exclusions_absent": True,
            "exact_source_and_permission_linkage": True,
            "old_train_rehearsal_bindings_match_caller_inventory": True,
            "questions_or_targets_present": False,
            "training_ready": False,
            "training_authorized": False,
        },
        "limitations": [
            "Mechanical validity does not verify current disk bytes, source accuracy, language labeling, license interpretation, permission truth, or scholarly quality.",
            "Input-planning eligibility does not approve future English targets or make the plan training-ready.",
            "Rehearsal validation confirms agreement with the caller-supplied inventory; it does not independently confirm old-train membership or file bytes.",
            "No question, answer, target, preparer, provider, model, or training operation is performed.",
        ],
    }
