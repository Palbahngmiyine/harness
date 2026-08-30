try:
    from .test_statekit_base import *
    from .test_statekit_01 import *
    from .test_statekit_02 import *
    from .test_statekit_03 import *
    from .test_statekit_04 import *
    from .test_statekit_05 import *
    from .test_statekit_06 import *
except ImportError:
    from test_statekit_base import *
    from test_statekit_01 import *
    from test_statekit_02 import *
    from test_statekit_03 import *
    from test_statekit_04 import *
    from test_statekit_05 import *
    from test_statekit_06 import *

class HwahapStateTests(StateFixtureMixin01, StateFixtureMixin02, StateFixtureMixin03, StateFixtureMixin04, StateFixtureMixin05, StateFixtureMixin06, unittest.TestCase):
        def test_completed_run_requires_all_completion_evidence(self) -> None:
            run_dir = self.init_run()
            contract = json.loads((run_dir / "contract.json").read_text())
            for field in hwahap_state.CONTRACT_LISTS:
                contract[field] = ["src" if field == "allowed_paths" else "test" if field == "test_commands" else "entry"]
            contract["locked"] = True
            contract["lock_sha256"] = hwahap_state.canonical_contract_digest(contract)
            run = json.loads((run_dir / "run.json").read_text())
            run.update({
                "status": "completed",
                "completed_at": "2026-08-27T00:00:00Z",
                "final_review": {"status": "pass", "attempts": [{"model": "gpt-5.6-sol", "effort": "ultra", "status": "pass", "thread_id": "final-1", "evidence": ["review"], "diff_snapshot": copy.deepcopy(self.snapshot), "diff_digest": self.snapshot["diff_digest"]}]},
            })
            run["goal_link"] = self.bound_goal_link()
            unit = self.passed_unit()
            unit_path = run_dir / "units" / "unit-1.json"
            self.write_json(run_dir / "contract.json", contract)
            self.write_json(run_dir / "run.json", run)
            self.write_json(unit_path, unit)
            run["metrics"].update({"unit_count": 1, "review_rounds": 1})
            self.write_json(run_dir / "run.json", run)
            self.write_events(run_dir, [("run", "initialized", "contract_locked"), ("run", "contract_locked", "implementing"), ("unit-1", "planned", "implementing"), ("run", "implementing", "reviewing"), ("unit-1", "implementing", "reviewing"), ("unit-1", "reviewing", "passed"), ("run", "reviewing", "final_review"), ("run", "final_review", "completed")])
            self.bind_last_event_digest(run_dir)
            self.write_report_receipt(run_dir)
            self.validate()
            fallback = copy.deepcopy(run)
            fallback["final_review"]["attempts"] = [
                {"model": "gpt-5.6-sol", "effort": "ultra", "status": "unsupported", "thread_id": "ultra-1", "evidence": ["unsupported"], "diff_snapshot": copy.deepcopy(self.snapshot), "diff_digest": self.snapshot["diff_digest"]},
                {"model": "gpt-5.6-sol", "effort": "xhigh", "status": "pass", "thread_id": "fallback-1", "evidence": ["review"], "diff_snapshot": copy.deepcopy(self.snapshot), "diff_digest": self.snapshot["diff_digest"]},
            ]
            self.write_json(run_dir / "run.json", fallback)
            self.write_report_receipt(run_dir)
            self.validate()
            for name, expected in (
                ("unlocked", "completed run requires"),
                ("no passed unit", "completed run requires"),
                ("final review", "completed run requires"),
                ("completed_at", "completed run requires"),
                ("invalid attempts", "completed final review attempts"),
                ("metrics", "metrics.unit_count"),
                ("deviation", "deviations[1] is incomplete"),
                ("deferred security", "deferred_security[1] is incomplete"),
            ):
                with self.subTest(case=name):
                    current_contract = copy.deepcopy(contract)
                    current_run = copy.deepcopy(run)
                    current_unit = copy.deepcopy(unit)
                    if name == "unlocked":
                        current_contract["locked"] = False
                    elif name == "no passed unit":
                        current_unit["status"] = "planned"
                    elif name == "final review":
                        current_run["final_review"]["status"] = "pending"
                    elif name == "completed_at":
                        current_run["completed_at"] = None
                    elif name == "invalid attempts":
                        current_run["final_review"]["attempts"] = [{"model": "gpt-5.6-sol", "effort": "xhigh", "status": "pass", "thread_id": "fallback", "evidence": ["review"], "diff_snapshot": copy.deepcopy(self.snapshot), "diff_digest": self.snapshot["diff_digest"]}]
                    elif name == "metrics":
                        current_run["metrics"]["unit_count"] = 0
                    elif name == "deviation":
                        current_run["deviations"] = [{"summary": "incomplete"}]
                    else:
                        current_run["deferred_security"] = [{"summary": "incomplete"}]
                    self.write_json(run_dir / "contract.json", current_contract)
                    self.write_json(run_dir / "run.json", current_run)
                    self.write_json(unit_path, current_unit)
                    self.assert_invalid(expected)

        def test_malformed_events_file_is_rejected(self) -> None:
            run_dir = self.init_run()
            (run_dir / "events.jsonl").write_text("{not-json}\n", encoding="utf-8")
            self.assert_invalid("invalid events.jsonl")

        def test_invalid_utf8_events_file_is_rejected_without_decode_details(self) -> None:
            run_dir = self.init_run()
            (run_dir / "events.jsonl").write_bytes(b"\xff\xfe\n")
            with self.assertRaises(hwahap_state.HwahapError) as raised:
                self.validate()
            self.assertEqual(raised.exception.code, "HW_STATE_INVALID")
            self.assertEqual(str(raised.exception), "invalid events.jsonl")
            self.assertNotIn("UnicodeDecodeError", str(raised.exception))
