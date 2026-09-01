try:
    from .test_statekit_base import *
    from .test_statekit_01 import *
    from .test_statekit_02 import *
except ImportError:
    from test_statekit_base import *
    from test_statekit_01 import *
    from test_statekit_02 import *
import stat


class HwahapStateCase67(StateFixtureMixin01, StateFixtureMixin02, unittest.TestCase):
    def test_new_state_directories_are_private_and_owned(self) -> None:
        run_dir = self.init_run()
        for path in (run_dir, run_dir / "units"):
            info = path.stat()
            self.assertTrue(stat.S_ISDIR(info.st_mode))
            self.assertEqual(stat.S_IMODE(info.st_mode), 0o700)
            self.assertEqual(info.st_uid, os.geteuid())
        self.validate()

    def test_validation_rejects_tampered_mode_type_and_owner(self) -> None:
        run_dir = self.init_run()
        run_dir.chmod(0o755)
        self.assert_invalid()
        run_dir.chmod(0o700)
        units = run_dir / "units"
        units.chmod(0o755)
        self.assert_invalid()
        units.chmod(0o700)
        units.rmdir()
        units.write_text("unsafe\n", encoding="utf-8")
        self.assert_invalid()
        units.unlink()
        units.mkdir(mode=0o700)
        with patch.object(hwahap_state.os, "geteuid", return_value=os.geteuid() + 1):
            self.assert_invalid()

    def test_parent_directories_are_not_repaired(self) -> None:
        hwahap_dir = self.workspace / ".hwahap"
        runs_dir = hwahap_dir / "runs"
        hwahap_dir.mkdir()
        runs_dir.mkdir()
        hwahap_dir.chmod(0o755)
        runs_dir.chmod(0o755)
        self.init_run()
        self.assertEqual(stat.S_IMODE(hwahap_dir.stat().st_mode), 0o755)
        self.assertEqual(stat.S_IMODE(runs_dir.stat().st_mode), 0o755)


if __name__ == "__main__":
    unittest.main()
