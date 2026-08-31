try:
    from .test_installerkit import InstallerFixture, installer
except ImportError:
    from test_installerkit import InstallerFixture, installer
import unittest
from unittest.mock import patch


class InstallerLateExtraTests(InstallerFixture, unittest.TestCase):
    def test_late_unexpected_profile_rolls_back_and_normalizes_error(self):
        profiles = installer.source_profiles()
        agents = self.agents()
        agents.mkdir(parents=True)
        (agents / profiles[0][0].name).write_bytes(profiles[0][1])
        (agents / "user-agent.toml").write_bytes(b"unrelated")
        config = self.root / ".codex/config.toml"
        config.write_bytes(b"[keep]\n")
        failing = agents / profiles[1][0].name
        original_open = installer.os.open
        original_unlink = installer.os.unlink
        calls = 0

        def add_late_extra(name, flags, mode=0o777, *, dir_fd=None):
            nonlocal calls
            if flags & installer.os.O_CREAT and flags & installer.os.O_EXCL:
                calls += 1
                if calls == 4:
                    (agents / "hwahap-extra.toml").write_bytes(b"extra-canary")
            return original_open(name, flags, mode, dir_fd=dir_fd)

        def fail_cleanup(name, *args, **kwargs):
            if name == failing.name:
                raise OSError("unlink-canary")
            return original_unlink(name, *args, **kwargs)

        with patch.object(installer.os, "open", new=add_late_extra), \
                patch.object(installer.os, "unlink", new=fail_cleanup):
            with self.assertRaises(installer.InstallError) as raised:
                self.run_install()
        self.assertEqual(raised.exception.code, "HW_AGENT_INSTALL_FAILED")
        self.assertEqual(str(raised.exception),
                         "profile installation conflict; rollback incomplete")
        self.assertTrue(failing.exists())
        self.assertEqual((agents / "hwahap-extra.toml").read_bytes(), b"extra-canary")
        self.assertEqual((agents / "user-agent.toml").read_bytes(), b"unrelated")
        self.assertEqual(config.read_bytes(), b"[keep]\n")
