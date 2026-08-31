try:
    from .test_installerkit import InstallerFixture, installer
except ImportError:
    from test_installerkit import InstallerFixture, installer
import os
import unittest
from unittest.mock import patch


class InstallerRaceRollbackTests(InstallerFixture, unittest.TestCase):
    def test_file_exists_race_with_incomplete_rollback_is_stable(self):
        profiles = self.profiles()
        agents = self.agents()
        agents.mkdir(parents=True)
        (agents / profiles[0][0].name).write_bytes(profiles[0][1])
        failing = agents / profiles[1][0].name
        racing = agents / profiles[2][0].name
        original_open = installer.os.open
        original_fdopen = installer.os.fdopen
        original_unlink = installer.os.unlink
        calls = 0

        def race(name, flags, mode=0o777, *, dir_fd=None):
            nonlocal calls
            if flags & os.O_CREAT and flags & os.O_EXCL:
                calls += 1
                if calls == 2:
                    fd = original_open(name, flags, mode, dir_fd=dir_fd)
                    with original_fdopen(fd, "wb") as output:
                        output.write(b"race-canary")
                    raise FileExistsError("race-canary")
            return original_open(name, flags, mode, dir_fd=dir_fd)

        def fail_cleanup(name, *args, **kwargs):
            if name == failing.name:
                raise OSError("unlink-canary")
            return original_unlink(name, *args, **kwargs)

        with patch.object(installer.os, "open", new=race), \
                patch.object(installer.os, "unlink", new=fail_cleanup):
            with self.assertRaises(installer.InstallError) as raised:
                self.run_install()
        self.assertEqual(raised.exception.code, "HW_AGENT_INSTALL_FAILED")
        self.assertEqual(str(raised.exception),
                         "profile installation conflict; rollback incomplete")
        self.assertTrue(failing.exists())
        self.assertEqual(racing.read_bytes(), b"race-canary")
        self.assertEqual((agents / profiles[0][0].name).read_bytes(), profiles[0][1])
