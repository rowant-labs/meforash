"""Constructed offline tests for two-condition native preparation and collection."""
from __future__ import annotations

import copy
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import unittest

from bibleprep.evidence_guidance_comparison import prepare_comparison_pair
from bibleprep.guidance_collection import (
    GuidanceCollectionError,
    canonical_sha256,
    collect_sequential,
    prepare_native_requests,
    verify_collection_run,
    verify_prepared_requests,
)
from tests import test_evidence_answer_context as answer_context_tests


class FakeRenderer:
    def __init__(self):
        self.calls = 0
        self.provenance = {
            "fixture_kind": "constructed_fake_native_renderer",
            "production_renderer": False,
        }

    def render(self, messages, effort):
        self.calls += 1
        raw = json.dumps(
            {"messages": messages, "effort": effort},
            ensure_ascii=False, sort_keys=True, separators=(",", ":"),
        ).encode("utf-8")
        return list(hashlib.sha256(raw).digest())


class FakeTransport:
    def __init__(self, prepared, outcomes):
        self.requests = list(prepared["prepared_requests"])
        self.outcomes = list(outcomes)
        self.calls = 0
        self.configs = []
        self.closed = False

    def __call__(self, payload, config, secret):
        index = self.calls
        self.calls += 1
        self.configs.append(copy.deepcopy(config))
        outcome = self.outcomes[index]
        if isinstance(outcome, Exception):
            raise outcome
        request = self.requests[index]
        normalized = {
            "stop_reason": outcome.get("stop_reason", "stop"),
            "final_text": outcome.get("final_text", "Complete constructed answer."),
            "diagnostic_sha256": hashlib.sha256(f"diagnostic-{index}".encode()).hexdigest(),
            "raw_generated_token_ids_sha256": hashlib.sha256(f"output-{index}".encode()).hexdigest(),
            "native_prompt_sha256": outcome.get(
                "native_prompt_sha256", request["prompt_token_ids_sha256"]
            ),
        }
        return {
            "model": "thinkingmachines/Inkling",
            "usage": {
                "prompt_tokens": request["exact_input_tokens"],
                "completion_tokens": outcome.get("completion_tokens", 7),
            },
            "native_tinker": {"prompt_sha256": request["prompt_token_ids_sha256"]},
            "constructed_normalized": normalized,
        }

    def close(self):
        self.closed = True


def fake_normalize(response, _run_dir):
    return copy.deepcopy(response["constructed_normalized"])


