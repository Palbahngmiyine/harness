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
    def test_failed_round_improvement_reenters_next_review(self) -> None:
        run_dir = self.prepare_pending_improvement_run()
        record = self.improvement_record(1, "terra_recovery")
        args = Namespace(
            workspace=str(self.workspace), run_id="test-goal", unit_id="unit-1",
            after_round=1, kind=record["kind"], failure_signature=record["failure_signature"],
            root_cause=record["root_cause"], hypothesis=record["hypothesis"],
            action=record["action"], strategy_digest=record["strategy_digest"],
            scope_status=record["scope_status"], evidence_ref=record["evidence"], actor="sol-1",
        )
        with redirect_stdout(io.StringIO()):
            hwahap_state.record_improvement(args)
        for entity, target in (("run", "implementing"), ("unit-1", "implementing"),
                               ("run", "reviewing"), ("unit-1", "reviewing")):
            with redirect_stdout(io.StringIO()):
                hwahap_state.transition(self.transition_args(entity, target))
        self.validate()
        unit = json.loads((run_dir / "units" / "unit-1.json").read_text())
        self.assertEqual(unit["status"], "reviewing")
        self.assertEqual(unit["review_history"][-1]["round"], 1)
        self.assertEqual(unit["improvement_history"][-1]["after_round"], 1)

    def test_implementing_rejects_unresolved_failed_round(self) -> None:
        run_dir = self.prepare_pending_improvement_run()
        unit_path, run_path = run_dir / "units" / "unit-1.json", run_dir / "run.json"
        unit = json.loads(unit_path.read_text())
        run = json.loads(run_path.read_text())
        unit["status"], unit["improvement_history"] = "implementing", []
        run["status"] = "implementing"
        self.write_json(unit_path, unit)
        self.write_json(run_path, run)
        self.write_events(run_dir, [
            ("run", "initialized", "contract_locked"),
            ("run", "contract_locked", "implementing"),
            ("unit-1", "planned", "implementing"),
        ])
        self.assert_invalid("requires improvement")
