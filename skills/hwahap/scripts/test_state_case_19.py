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
        def test_git_diff_snapshot_rejects_tampered_fields_and_refs(self) -> None:
            repo = self.workspace / "snapshot-tamper"
            repo.mkdir()
            def git(*args: str) -> str:
                return subprocess.run(["git", *args], cwd=repo, check=True, stdout=subprocess.PIPE,
                                      stderr=subprocess.DEVNULL, text=True).stdout.strip()
            git("init", "-q")
            git("config", "user.email", "test@example.invalid")
            git("config", "user.name", "Hwahap Test")
            (repo / "src").write_text("one\n", encoding="utf-8")
            git("add", "src")
            git("commit", "-qm", "one")
            base = git("rev-parse", "HEAD")
            (repo / "src").write_text("two\n", encoding="utf-8")
            git("commit", "-qam", "two")
            target = git("rev-parse", "HEAD")
            snapshot = hwahap_state.git_diff_snapshot(repo, base, target)
            for field, value in (("diff_digest", "sha256:" + "f" * 64), ("changed_paths", ["other"]),
                                 ("base_tree", "0" * 40), ("target_commit", "1" * 40)):
                tampered = {**snapshot, field: value}
                errors: list[str] = []
                hwahap_state.validate_diff_snapshot(tampered, repo, "snapshot", errors)
                self.assertTrue(errors)

        def test_git_snapshot_ignores_redirects_replace_dirty_tree_and_diff_config(self) -> None:
            expected = self.snapshot
            fake_dir = self.workspace / "fake-bin"
            fake_dir.mkdir()
            marker = self.workspace / "fake-git-called"
            fake = fake_dir / "git"
            fake.write_text(f"#!/bin/sh\ntouch '{marker}'\nexit 99\n", encoding="utf-8")
            fake.chmod(0o755)
            other = self.workspace / "other-repo"
            other.mkdir()
            subprocess.run(["git", "init", "-q"], cwd=other, check=True, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
            with patch.dict(os.environ, {"GIT_DIR": str(other / ".git"), "GIT_WORK_TREE": str(other), "GIT_INDEX_FILE": "bad"}):
                self.assertEqual(hwahap_state.git_diff_snapshot(self.workspace, self.base_commit, self.target_commit), expected)
            with patch.dict(os.environ, {"PATH": str(fake_dir) + os.pathsep + os.environ.get("PATH", "")}):
                self.assertEqual(hwahap_state.git_diff_snapshot(self.workspace, self.base_commit, self.target_commit), expected)
            self.assertFalse(marker.exists())
            nested = self.workspace / "nested"
            nested.mkdir()
            with self.assertRaises(hwahap_state.HwahapError):
                hwahap_state.git_diff_snapshot(nested, self.base_commit, self.target_commit)
            src = self.workspace / "src"
            src.write_text("dirty\n", encoding="utf-8")
            try:
                subprocess.run(["git", "config", "diff.renames", "true"], cwd=self.workspace, check=True,
                               stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
                subprocess.run(["git", "replace", self.base_commit, self.target_commit], cwd=self.workspace, check=True,
                               stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
                self.assertEqual(hwahap_state.git_diff_snapshot(self.workspace, self.base_commit, self.target_commit), expected)
            finally:
                subprocess.run(["git", "replace", "-d", self.base_commit], cwd=self.workspace, check=False,
                               stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)

        def test_init_event_write_failure_removes_only_new_state(self) -> None:
            hwahap_dir, runs_dir = self.workspace / ".hwahap", self.workspace / ".hwahap" / "runs"
            hwahap_dir.mkdir()
            runs_dir.mkdir()
            run_dir = runs_dir / "test-goal"
            events_path = run_dir / "events.jsonl"
            original_write_text = Path.write_text

            def fail_events(path: Path, *args: object, **kwargs: object) -> int:
                if path == events_path:
                    raise OSError("secret init event write")
                return original_write_text(path, *args, **kwargs)

            with patch.object(Path, "write_text", new=fail_events):
                with self.assertRaises(hwahap_state.HwahapError) as raised:
                    hwahap_state.init_run(Namespace(
                        workspace=str(self.workspace), goal_id="test-goal", spec=str(self.spec)))
            self.assertEqual(raised.exception.code, "HW_STATE_INVALID")
            self.assertNotIn("secret init event write", str(raised.exception))
            self.assertTrue(hwahap_dir.is_dir())
            self.assertTrue(runs_dir.is_dir())
            self.assertFalse(run_dir.exists())
