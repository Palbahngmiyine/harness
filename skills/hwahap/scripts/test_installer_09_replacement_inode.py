try:
    from .test_installerkit import InstallerFixture, installer
except ImportError:
    from test_installerkit import InstallerFixture, installer
import unittest
from unittest.mock import patch


class InstallerReplacementInodeTests(InstallerFixture, unittest.TestCase):
    def test_replacement_inode_is_preserved_during_rollback(self):
        profiles = installer.source_profiles()
        agents = self.agents()
        agents.mkdir(parents=True)
        (agents / profiles[0][0].name).write_bytes(profiles[0][1])
        target = agents / profiles[1][0].name
        original_fdopen = installer.os.fdopen

        class ReplaceOnWriteFailure:
            def __init__(self, handle):
                self.handle = handle
            def __enter__(self):
                self.handle.__enter__()
                return self
            def __exit__(self, *args):
                result = self.handle.__exit__(*args)
                if args[0] is not None:
                    target.unlink()
                    target.write_bytes(b"replacement-canary")
                return result
            def write(self, data):
                result = self.handle.write(data)
                raise OSError("write-canary")
                return result

        def fdopen(handle, *args, **kwargs):
            return ReplaceOnWriteFailure(original_fdopen(handle, *args, **kwargs))

        with patch.object(installer.os, "fdopen", new=fdopen):
            with self.assertRaises(installer.InstallError) as raised:
                self.run_install()
        self.assertEqual(raised.exception.code, "HW_AGENT_INSTALL_FAILED")
        self.assertEqual(target.read_bytes(), b"replacement-canary")
