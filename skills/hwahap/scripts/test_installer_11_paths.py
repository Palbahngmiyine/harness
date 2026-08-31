try:
    from .test_installerkit import InstallerFixture, installer
except ImportError:
    from test_installerkit import InstallerFixture, installer
import unittest


class InstallerPathTests(InstallerFixture, unittest.TestCase):
    def test_ancestor_symlink_workspace_fails_without_creating_state(self):
        target_parent = self.root / "target-parent"
        target_parent.joinpath("project").mkdir(parents=True)
        alias_parent = self.root / "alias-parent"
        alias_parent.symlink_to(target_parent, target_is_directory=True)
        workspace = alias_parent / "project"
        with self.assertRaises(installer.InstallError) as raised:
            self.run_install(workspace)
        self.assertEqual(raised.exception.code, "HW_AGENT_PATH_INVALID")
        self.assertFalse((target_parent / "project" / ".codex").exists())


if __name__ == "__main__":
    unittest.main()