class GuidanceCollectionTests(unittest.TestCase):
    def setUp(self):
        self.fixture = answer_context_tests.EvidenceAnswerContextTests(
            "test_exact_three_field_shape_and_existing_evidence_are_preserved"
        )
        self.fixture.setUp()
        self.root = self.fixture.root
        (self.root / "runs").mkdir(exist_ok=True)
        checkpoint = self.root / "runs/checkpoint-B.json"
        checkpoint.write_text(
            json.dumps({"sampler_path": "synthetic://fixture/retained-B"}) + "\n",
            encoding="utf-8",
        )
        sampler = "synthetic://fixture/retained-B"
        self.model_reference = {
            "model": "thinkingmachines/Inkling",
            "checkpoint_id": "retained-B-original-text-only",
            "state": "original_text_lora_adapter",
            "checkpoint_reference_file": "runs/checkpoint-B.json",
            "checkpoint_reference_sha256": hashlib.sha256(checkpoint.read_bytes()).hexdigest(),
            "adapter_sampler_path": sampler,
            "sampler_path_sha256": hashlib.sha256(sampler.encode()).hexdigest(),
        }
        self.protocol_bindings = {
            "protocol_sha256": hashlib.sha256(b"synthetic protocol").hexdigest(),
            "criteria_sha256": hashlib.sha256(b"synthetic criteria").hexdigest(),
            "review_plan_sha256": hashlib.sha256(b"synthetic review plan").hexdigest(),
        }
        self.settings = {
            "effort": 0.7,
            "reasoning_effort": "medium",
            "temperature": 0.0,
            "seed": 1702,
            "input_token_limit": 1000,
            "max_tokens": 100,
            "deadline_seconds": 300,
            "prompt_date": "2026-09-09",
        }
        evidence_inputs = {
            "case_id": "synthetic-evidence-case",
            "system_prompt": "Constructed system policy.",
            "question": "Synthetic question about supplied fixture evidence?",
            "selected_component_keys": [
                "SYNTHETIC01/claim-Q1", "SYNTHETIC01/reading-R1",
            ],
            "verified": self.fixture.verified,
            "registry": self.fixture.registry,
            "notice_manifest": self.fixture.manifest,
            "root": self.fixture.root,
            "record_directory": self.fixture.directory,
        }
        control_inputs = {
            **evidence_inputs,
            "case_id": "synthetic-general-control",
            "question": "Synthetic general control question?",
            "selected_component_keys": [],
            "verified": None,
            "general_control": True,
        }
        self.case_specs = [
            {
                "pair_inputs": evidence_inputs,
                "prepared_pair": prepare_comparison_pair(**evidence_inputs),
            },
            {
                "pair_inputs": control_inputs,
                "prepared_pair": prepare_comparison_pair(**control_inputs),
            },
        ]
        self.renderer = FakeRenderer()
        self.prepare_kwargs = {
            "model_reference": self.model_reference,
            "protocol_bindings": self.protocol_bindings,
            "settings": self.settings,
            "input_rate_usd_per_million": Decimal("1"),
            "output_rate_usd_per_million": Decimal("2"),
            "allowance_usd": Decimal("0.01"),
            "comparison_manifest": "manifests/comparison-large-models-v1.json",
            "renderer": self.renderer,
            "root": self.root,
        }
        self.prepared = prepare_native_requests(self.case_specs, **self.prepare_kwargs)

    def tearDown(self):
        self.fixture.tearDown()

    def test_preparation_has_only_two_conditions_alternating_order_and_full_reservation(self):
        slots = self.prepared["planned_slots"]
        self.assertEqual(self.prepared["planned_slot_count"], 4)
        self.assertEqual(
            [slot["condition_id"] for slot in slots],
            ["B-original", "B-guided", "B-guided", "B-original"],
        )
        self.assertEqual([slot["case_id"] for slot in slots], [
            "synthetic-evidence-case", "synthetic-evidence-case",
            "synthetic-general-control", "synthetic-general-control",
        ])
        self.assertTrue(all("arm" not in slot for slot in slots))
        self.assertEqual(self.prepared["full_run_worst_case_reservation_usd"], "0.0048")
        self.assertEqual(self.prepared["protocol_bindings"], self.protocol_bindings)
        self.assertTrue(all(
            set(("slot_id", "case_id", "condition_id", "general_control", "question"))
            <= set(slot) for slot in slots
        ))
        self.assertTrue(verify_prepared_requests(
            self.case_specs, self.prepared, **self.prepare_kwargs
        ))

    def test_budget_and_stale_pair_checkpoint_and_prompt_fail_closed(self):
        untouched = FakeRenderer()
        with self.assertRaisesRegex(GuidanceCollectionError, "full-run"):
            prepare_native_requests(
                self.case_specs,
                **{**self.prepare_kwargs, "allowance_usd": Decimal("0.0047"),
                   "renderer": untouched},
            )
        self.assertEqual(untouched.calls, 0)

        with self.assertRaisesRegex(GuidanceCollectionError, "numeric effort"):
            prepare_native_requests(
                self.case_specs,
                **{**self.prepare_kwargs,
                   "settings": {**self.settings, "effort": 0.37}},
            )

        stale_specs = copy.deepcopy(self.case_specs)
        stale_specs[0]["pair_inputs"]["question"] = "Changed question."
        with self.assertRaisesRegex(GuidanceCollectionError, "pair regeneration"):
            prepare_native_requests(stale_specs, **self.prepare_kwargs)

        checkpoint = self.root / self.model_reference["checkpoint_reference_file"]
        saved = checkpoint.read_bytes()
        checkpoint.write_text('{"sampler_path":"synthetic://fixture/changed"}\n')
        with self.assertRaisesRegex(GuidanceCollectionError, "file hash"):
            prepare_native_requests(self.case_specs, **self.prepare_kwargs)
        checkpoint.write_bytes(saved)

        changed = copy.deepcopy(self.prepared)
        changed["prepared_requests"][0]["prompt_token_ids"][0] += 1
        with self.assertRaisesRegex(GuidanceCollectionError, "exact regeneration"):
            verify_prepared_requests(self.case_specs, changed, **self.prepare_kwargs)

    def test_execute_false_has_no_run_and_complete_collection_verifies(self):
        dry = self.root / "runs/dry"
        self.assertEqual(
            collect_sequential(
                self.case_specs, self.prepared, run_dir=dry, execute=False,
                renderer=self.renderer, root=self.root,
            ),
            self.prepared,
        )
        self.assertFalse(dry.exists())

        run_dir = self.root / "runs/complete"
        transport = FakeTransport(self.prepared, [{} for _ in range(4)])
        collection = collect_sequential(
            self.case_specs, self.prepared, run_dir=run_dir, execute=True,
            secret="constructed-secret", transport=transport,
            normalize=fake_normalize, renderer=self.renderer, root=self.root,
        )
        self.assertEqual([row["status"] for row in collection["results"]], ["complete"] * 4)
        self.assertEqual(len(collection["results"]), len(collection["planned_slots"]))
        self.assertEqual(transport.calls, 4)
        self.assertTrue(transport.closed)
        self.assertTrue(all(config == transport.configs[0] for config in transport.configs))
        self.assertEqual(
            verify_collection_run(
                self.case_specs, self.prepared, run_dir=run_dir,
                renderer=self.renderer, normalize=fake_normalize, root=self.root,
            ),
            collection,
        )
        with self.assertRaisesRegex(GuidanceCollectionError, "already exists"):
            collect_sequential(
                self.case_specs, self.prepared, run_dir=run_dir, execute=True,
                secret="constructed-secret", transport=FakeTransport(self.prepared, []),
                normalize=fake_normalize, renderer=self.renderer, root=self.root,
            )

    def test_partial_final_is_retained_and_later_slots_are_unsubmitted(self):
        run_dir = self.root / "runs/partial"
        transport = FakeTransport(self.prepared, [
            {}, {"stop_reason": "output_limit", "final_text": "Exact partial final.\n"},
        ])
        collection = collect_sequential(
            self.case_specs, self.prepared, run_dir=run_dir, execute=True,
            secret="constructed-secret", transport=transport,
            normalize=fake_normalize, renderer=self.renderer, root=self.root,
        )
        self.assertEqual(
            [row["status"] for row in collection["results"]],
            ["complete", "partial", "unsubmitted", "unsubmitted"],
        )
        self.assertEqual(collection["results"][1]["final_text"], "Exact partial final.\n")
        self.assertEqual(
            collection["results"][1]["final_text_sha256"],
            hashlib.sha256(b"Exact partial final.\n").hexdigest(),
        )
        self.assertEqual(transport.calls, 2)
        verify_collection_run(
            self.case_specs, self.prepared, run_dir=run_dir,
            renderer=self.renderer, normalize=fake_normalize, root=self.root,
        )

    def test_exception_empty_and_native_prompt_mismatch_stop_uncertain(self):
        scenarios = [
            ("exception", [RuntimeError("constructed")]),
            ("empty", [{"final_text": ""}]),
            ("prompt-mismatch", [{"native_prompt_sha256": "f" * 64}]),
        ]
        for name, outcomes in scenarios:
            with self.subTest(name=name):
                run_dir = self.root / f"runs/{name}"
                transport = FakeTransport(self.prepared, outcomes)
                collection = collect_sequential(
                    self.case_specs, self.prepared, run_dir=run_dir, execute=True,
                    secret="constructed-secret", transport=transport,
                    normalize=fake_normalize, renderer=self.renderer, root=self.root,
                )
                self.assertEqual(
                    [row["status"] for row in collection["results"]],
                    ["uncertain", "unsubmitted", "unsubmitted", "unsubmitted"],
                )
                self.assertIsNone(collection["results"][0]["final_text"])
                self.assertIsNotNone(collection["results"][0]["receipt_sha256"])
                self.assertEqual(transport.calls, 1)
                verify_collection_run(
                    self.case_specs, self.prepared, run_dir=run_dir,
                    renderer=self.renderer, normalize=fake_normalize, root=self.root,
                )

    def test_saved_receipt_tamper_is_rejected(self):
        run_dir = self.root / "runs/tamper"
        transport = FakeTransport(self.prepared, [{} for _ in range(4)])
        collect_sequential(
            self.case_specs, self.prepared, run_dir=run_dir, execute=True,
            secret="constructed-secret", transport=transport,
            normalize=fake_normalize, renderer=self.renderer, root=self.root,
        )
        receipt = next((run_dir / "receipts").glob("*.json"))
        receipt.write_bytes(receipt.read_bytes() + b" ")
        with self.assertRaisesRegex(GuidanceCollectionError, "receipt bytes"):
            verify_collection_run(
                self.case_specs, self.prepared, run_dir=run_dir,
                renderer=self.renderer, normalize=fake_normalize, root=self.root,
            )

    def test_saved_stop_reason_tamper_is_rejected(self):
        run_dir = self.root / "runs/stop-reason-tamper"
        transport = FakeTransport(self.prepared, [
            {"stop_reason": "output_limit", "final_text": "Partial."},
        ])
        collect_sequential(
            self.case_specs, self.prepared, run_dir=run_dir, execute=True,
            secret="constructed-secret", transport=transport,
            normalize=fake_normalize, renderer=self.renderer, root=self.root,
        )
        path = run_dir / "collection.json"
        saved = json.loads(path.read_text())
        saved["local_stop_reason"] = "invented"
        path.write_text(json.dumps(saved) + "\n")
        with self.assertRaisesRegex(GuidanceCollectionError, "stop reason"):
            verify_collection_run(
                self.case_specs, self.prepared, run_dir=run_dir,
                renderer=self.renderer, normalize=fake_normalize, root=self.root,
            )


if __name__ == "__main__":
    unittest.main()
