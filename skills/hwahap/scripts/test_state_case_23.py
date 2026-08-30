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
        def test_request_lock_requires_bound_goal_without_mutating_bytes(self) -> None:
            run_dir = self.init_request_run()
            self._fill_request_contract(run_dir)
            before = {name: (run_dir / name).read_bytes() for name in ("contract.json", "run.json", "events.jsonl")}
            with self.assertRaises(hwahap_state.HwahapError) as raised:
                hwahap_state.lock_contract(self.request_lock_args())
            self.assertEqual(raised.exception.code, "HW_GOAL_REQUIRED")
            self.assertEqual(before, {name: (run_dir / name).read_bytes() for name in before})

        def test_request_bound_goal_then_lock_succeeds(self) -> None:
            run_dir = self.init_request_run()
            self._fill_request_contract(run_dir)
            with redirect_stdout(io.StringIO()):
                hwahap_state.goal_sync(self.goal_args(
                    "bound", thread_id="goal-thread", objective_sha256="sha256:" + "a" * 64,
                    receipt_sha256="sha256:" + "b" * 64, run_id="request-goal"))
                hwahap_state.lock_contract(self.request_lock_args())
            self.assertEqual(json.loads((run_dir / "contract.json").read_text())["locked"], True)
            self.assertEqual(json.loads((run_dir / "run.json").read_text())["status"], "contract_locked")

        def test_unconfirmed_spec_is_rejected(self) -> None:
            self.spec.write_text("---\ntitle: Test goal\nstatus: draft\n---\n", encoding="utf-8")
            args = Namespace(workspace=str(self.workspace), goal_id="test-goal", spec=str(self.spec))
            with self.assertRaises(hwahap_state.HwahapError) as raised:
                hwahap_state.init_run(args)
            self.assertEqual(raised.exception.code, "HW_SPEC_UNCONFIRMED")

        def test_invalid_utf8_spec_is_a_stable_spec_error(self) -> None:
            self.spec.write_bytes(b"\xff\xfe\xfd")
            with self.assertRaises(hwahap_state.HwahapError) as raised:
                hwahap_state.init_run(Namespace(workspace=str(self.workspace), goal_id="bad-utf8", spec=str(self.spec)))
            self.assertEqual(raised.exception.code, "HW_SPEC_UNCONFIRMED")
            self.assertIn("spec cannot be read", str(raised.exception))

        def test_spec_read_oserror_does_not_echo_secret_or_create_state(self) -> None:
            sentinel = "SECRET_PATH=/private/tmp/do-not-echo"
            with patch.object(hwahap_state.Path, "read_bytes", side_effect=OSError(sentinel)):
                with self.assertRaises(hwahap_state.HwahapError) as raised:
                    hwahap_state.init_run(Namespace(
                        workspace=str(self.workspace), goal_id="read-error", spec=str(self.spec)))
            self.assertEqual(raised.exception.code, "HW_SPEC_UNCONFIRMED")
            self.assertEqual(str(raised.exception), "spec cannot be read as approved UTF-8")
            self.assertNotIn(sentinel, str(raised.exception))
            self.assertFalse((self.workspace / ".hwahap").exists())

        def test_installed_agent_read_failures_are_generic_before_run_creation(self) -> None:
            agents = self.workspace / ".codex" / "agents"
            target = agents / "hwahap-luna-verifier.toml"
            original_iterdir, original_read = Path.iterdir, Path.read_bytes
            for kind in ("iterdir", "read"):
                with self.subTest(kind=kind):
                    marker = f"Proxy-Authorization: Digest /private/tmp/{kind}-canary"
                    def fail_iterdir(path: Path):
                        if path == agents:
                            raise OSError(marker)
                        return original_iterdir(path)
                    def fail_read(path: Path, *args: object, **kwargs: object):
                        if path == target:
                            raise OSError(marker)
                        return original_read(path, *args, **kwargs)
                    patcher = patch.object(Path, "iterdir", new=fail_iterdir) if kind == "iterdir" else patch.object(Path, "read_bytes", new=fail_read)
                    with patcher:
                        with self.assertRaises(hwahap_state.HwahapError) as raised:
                            hwahap_state.init_run(Namespace(workspace=str(self.workspace), goal_id=f"bad-{kind}", spec=str(self.spec)))
                    self.assertEqual(raised.exception.code, "HW_AGENT_CONFIG_INVALID")
                    self.assertNotIn(marker, str(raised.exception))
                    self.assertFalse((self.workspace / ".hwahap" / "runs" / f"bad-{kind}").exists())
