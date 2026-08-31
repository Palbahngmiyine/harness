try:
    from .test_installer_faultkit import InstallerFaultMixin, installer
except ImportError:
    from test_installer_faultkit import InstallerFaultMixin, installer
import unittest


class UpstreamInstallerFileExistsTests(InstallerFaultMixin, unittest.TestCase):
    def test_file_exists_race_preserves_racing_target(self):
        for index in (1, 2, 3):
            with self.subTest(index=index):
                workspace, profiles, unrelated, config = self.prepare_partial_workspace(f"file-exists-race-{index}")
                racing = workspace / ".codex" / "agents" / profiles[index][0].name
                with self.assertRaises(installer.InstallError) as raised:
                    self.install_with_open_failure(workspace, profiles, index, "race")
                self.assertEqual(raised.exception.code, "HW_AGENT_CONFLICT")
                self.assertNotIn("race-canary", str(raised.exception))
                self.assertEqual(racing.read_bytes(), b"race-canary")
                self.assertEqual(unrelated.read_bytes(), b"name = 'unrelated'\n")
                self.assertEqual((workspace / ".codex" / "config.toml").read_bytes(), config)
                for path, _ in profiles[1:]:
                    if path.name != racing.name:
                        self.assertFalse((workspace / ".codex" / "agents" / path.name).exists())

    def test_race_replacement_is_not_deleted(self):
        workspace, profiles, unrelated, config = self.prepare_partial_workspace("race-replacement")
        prior = workspace / ".codex" / "agents" / profiles[1][0].name
        racing = workspace / ".codex" / "agents" / profiles[2][0].name
        with self.assertRaises(installer.InstallError) as raised:
            self.install_with_open_failure(workspace, profiles, 2, "race-replace")
        self.assertEqual(raised.exception.code, "HW_AGENT_INSTALL_FAILED")
        self.assertEqual(str(raised.exception), "profile installation conflict; rollback incomplete")
        self.assertEqual(prior.read_bytes(), b"replacement-canary")
        self.assertEqual(racing.read_bytes(), b"race-canary")
        self.assertEqual(unrelated.read_bytes(), b"name = 'unrelated'\n")
        self.assertEqual((workspace / ".codex" / "config.toml").read_bytes(), config)
