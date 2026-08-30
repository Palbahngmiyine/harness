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
        def test_goal_complete_sync_rollback_failure_is_generic_and_attempts_all_files(self) -> None:
            run_dir = self.prepare_final_review()
            with redirect_stdout(io.StringIO()):
                hwahap_state.complete_run(self.complete_args())
            run_path, report_path = run_dir / "run.json", run_dir / "report.html"
            run_before, report_before = run_path.read_bytes(), report_path.read_bytes()
            original_atomic = hwahap_state._atomic_replace_bytes
            calls: list[Path] = []
            def flaky_write(path: Path, data: bytes) -> None:
                calls.append(path)
                if path == run_path:
                    raise OSError("/private/tmp/Authorization: Bearer rollback-canary")
                return original_atomic(path, data)
            original_validate = hwahap_state.validate_run
            validations = 0
            def fail_after_write(args: Namespace) -> None:
                nonlocal validations
                validations += 1
                if validations > 1:
                    raise hwahap_state.HwahapError("HW_STATE_INVALID", "/private/tmp/auth-canary")
                original_validate(args)
            hwahap_state.validate_run = fail_after_write
            try:
                with patch.object(hwahap_state, "_atomic_replace_bytes", new=flaky_write):
                    with self.assertRaises(hwahap_state.HwahapError) as raised:
                        hwahap_state.goal_complete_sync(self.goal_complete_args())
            finally:
                hwahap_state.validate_run = original_validate
            self.assertEqual(raised.exception.code, "HW_REPORT_GENERATION_FAILED")
            self.assertEqual(str(raised.exception), "Goal completion report generation failed")
            self.assertNotIn("canary", str(raised.exception))
            self.assertIn(run_path, calls)
            self.assertIn(report_path, calls)
            self.assertEqual(report_path.read_bytes(), report_before)
            self.assertEqual(run_path.read_bytes(), run_before)

        def test_approved_spec_init_and_validate(self) -> None:
            run_dir = self.init_run()
            self.validate()
            goal_link = json.loads((run_dir / "run.json").read_text())["goal_link"]
            self.assertEqual(goal_link["current"]["mode"], "unobserved")
            self.assertEqual(goal_link["history"], [])
            self.assertEqual(json.loads((run_dir / "contract.json").read_text())["locked"], False)
            self.assertEqual(json.loads((run_dir / "run.json").read_text())["status"], "initialized")

        def test_git_diff_snapshot_binds_exact_commits_trees_bytes_and_paths(self) -> None:
            repo = self.workspace / "snapshot-repo"
            repo.mkdir()
            def git(*args: str) -> str:
                return subprocess.run(["git", *args], cwd=repo, check=True, stdout=subprocess.PIPE,
                                      stderr=subprocess.DEVNULL, text=True).stdout.strip()
            git("init", "-q")
            git("config", "user.email", "test@example.invalid")
            git("config", "user.name", "Hwahap Test")
            (repo / "src").write_text("base\n", encoding="utf-8")
            git("add", "src")
            git("commit", "-qm", "base")
            base = git("rev-parse", "HEAD")
            (repo / "src").write_text("target\n", encoding="utf-8")
            git("commit", "-qam", "target")
            target = git("rev-parse", "HEAD")
            snapshot = hwahap_state.git_diff_snapshot(repo, base, target)
            self.assertEqual(snapshot["base_commit"], base)
            self.assertEqual(snapshot["target_commit"], target)
            self.assertEqual(snapshot["changed_paths"], ["src"])
            self.assertEqual(snapshot["base_tree"], git("rev-parse", f"{base}^{{tree}}"))
            self.assertEqual(snapshot["target_tree"], git("rev-parse", f"{target}^{{tree}}"))
            self.assertTrue(hwahap_state.SHA256.fullmatch(snapshot["diff_digest"]))
            with self.assertRaises(hwahap_state.HwahapError) as raised:
                hwahap_state.git_diff_snapshot(self.workspace, base, target)
            self.assertEqual(raised.exception.code, "HW_STATE_INVALID")
