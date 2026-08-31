try:
    from .test_installer_faultkit import InstallerFaultMixin, installer
except ImportError:
    from test_installer_faultkit import InstallerFaultMixin, installer
import unittest
from unittest.mock import patch


class UpstreamInstallerWriteRaceTests(InstallerFaultMixin, unittest.TestCase):
    def test_close_failure_and_cleanup_failure_are_stable(self):
        workspace, profiles, unrelated, config = self.prepare_partial_workspace("close-failure")
        with self.assertRaises(installer.InstallError) as raised:
            self.install_with_open_failure(workspace, profiles, 2, "close")
        self.assertEqual(raised.exception.code, "HW_AGENT_INSTALL_FAILED")
        self.assertNotIn("canary", str(raised.exception))
        agents = workspace / ".codex" / "agents"
        self.assertFalse((agents / profiles[1][0].name).exists())
        self.assertFalse((agents / profiles[2][0].name).exists())
        self.assertEqual(unrelated.read_bytes(), b"name = 'unrelated'\n")
        self.assertEqual((workspace / ".codex" / "config.toml").read_bytes(), config)

        workspace, profiles, unrelated, config = self.prepare_partial_workspace("cleanup-failure")
        failing = workspace / ".codex" / "agents" / profiles[1][0].name
        original_unlink = installer.os.unlink
        def fail_one(name, *args, **kwargs):
            if name == failing.name: raise OSError("unlink-canary")
            return original_unlink(name, *args, **kwargs)
        with patch.object(installer.os, "unlink", new=fail_one):
            with self.assertRaises(installer.InstallError) as raised:
                self.install_with_open_failure(workspace, profiles, 2, "write")
        self.assertEqual(raised.exception.code, "HW_AGENT_INSTALL_FAILED")
        self.assertEqual(str(raised.exception), "profile installation failed; rollback incomplete")
        self.assertNotIn("canary", str(raised.exception)); self.assertTrue(failing.exists())
        self.assertFalse((workspace / ".codex" / "agents" / profiles[2][0].name).exists())
        self.assertEqual(unrelated.read_bytes(), b"name = 'unrelated'\n")
        self.assertEqual((workspace / ".codex" / "config.toml").read_bytes(), config)

    def test_write_failures_rollback_all_new_profiles(self):
        for index in (2, 3, 4):
            with self.subTest(index=index):
                workspace, profiles, unrelated, config = self.prepare_partial_workspace(f"write-failure-{index}")
                with self.assertRaises(installer.InstallError) as raised:
                    self.install_with_open_failure(workspace, profiles, index, "write")
                self.assertEqual(raised.exception.code, "HW_AGENT_INSTALL_FAILED")
                self.assertNotIn("canary", str(raised.exception)); self.assertNotIn(str(workspace), str(raised.exception))
                agents = workspace / ".codex" / "agents"
                self.assertEqual(unrelated.read_bytes(), b"name = 'unrelated'\n")
                self.assertEqual((workspace / ".codex" / "config.toml").read_bytes(), config)
                self.assertEqual((agents / profiles[0][0].name).read_bytes(), profiles[0][1])
                for path, _ in profiles[1:]: self.assertFalse((agents / path.name).exists())

    def test_write_failure_replacement_is_not_deleted(self):
        workspace, profiles, unrelated, config = self.prepare_partial_workspace("write-replacement")
        prior = workspace / ".codex" / "agents" / profiles[1][0].name
        with self.assertRaises(installer.InstallError) as raised:
            self.install_with_open_failure(workspace, profiles, 2, "write-replace")
        self.assertEqual(raised.exception.code, "HW_AGENT_INSTALL_FAILED")
        self.assertEqual(str(raised.exception), "profile installation failed; rollback incomplete")
        self.assertEqual(prior.read_bytes(), b"replacement-canary")
        self.assertFalse((workspace / ".codex" / "agents" / profiles[2][0].name).exists())
        self.assertEqual(unrelated.read_bytes(), b"name = 'unrelated'\n")
        self.assertEqual((workspace / ".codex" / "config.toml").read_bytes(), config)
