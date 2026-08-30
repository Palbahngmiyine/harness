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
        def test_record_improvement_command_rolls_back_invalid_append(self) -> None:
            run_dir = self.prepare_pending_improvement_run()
            unit_path = run_dir / "units" / "unit-1.json"
            record = self.improvement_record(1, "terra_recovery")
            args = Namespace(
                workspace=str(self.workspace), run_id="test-goal", unit_id="unit-1",
                after_round=record["after_round"], kind=record["kind"],
                failure_signature=record["failure_signature"], root_cause=record["root_cause"],
                hypothesis=record["hypothesis"], action=record["action"],
                strategy_digest="not-a-digest", scope_status=record["scope_status"],
                evidence_ref=record["evidence"], actor="sol-1",
            )
            before = unit_path.read_bytes(), (run_dir / "events.jsonl").read_bytes()
            with self.assertRaises(hwahap_state.HwahapError):
                with redirect_stdout(io.StringIO()):
                    hwahap_state.record_improvement(args)
            self.assertEqual((unit_path.read_bytes(), (run_dir / "events.jsonl").read_bytes()), before)
            args.strategy_digest = record["strategy_digest"]
            with redirect_stdout(io.StringIO()):
                hwahap_state.record_improvement(args)
            self.validate()
            current = json.loads(unit_path.read_text())
            self.assertEqual(current["status"], "recovery")
            events = [json.loads(line) for line in (run_dir / "events.jsonl").read_text().splitlines()]
            self.assertEqual(events[-1]["to"], "recovery")

            current["status"] = "reviewing"
            current["review_history"].append(self.review_round(2, "fail"))
            run = json.loads((run_dir / "run.json").read_text())
            run["status"] = "reviewing"
            self.write_json(run_dir / "run.json", run)
            self.write_json(unit_path, current)
            self.write_events(run_dir, [
                ("run", "initialized", "contract_locked"), ("run", "contract_locked", "implementing"),
                ("unit-1", "planned", "implementing"), ("run", "implementing", "reviewing"),
                ("unit-1", "implementing", "reviewing"), ("run", "reviewing", "recovering"),
                ("unit-1", "reviewing", "recovery"), ("run", "recovering", "implementing"),
                ("unit-1", "recovery", "implementing"), ("run", "implementing", "reviewing"),
                ("unit-1", "implementing", "reviewing"),
            ])
            second = self.improvement_record(2, "sol_replan")
            args.after_round = second["after_round"]
            args.kind = second["kind"]
            args.failure_signature = second["failure_signature"]
            args.root_cause = second["root_cause"]
            args.hypothesis = second["hypothesis"]
            args.action = second["action"]
            args.strategy_digest = second["strategy_digest"]
            args.evidence_ref = second["evidence"]
            with redirect_stdout(io.StringIO()):
                hwahap_state.record_improvement(args)
            self.validate()
            current = json.loads(unit_path.read_text())
            self.assertEqual(current["status"], "replan_required")
            self.assertEqual(current["failure"]["code"], "HW_REPLAN_REQUIRED")
            self.assertEqual(json.loads((run_dir / "events.jsonl").read_text().splitlines()[-1])["to"], "replan_required")

        def test_record_improvement_rejects_traversal_before_external_access(self) -> None:
            run_dir = self.init_run()
            victim_id = f"hwahap-victim-{self.workspace.name}"
            victim = self.workspace.parent / f"{victim_id}.json"
            victim.write_bytes(b"do not modify\n")
            victim_mtime = victim.stat().st_mtime_ns
            state_paths = (run_dir / "contract.json", run_dir / "run.json", run_dir / "events.jsonl")
            before = tuple(path.read_bytes() for path in state_paths)
            traversal = f"../../../../../{victim_id}"
            legacy_unit_path = (run_dir / "units" / f"{traversal}.json").resolve()
            self.assertEqual(legacy_unit_path, victim.resolve())
            args = Namespace(workspace=str(self.workspace), run_id="test-goal", unit_id=traversal)

            with self.assertRaises(hwahap_state.HwahapError) as raised:
                hwahap_state.record_improvement(args)

            self.assertEqual(raised.exception.code, "HW_STATE_INVALID")
            self.assertEqual(victim.read_bytes(), b"do not modify\n")
            self.assertEqual(victim.stat().st_mtime_ns, victim_mtime)
            self.assertEqual(tuple(path.read_bytes() for path in state_paths), before)
