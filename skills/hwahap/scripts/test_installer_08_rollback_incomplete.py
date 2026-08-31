try:
    from .test_installerkit import InstallerFixture, installer
except ImportError:
    from test_installerkit import InstallerFixture, installer
import unittest
from unittest.mock import patch


class InstallerRollbackIncompleteTests(InstallerFixture, unittest.TestCase):
    def test_cleanup_failure_reports_incomplete_rollback_without_leaking_detail(self):
        profiles = installer.source_profiles()
        agents = self.agents()
        agents.mkdir(parents=True)
        (agents / "user-agent.toml").write_bytes(b"unrelated")
        config = self.root / ".codex/config.toml"
        config.write_bytes(b"[keep]\n")
        original_fdopen = installer.os.fdopen
        original_unlink = installer.os.unlink
        writes = 0
        failing = agents / profiles[1][0].name

        class FailOnSecondWrite:
            def __init__(self, handle):
                self.handle = handle
            def __enter__(self):
                self.handle.__enter__()
                return self
            def __exit__(self, *args):
                return self.handle.__exit__(*args)
            def write(self, data):
                nonlocal writes
                writes += 1
                result = self.handle.write(data)
                if writes == 2:
                    raise OSError("write-canary")
                return result

        def fdopen(handle, *args, **kwargs):
            return FailOnSecondWrite(original_fdopen(handle, *args, **kwargs))

        def fail_cleanup(name, *args, **kwargs):
            if name == failing.name:
                raise OSError("unlink-canary")
            return original_unlink(name, *args, **kwargs)

        with patch.object(installer.os, "fdopen", new=fdopen), \
                patch.object(installer.os, "unlink", new=fail_cleanup):
            with self.assertRaises(installer.InstallError) as raised:
                self.run_install()
        self.assertEqual(raised.exception.code, "HW_AGENT_INSTALL_FAILED")
        self.assertEqual(str(raised.exception),
                         "profile installation failed; rollback incomplete")
        self.assertTrue(failing.exists())
        self.assertFalse((agents / profiles[0][0].name).exists())
        self.assertEqual((agents / "user-agent.toml").read_bytes(), b"unrelated")
        self.assertEqual(config.read_bytes(), b"[keep]\n")
