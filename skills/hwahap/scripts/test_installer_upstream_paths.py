try:
    from .test_installer_faultkit import InstallerFaultMixin, installer
except ImportError:
    from test_installer_faultkit import InstallerFaultMixin, installer
import unittest


class UpstreamInstallerPathTests(InstallerFaultMixin, unittest.TestCase):
    def test_missing_or_non_directory_workspace_fails(self):
        with self.assertRaises(installer.InstallError) as raised:
            self.run_install(self.root / "missing")
        self.assertEqual(raised.exception.code, "HW_AGENT_PATH_INVALID")
        file_path = self.root / "workspace-file"; file_path.write_text("not a directory")
        with self.assertRaises(installer.InstallError) as raised:
            self.run_install(file_path)
        self.assertEqual(raised.exception.code, "HW_AGENT_PATH_INVALID")

    def test_symlink_workspace_fails_before_resolve(self):
        target = self.root / "real-workspace"; target.mkdir()
        link = self.root / "workspace-link"; link.symlink_to(target, target_is_directory=True)
        with self.assertRaises(installer.InstallError) as raised: self.run_install(link)
        self.assertEqual(raised.exception.code, "HW_AGENT_PATH_INVALID")
        self.assertFalse((target / ".codex").exists())

    def test_symlinked_state_paths_fail_closed(self):
        for name in ("codex", "agents", "target"):
            with self.subTest(path=name):
                workspace = self.root / name; workspace.mkdir()
                codex = workspace / ".codex"; target = workspace / f"{name}-target"; target.mkdir()
                if name == "codex": codex.symlink_to(target, target_is_directory=True)
                else:
                    codex.mkdir(); agents = codex / "agents"
                    if name == "agents": agents.symlink_to(target, target_is_directory=True)
                    else:
                        agents.mkdir(); profile = installer.source_profiles()[0][0].name
                        target_file = workspace / "profile-target"; target_file.write_bytes(b"existing")
                        (agents / profile).symlink_to(target_file)
                with self.assertRaises(installer.InstallError) as raised: self.run_install(workspace)
                self.assertEqual(raised.exception.code, "HW_AGENT_PATH_INVALID")

    def test_symlink_path_error_does_not_echo_workspace(self):
        target = self.root / "real"; target.mkdir(); link = self.root / "link"
        link.symlink_to(target, target_is_directory=True)
        with self.assertRaises(installer.InstallError) as raised: self.run_install(link)
        self.assertEqual(raised.exception.code, "HW_AGENT_PATH_INVALID")
        self.assertNotIn(str(link), str(raised.exception))
