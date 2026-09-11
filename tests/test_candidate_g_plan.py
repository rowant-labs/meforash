"""Constructed tests for the Candidate G source/row plan validator."""
import copy
import hashlib
import unittest

from bibleprep.candidate_g_plan import CandidateGPlanError, validate_plan


def sha(label):
    return hashlib.sha256(label.encode()).hexdigest()


class CandidateGPlanTests(unittest.TestCase):
    def setUp(self):
        self.layers = {}
        source_layers = []
        decisions = []
        for language in ("hbo", "grc", "arc"):
            short = language
            source_id = f"source-{short}"
            layer_id = f"original-{short}"
            path = f"sources/{short}.txt"
            permission = f"permission-{short}"
            boundary = "Daniel.2.4b-7.28" if language == "arc" else None
            layer = {
                "source_id": source_id,
                "local_path": path,
                "content_sha256": sha(path),
                "language": language,
                "layer": layer_id,
                "edition": f"Pinned {language} edition",
                "pinned_version": "fixture-v1",
                "source_refs": [f"ref:{short}"],
                "rights_fact_sha256": sha("rights-" + short),
                "rights_notice_path": f"sources/{short}-NOTICE.txt",
                "rights_notice_sha256": sha("notice-" + short),
                "permission_ref": permission,
                "training_input_recommendation": (
                    "conditionally_eligible_for_training_input_planning"
                ),
                "limits": ["Constructed fixture only."],
                "review_status": "reviewed_nonexpert",
                "expert_certified": False,
                "language_boundary_ref": boundary,
            }
            source_layers.append(layer)
            self.layers[language] = layer
            decisions.append({
                "permission_ref": permission,
                "declared_use": "training_input",
                "decision": "conditional_input_eligible_for_plan",
                "source_id": source_id,
                "source_path": path,
                "source_sha256": sha(path),
                "source_layer": layer_id,
                "language": language,
                "rights_fact_sha256": sha("rights-" + short),
                "basis_refs": [f"rights:{short}"],
                "limits": ["Input planning only."],
                "review_status": "reviewed_nonexpert",
                "expert_certified": False,
            })

        def family(language, number, validation=False):
            layer = self.layers[language]
            prefix = "val" if validation else "train"
            chapter = str(number + (100 if validation else 0))
            exposed = validation and language == "arc"
            return {
                "family_id": f"{prefix}-{language.lower()}-{number:02d}",
                "language": language,
                "book": f"{language}Book",
                "chapter": chapter,
                "source_span": f"{language}Book.{chapter}.1-10",
                "source_id": layer["source_id"],
                "source_path": layer["local_path"],
                "source_sha256": layer["content_sha256"],
                "source_layer": layer["layer"],
                "source_refs": list(layer["source_refs"]),
                "permission_ref": layer["permission_ref"],
                "language_boundary_ref": layer["language_boundary_ref"],
                "prior_exposure": {
                    "in_b_raw_text": True,
                    "in_prior_english_training": exposed,
                    "in_prior_evaluation": exposed,
                    "in_project_research": exposed,
                    "validation_exposure_exception": (
                        "Scarce Aramaic family; explicitly known prior development exposure."
                        if exposed else None
                    ),
                },
            }

        train_families = []
        for language, count in (("hbo", 22), ("grc", 14), ("arc", 4)):
            train_families += [family(language, n) for n in range(1, count + 1)]
        validation_families = []
        for language, count in (("hbo", 6), ("grc", 4), ("arc", 2)):
            validation_families += [
                family(language, n, validation=True) for n in range(1, count + 1)
            ]

        rehearsal_rows = []
        for n in range(16):
            language = ("hbo", "grc", "arc")[n % 3]
            layer = self.layers[language]
            chapter = str(201 + n)
            rehearsal_rows.append({
                "rehearsal_row_id": f"rehearsal-{n:02d}",
                "old_row_id": f"old-train-{n:02d}",
                "old_split": "train",
                "old_dataset_path": "old/train.jsonl",
                "prepared_path": f"old/prepared/{n:02d}.json",
                "full_row_sha256": sha(f"old-row-{n}"),
                "family_id": f"old-family-{n:02d}",
                "language": language,
                "book": f"Rehearsal{language}Book",
                "chapter": chapter,
                "source_span": f"Rehearsal{language}Book.{chapter}.1-10",
                "source_id": layer["source_id"],
                "source_path": layer["local_path"],
                "source_sha256": layer["content_sha256"],
                "source_layer": layer["layer"],
                "source_refs": list(layer["source_refs"]),
                "permission_ref": layer["permission_ref"],
                "language_boundary_ref": layer["language_boundary_ref"],
            })
        self.inventory = {
            "schema_version": 1,
            "artifact_kind": "candidate_g_source_inventory_v1",
            "status": "planning_inventory_unapproved",
            "scope": "Constructed source and family plan.",
            "source_layers": source_layers,
            "training_families": train_families,
            "validation_families": validation_families,
            "rehearsal_rows": rehearsal_rows,
            "exclusions": [],
            "constraints": ["No real training data."],
            "counts": {
                "source_layers": 3, "training_families": 40,
                "validation_families": 12, "rehearsal_rows": 16,
            },
            "validation_checks": ["Constructed bindings checked."],
        }
        self.permissions = {
            "schema_version": 1,
            "artifact_kind": "candidate_g_training_input_permissions_v1",
            "status": "reviewed_for_input_planning",
            "decisions": decisions,
        }

        def planned_row(row_id, split, group, family, rehearsal=None):
            return {
                "row_id": row_id,
                "split": split,
                "group": group,
                "family_id": family["family_id"],
                "language": family["language"],
                "book": family["book"],
                "chapter": family["chapter"],
                "source_span": family["source_span"],
                "source_id": family["source_id"],
                "source_path": family["source_path"],
                "source_sha256": family["source_sha256"],
                "source_layer": family["source_layer"],
                "source_refs": list(family["source_refs"]),
                "permission_ref": family["permission_ref"],
                "language_boundary_ref": family["language_boundary_ref"],
                "rehearsal_row_id": rehearsal["rehearsal_row_id"] if rehearsal else None,
                "full_row_sha256": rehearsal["full_row_sha256"] if rehearsal else None,
            }

        training_rows = []
        for index, family_row in enumerate(train_families):
            group = "direct" if index < 20 else "boundary" if index < 32 else "intent"
            for variant in range(2):
                training_rows.append(planned_row(
                    f"new-train-{index:02d}-{variant}", "train", group, family_row
                ))
        for index, rehearsal in enumerate(rehearsal_rows):
            training_rows.append(planned_row(
                f"rehearsal-plan-{index:02d}", "train", "rehearsal", rehearsal,
                rehearsal=rehearsal,
            ))
        validation_rows = []
        for index, family_row in enumerate(validation_families):
            group = "direct" if index < 6 else "boundary" if index < 9 else "intent"
            for variant in range(2):
                validation_rows.append(planned_row(
                    f"validation-{index:02d}-{variant}", "validation", group, family_row
                ))
        self.plan = {
            "schema_version": 1,
            "artifact_kind": "candidate_g_source_row_plan_v1",
            "status": "planning_only_unapproved",
            "scope": "Constructed 96/24 source and row plan without authored content.",
            "training_ready": False,
            "training_authorized": False,
            "questions_authored": False,
            "targets_authored": False,
            "training_rows": training_rows,
            "validation_rows": validation_rows,
            "language_family_quotas": {
                "training": {"hbo": 22, "grc": 14, "arc": 4},
                "validation": {"hbo": 6, "grc": 4, "arc": 2},
            },
            "constraints": ["Mechanical fixture; no training authorization."],
        }

    def validate(self, plan=None, inventory=None, permissions=None):
        return validate_plan(
            self.plan if plan is None else plan,
            self.inventory if inventory is None else inventory,
            self.permissions if permissions is None else permissions,
        )

    def test_valid_plan_has_exact_counts_and_is_not_training_ready(self):
        result = self.validate()
        self.assertEqual(result["counts"]["training_rows"], 96)
        self.assertEqual(result["counts"]["validation_rows"], 24)
        self.assertFalse(result["checks"]["training_ready"])
        self.assertEqual(result["training_group_counts"], {
            "direct": 40, "boundary": 24, "intent": 16, "rehearsal": 16,
        })

    def test_count_and_duplicate_row_fail(self):
        plan = copy.deepcopy(self.plan)
        plan["training_rows"].pop()
        with self.assertRaisesRegex(CandidateGPlanError, "96 entries"):
            self.validate(plan=plan)
        plan = copy.deepcopy(self.plan)
        plan["validation_rows"][0]["row_id"] = plan["training_rows"][0]["row_id"]
        with self.assertRaisesRegex(CandidateGPlanError, "Duplicate row_id"):
            self.validate(plan=plan)

    def test_validation_chapter_cannot_overlap_new_or_rehearsal_training(self):
        inventory = copy.deepcopy(self.inventory)
        family = inventory["validation_families"][0]
        family["book"] = inventory["rehearsal_rows"][0]["book"]
        family["chapter"] = inventory["rehearsal_rows"][0]["chapter"]
        with self.assertRaisesRegex(CandidateGPlanError, "chapters overlap"):
            self.validate(inventory=inventory)

    def test_each_new_family_requires_a_distinct_canonical_chapter(self):
        inventory = copy.deepcopy(self.inventory)
        inventory["training_families"][1]["book"] = (
            inventory["training_families"][0]["book"]
        )
        inventory["training_families"][1]["chapter"] = (
            inventory["training_families"][0]["chapter"]
        )
        with self.assertRaisesRegex(CandidateGPlanError, "Duplicate canonical chapter"):
            self.validate(inventory=inventory)
        inventory = copy.deepcopy(self.inventory)
        inventory["validation_families"][0]["chapter"] = "0101"
        with self.assertRaisesRegex(CandidateGPlanError, "without leading zeroes"):
            self.validate(inventory=inventory)

    def test_rehearsal_requires_old_train_and_exact_full_row_hash(self):
        inventory = copy.deepcopy(self.inventory)
        inventory["rehearsal_rows"][0]["old_split"] = "validation"
        with self.assertRaisesRegex(CandidateGPlanError, "old train row"):
            self.validate(inventory=inventory)
        plan = copy.deepcopy(self.plan)
        plan["training_rows"][-1]["full_row_sha256"] = sha("mutated")
        with self.assertRaisesRegex(CandidateGPlanError, "mutates"):
            self.validate(plan=plan)

    def test_validation_cannot_accept_rehearsal_group(self):
        plan = copy.deepcopy(self.plan)
        plan["validation_rows"][0]["group"] = "rehearsal"
        with self.assertRaisesRegex(CandidateGPlanError, "split/group"):
            self.validate(plan=plan)

    def test_stale_source_hash_and_rights_mismatch_fail(self):
        plan = copy.deepcopy(self.plan)
        plan["training_rows"][0]["source_sha256"] = sha("stale")
        with self.assertRaisesRegex(CandidateGPlanError, "stale or mismatched"):
            self.validate(plan=plan)
        permissions = copy.deepcopy(self.permissions)
        permissions["decisions"][0]["rights_fact_sha256"] = sha("wrong-rights")
        with self.assertRaisesRegex(CandidateGPlanError, "rights fact"):
            self.validate(permissions=permissions)

    def test_forbidden_answer_question_or_target_fields_fail(self):
        for field in ("answer_text", "question", "target"):
            plan = copy.deepcopy(self.plan)
            plan["training_rows"][0][field] = "Forbidden authored content."
            with self.assertRaisesRegex(CandidateGPlanError, "forbidden"):
                self.validate(plan=plan)

    def test_pending_or_app_only_permission_is_not_training_input_clearance(self):
        permissions = copy.deepcopy(self.permissions)
        permissions["decisions"][0]["declared_use"] = "app_display"
        with self.assertRaisesRegex(CandidateGPlanError, "app-only"):
            self.validate(permissions=permissions)
        inventory = copy.deepcopy(self.inventory)
        inventory["source_layers"][0]["training_input_recommendation"] = "pending"
        with self.assertRaisesRegex(CandidateGPlanError, "pending"):
            self.validate(inventory=inventory)

    def test_unexpected_source_and_aramaic_boundary_fail(self):
        inventory = copy.deepcopy(self.inventory)
        inventory["training_families"][0]["source_id"] = "unlisted-source"
        with self.assertRaisesRegex(CandidateGPlanError, "unexpected source"):
            self.validate(inventory=inventory)
        inventory = copy.deepcopy(self.inventory)
        aramaic = next(x for x in inventory["source_layers"] if x["language"] == "arc")
        aramaic["language_boundary_ref"] = None
        with self.assertRaisesRegex(CandidateGPlanError, "Aramaic language boundary"):
            self.validate(inventory=inventory)

    def test_protected_exclusion_and_exposure_rules_fail_closed(self):
        inventory = copy.deepcopy(self.inventory)
        victim = inventory["rehearsal_rows"][0]
        inventory["exclusions"].append({
            "exclusion_id": "protected-heldout-chapter",
            "source_id": None,
            "family_id": None,
            "source_path": None,
            "book": victim["book"],
            "chapter": victim["chapter"],
            "reason": "Frozen validation or evaluation holdout.",
            "applies_to": ["training"],
        })
        with self.assertRaisesRegex(CandidateGPlanError, "protected exclusion"):
            self.validate(inventory=inventory)
        inventory = copy.deepcopy(self.inventory)
        family = next(x for x in inventory["validation_families"]
                      if x["language"] == "hbo")
        family["prior_exposure"]["in_prior_english_training"] = True
        with self.assertRaisesRegex(CandidateGPlanError, "protected prior exposure"):
            self.validate(inventory=inventory)

    def test_exactly_two_declared_aramaic_validation_exceptions_required(self):
        inventory = copy.deepcopy(self.inventory)
        aramaic = next(x for x in inventory["validation_families"]
                       if x["language"] == "arc")
        aramaic["prior_exposure"]["validation_exposure_exception"] = None
        with self.assertRaisesRegex(CandidateGPlanError, "documented Aramaic"):
            self.validate(inventory=inventory)


if __name__ == "__main__":
    unittest.main()
