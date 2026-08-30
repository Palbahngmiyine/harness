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
        def test_same_spec_idempotence_validates_entire_existing_run(self) -> None:
            run_dir = self.init_run()
            args = Namespace(workspace=str(self.workspace), goal_id="test-goal", spec=str(self.spec))
            run_path = run_dir / "run.json"
            run = json.loads(run_path.read_text())
            run["status"] = []
            self.write_json(run_path, run)
            with self.assertRaises(hwahap_state.HwahapError) as raised:
                hwahap_state.init_run(args)
            self.assertEqual(raised.exception.code, "HW_STATE_INVALID")
            run["status"] = "initialized"
            self.write_json(run_path, run)
            (run_dir / "events.jsonl").write_text("{bad}\n", encoding="utf-8")
            with self.assertRaises(hwahap_state.HwahapError) as raised:
                hwahap_state.init_run(args)
            self.assertEqual(raised.exception.code, "HW_STATE_INVALID")

        def test_all_state_paths_require_real_expected_types(self) -> None:
            init_symlinks = {"hwahap", "runs", "run"}
            for name in ("hwahap", "runs", "run", "units", "contract", "run.json", "events", "unit"):
                with self.subTest(path=name):
                    workspace = self.workspace / name
                    workspace.mkdir()
                    self.install_agents(workspace)
                    spec = workspace / "spec.md"
                    spec.write_text(self.spec.read_text(encoding="utf-8"), encoding="utf-8")
                    hwahap = workspace / ".hwahap"
                    if name == "hwahap":
                        target = workspace / "hwahap-target"
                        target.mkdir()
                        os.symlink(target, hwahap)
                    elif name == "runs":
                        hwahap.mkdir()
                        target = workspace / "runs-target"
                        target.mkdir()
                        os.symlink(target, hwahap / "runs")
                    elif name == "run":
                        (hwahap / "runs").mkdir(parents=True)
                        target = workspace / "run-target"
                        target.mkdir()
                        os.symlink(target, hwahap / "runs" / "test-goal")
                    else:
                        args = Namespace(workspace=str(workspace), goal_id="test-goal", spec=str(spec))
                        with redirect_stdout(io.StringIO()):
                            hwahap_state.init_run(args)
                        run_dir = hwahap / "runs" / "test-goal"
                        if name == "units":
                            units = run_dir / "units"
                            units.rmdir()
                            target = workspace / "units-target"
                            target.mkdir()
                            os.symlink(target, units)
                        else:
                            path = {
                                "contract": run_dir / "contract.json",
                                "run.json": run_dir / "run.json",
                                "events": run_dir / "events.jsonl",
                                "unit": run_dir / "units" / "unit-1.json",
                            }[name]
                            target = workspace / f"{name}-target"
                            target.write_text("{}\n", encoding="utf-8")
                            if path.exists():
                                path.unlink()
                            os.symlink(target, path)
                    args = Namespace(workspace=str(workspace), goal_id="test-goal", spec=str(spec))
                    if name in init_symlinks:
                        with self.assertRaises(hwahap_state.HwahapError) as raised:
                            hwahap_state.init_run(args)
                        self.assertEqual(raised.exception.code, "HW_STATE_INVALID")
                    else:
                        self.assert_invalid_at(workspace)

        def test_locked_contract_digest_rejects_mutation(self) -> None:
            run_dir = self.init_run()
            self.lock_contract(run_dir)
            self.validate()
            contract_path = run_dir / "contract.json"
            contract = json.loads(contract_path.read_text())
            contract["goals"] = ["mutated"]
            self.write_json(contract_path, contract)
            self.assert_invalid("lock_sha256")
