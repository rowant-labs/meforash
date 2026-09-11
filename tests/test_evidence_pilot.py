import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from bibleprep import evidence_pilot as pilot


class FakeTransport:
    def __init__(self, outcomes=None, fail=False):
        self.outcomes = list(outcomes or [])
        self.fail = fail
        self.calls = []
        self.closed = False

    def __call__(self, payload, config, secret):
        self.calls.append((copy.deepcopy(payload), copy.deepcopy(config), secret))
        if self.fail:
            raise TimeoutError("synthetic timeout")
        normalized = self.outcomes.pop(0) if self.outcomes else {
            "stop_reason": "stop", "final_text": "final answer",
        }
        prompt_hash = payload["prompt_hash"]
        normalized = {
            **normalized, "native_prompt_sha256": prompt_hash,
            "diagnostic_sha256": "d" * 64,
            "raw_generated_token_ids_sha256": "e" * 64,
        }
        return {
            "model": pilot.MODEL,
            "usage": {"prompt_tokens": payload["prompt_count"], "completion_tokens": 3},
            "native_tinker": {"prompt_sha256": prompt_hash},
            "normalized": normalized,
        }

    def close(self):
        self.closed = True


class EvidencePilotTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / "runs/evidence-pilot-v1").mkdir(parents=True)
        (self.root / "manifests").mkdir()
        (self.root / "manifests/model.json").write_text("{}")
        (self.root / "runs/checkpoint.json").write_text("{}")
        slots = []
        requests = []
        arms = ("B-memory", "B-packet", "B-lookup")
        for index in range(18):
            case_id = f"case-{index // 3}"
            arm = arms[index % 3]
            slot_id = case_id + "--" + arm.lower()
            slot = {"slot_id": slot_id, "case_id": case_id, "arm": arm}
            prompt_hash = hashlib.sha256(str(index).encode()).hexdigest()
            payload = {"messages": [{"role": "system", "content": "policy"},
                                    {"role": "user", "content": "question"}],
                       "prompt_hash": prompt_hash, "prompt_count": index + 10}
            request = {
                "slot_id": slot_id, "slot_sha256": pilot._canonical_sha256(slot),
                "model_input_sha256": hashlib.sha256((slot_id + "input").encode()).hexdigest(),
                "payload": payload, "payload_sha256": pilot._canonical_sha256(payload),
                "prompt_token_ids_sha256": prompt_hash, "exact_input_tokens": index + 10,
                "max_output_tokens": 8192, "worst_case_reservation_usd": "0.0536576",
            }
            slots.append(slot)
            requests.append(request)
        prepared_requests = {
            "planned_slots_sha256": pilot._canonical_sha256(slots),
            "planned_slot_count": 18, "prepared_requests": requests,
            "full_run_worst_case_reservation_usd": "0.9658368",
            "cost_basis": {"kind": "current_verified_fixture_rates"},
        }
        prepared = {"coordinated_plan": {"planned_slots": slots},
                    "prepared_requests": prepared_requests}
        self.context = {
            "root": self.root, "protocol_sha256": "a" * 64,
            "prepared": prepared, "prepared_sha256": pilot._canonical_sha256(prepared),
            "implementation_files_sha256": "b" * 64,
            "input_hashes": {"criteria": "c" * 64, "criteria_review": "f" * 64,
                             "review_plan": "1" * 64},
            "protocol": {
                "run_directory": "runs/evidence-pilot-v1/live",
                "implementation_files": {},
                "checkpoint": {"reference_file_sha256": "2" * 64,
                               "sampler_path_sha256": "3" * 64},
                "sampling": {"max_input_tokens": 8192, "max_output_tokens": 8192,
                             "timeout_seconds": 300, "reasoning_effort": "medium",
                             "temperature": 0.0, "seed": 1702},
                "execution": {"authorized_on": "2026-09-09"},
            },
            "paths": {"comparison_manifest": self.root / "manifests/model.json"},
            "checkpoint_path": self.root / "runs/checkpoint.json", "sampler": "tinker://B",
            "input_rate": pilot.Decimal("1.87"), "output_rate": pilot.Decimal("4.68"),
            "allowance": pilot.Decimal("2"),
        }

    def tearDown(self):
        self.temp.cleanup()

    def patches(self, transport, *, contexts=None):
        queue = list(contexts) if contexts is not None else None

        def load(*args, **kwargs):
            if queue is not None:
                item = queue.pop(0)
                if isinstance(item, Exception):
                    raise item
                return item
            return self.context

        return (
            mock.patch.object(pilot, "_load_context", side_effect=load),
            mock.patch.object(pilot, "_load_secret", return_value="secret"),
            mock.patch.object(pilot, "_make_transport", return_value=transport),
            mock.patch.object(pilot, "_validate_implementation_files", return_value="b" * 64),
            mock.patch.object(pilot, "_normalize_response", side_effect=lambda response, _: response["normalized"]),
        )

    def run_with(self, transport, *, contexts=None):
        patches = self.patches(transport, contexts=contexts)
        with patches[0], patches[1], patches[2], patches[3], patches[4]:
            return pilot.run_known_topic_pilot("protocol.json", "a" * 64, execute=True, root=self.root)

    def test_complete_collection_uses_exact_payload_and_native_adapter_config(self):
        transport = FakeTransport()
        result = self.run_with(transport)
        self.assertTrue(result["collection_complete"])
        self.assertEqual(len(transport.calls), 18)
        first_request = self.context["prepared"]["prepared_requests"]["prepared_requests"][0]
        self.assertEqual(transport.calls[0][0], first_request["payload"])
        self.assertEqual(transport.calls[0][1]["reasoning_effort"], "medium")
        self.assertEqual(transport.calls[0][1]["adapter_sampler_path"], "tinker://B")
        events = pilot._read_events(self.root / "runs/evidence-pilot-v1/live/events.jsonl")
        self.assertEqual(events[0], {"event": "submission", "slot_id": "case-0--b-memory"})
        self.assertEqual(result["cost_accounting"]["submitted_maximum_reservation_usd"], "0.9658368")
        self.assertTrue(transport.closed)

    def test_partial_stops_all_and_releases_unsubmitted_inventory(self):
        transport = FakeTransport([
            {"stop_reason": "stop", "final_text": "complete"},
            {"stop_reason": "output_limit", "final_text": "partial"},
        ])
        result = self.run_with(transport)
        self.assertEqual(result["audit"]["totals"], {
            "planned": 18, "complete": 1, "partial": 1, "failed": 0,
            "uncertain": 0, "outstanding": 0, "unsubmitted": 16,
        })
        self.assertEqual(result["cost_accounting"]["submitted_maximum_reservation_usd"], "0.1073152")
        self.assertEqual(result["cost_accounting"]["released_unsubmitted_reservation_usd"], "0.8585216")

    def test_uncertain_submission_is_durable_and_never_retried(self):
        transport = FakeTransport(fail=True)
        result = self.run_with(transport)
        self.assertEqual(len(transport.calls), 1)
        self.assertEqual(result["audit"]["totals"]["uncertain"], 1)
        events = pilot._read_events(self.root / "runs/evidence-pilot-v1/live/events.jsonl")
        self.assertEqual([event["event"] for event in events], ["submission", "failure"])
        self.assertIsNone(events[1]["receipt_sha256"])

    def test_changed_source_closure_before_next_attempt_stops_unsubmitted(self):
        contexts = [self.context, self.context, pilot.EvidencePilotError("stale source")]
        result = self.run_with(FakeTransport(), contexts=contexts)
        self.assertEqual(result["local_stop_reason"], "pre_submission_verification_failed")
        self.assertEqual(result["audit"]["totals"]["complete"], 1)
        self.assertEqual(result["audit"]["totals"]["unsubmitted"], 17)

    def test_setup_failure_leaves_durable_empty_journal_and_zero_submitted(self):
        with mock.patch.object(pilot, "_load_context", return_value=self.context), \
             mock.patch.object(pilot, "_load_secret", side_effect=pilot.EvidencePilotError("missing")):
            result = pilot.run_known_topic_pilot("protocol.json", "a" * 64, execute=True, root=self.root)
        self.assertEqual(result["local_stop_reason"], "pre_submission_setup_failed")
        self.assertEqual(result["audit"]["totals"]["unsubmitted"], 18)
        self.assertEqual((self.root / "runs/evidence-pilot-v1/live/events.jsonl").read_bytes(), b"")

    def test_native_output_cap_and_bool_execute_fail_closed(self):
        request = self.context["prepared"]["prepared_requests"]["prepared_requests"][0]
        response = {"model": pilot.MODEL,
                    "usage": {"prompt_tokens": request["exact_input_tokens"],
                              "completion_tokens": 8193},
                    "native_tinker": {"prompt_sha256": request["prompt_token_ids_sha256"]}}
        normalized = {"native_prompt_sha256": request["prompt_token_ids_sha256"]}
        with self.assertRaises(pilot.EvidencePilotError):
            pilot._validate_native_result(response, normalized, request)
        with self.assertRaises(pilot.EvidencePilotError):
            pilot.run_known_topic_pilot("x", "a" * 64, execute=1, root=self.root)

    def test_verifier_rejects_forged_journal_text_with_unchanged_receipt(self):
        transport = FakeTransport([
            {"stop_reason": "output_limit", "final_text": "authentic partial"},
        ])
        result = self.run_with(transport)
        run_dir = self.root / "runs/evidence-pilot-v1/live"
        events = pilot._read_events(run_dir / "events.jsonl")
        events[1]["final_text"] = "forged partial"
        (run_dir / "events.jsonl").write_text("".join(
            json.dumps(item, separators=(",", ":")) + "\n" for item in events
        ))
        forged_summary = pilot._summary(self.context, events, result["local_stop_reason"])
        (run_dir / "summary.json").write_bytes(pilot._canonical_bytes(forged_summary) + b"\n")
        patches = self.patches(transport)
        with patches[0], patches[3], patches[4], self.assertRaises(pilot.EvidencePilotError):
            pilot.verify_pilot_run("protocol.json", "a" * 64, root=self.root)


if __name__ == "__main__":
    unittest.main()
