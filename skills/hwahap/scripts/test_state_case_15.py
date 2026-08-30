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
        def test_atomic_report_replace_is_safe_if_target_becomes_hardlink(self) -> None:
            run_dir = self.prepare_final_review()
            targets = {run_dir / name for name in hwahap_state._REPORT_RECOVERY_FILES}
            victims: dict[Path, Path] = {}
            original_replace = os.replace

            def race(source: str, destination: str) -> None:
                path = Path(destination)
                if path in targets:
                    victim = victims.setdefault(path, self.workspace / ("replace-victim-" + path.name))
                    if not victim.exists():
                        victim.write_bytes(b"external-replace-canary")
                    if path.exists():
                        path.unlink()
                    os.link(victim, path)
                original_replace(source, destination)

            with patch.object(hwahap_state.os, "replace", new=race):
                with redirect_stdout(io.StringIO()):
                    hwahap_state.complete_run(self.complete_args())
                with redirect_stdout(io.StringIO()):
                    hwahap_state.goal_complete_sync(self.goal_complete_args())
            for victim in victims.values():
                self.assertEqual(victim.read_bytes(), b"external-replace-canary")
            self.validate()

        def test_atomic_report_temp_collision_preserves_preexisting_temp(self) -> None:
            run_dir = self.prepare_final_review()
            run_path, events_path = run_dir / "run.json", run_dir / "events.jsonl"
            before = (run_path.read_bytes(), events_path.read_bytes())
            old_counter = hwahap_state._REPORT_TEMP_COUNTER
            hwahap_state._REPORT_TEMP_COUNTER = 0
            temp = run_dir / f".run.json.tmp-{os.getpid()}-1"
            temp.write_bytes(b"preexisting-temp-canary")
            try:
                with self.assertRaises(hwahap_state.HwahapError) as raised:
                    hwahap_state.complete_run(self.complete_args())
            finally:
                hwahap_state._REPORT_TEMP_COUNTER = old_counter
            self.assertEqual(raised.exception.code, "HW_REPORT_GENERATION_FAILED")
            self.assertEqual(temp.read_bytes(), b"preexisting-temp-canary")
            self.assertEqual(before, (run_path.read_bytes(), events_path.read_bytes()))

        def test_report_generated_at_is_bound_to_event_or_goal_receipt(self) -> None:
            run_dir = self.prepare_final_review()
            with redirect_stdout(io.StringIO()):
                hwahap_state.complete_run(self.complete_args())
            run_path = run_dir / "run.json"
            run = json.loads(run_path.read_text())
            run["report"]["generated_at"] = "tampered-generated-at"
            self.write_json(run_path, run)
            self.assert_invalid("generated_at")

        def test_physical_report_data_preserves_large_histories(self) -> None:
            run_dir = self.prepare_final_review()
            contract = json.loads((run_dir / "contract.json").read_text())
            run = json.loads((run_dir / "run.json").read_text())
            units = [json.loads(path.read_text()) for path in sorted((run_dir / "units").glob("*.json"))]
            events = [{"timestamp": str(index), "type": "state_transition", "sequence": index,
                       "entity": "run", "from": "reviewing", "to": "reviewing", "actor": "stress",
                       "role": "verifier", "reason": f"event-{index}", "input_digest": "sha256:" + "a" * 64,
                       "evidence_refs": [f"event-{index}"], "review_round": 0} for index in range(1, 502)]
            unit = units[0]
            unit["test_receipts"] = [{"test_id": f"receipt-{index}"} for index in range(1, 102)]
            unit["review_history"] = [{"round": index, "changed_paths": [f"review-{index}"]} for index in range(1, 102)]
            unit["improvement_history"] = [{"after_round": index, "action": f"improvement-{index}"} for index in range(1, 102)]
            run["goal_link"]["history"] = [{"reason": f"goal-{index}"} for index in range(1, 102)]
            run["improvement_candidates"] = [{"summary": f"candidate-{index}"} for index in range(1, 102)]
            digests = hwahap_state.report_state_digests(run_dir / "contract.json", run_dir / "events.jsonl", run_dir / "units")
            payload = hwahap_report.build_payload(self.workspace, contract, run, units, events, digests,
                                                  hwahap_state.build_scope_audit(run, contract, units))
            data = hwahap_report.canonical_payload_bytes(payload)
            html = hwahap_report.render_report(payload, hwahap_report.canonical_payload_digest(payload))
            (run_dir / "report-data.json").write_bytes(data)
            (run_dir / "report.html").write_bytes(html)
            parsed = json.loads((run_dir / "report-data.json").read_bytes())
            self.assertEqual(len(parsed["timeline"]), 501)
            self.assertEqual(len(parsed["units"][0]["test_receipts"]), 101)
            for sentinel in ("event-501", "receipt-101", "review-101", "improvement-101", "goal-101", "candidate-101"):
                self.assertIn(sentinel, (run_dir / "report-data.json").read_text())
                self.assertIn(sentinel, (run_dir / "report.html").read_text())
