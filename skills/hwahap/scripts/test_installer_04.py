try:
    from .test_installerkit import InstallerFixture, installer
except ImportError:
    from test_installerkit import InstallerFixture, installer
import unittest
from unittest.mock import patch


class InstallerRollbackTests(InstallerFixture, unittest.TestCase):
    def test_write_failure_rolls_back_only_new_profiles(self):
        original = installer.os.fdopen
        calls = 0

        class Faulty:
            def __init__(self, handle): self.handle = handle
            def __enter__(self): self.handle.__enter__(); return self
            def __exit__(self, *args): return self.handle.__exit__(*args)
            def write(self, data):
                nonlocal calls
                calls += 1
                result = self.handle.write(data)
                if calls == 2: raise OSError("write")
                return result

        def fdopen(handle, *args, **kwargs):
            return Faulty(original(handle, *args, **kwargs))

        with patch.object(installer.os, "fdopen", new=fdopen):
            with self.assertRaises(installer.InstallError) as error:
                self.run_install()
        self.assertEqual(error.exception.code, "HW_AGENT_INSTALL_FAILED")
        self.assertEqual(tuple(self.agents().iterdir()), ())

    def test_preflight_conflict_preserves_existing_and_config(self):
        profiles = self.profiles()
        agents = self.agents()
        agents.mkdir(parents=True)
        existing = agents / profiles[0][0].name
        existing.write_bytes(profiles[0][1])
        conflict = agents / profiles[1][0].name
        conflict.write_bytes(b"conflict")
        config = self.root / ".codex/config.toml"
        config.write_bytes(b"[keep]\n")
        self.assert_code("HW_AGENT_CONFLICT")
        self.assertEqual(existing.read_bytes(), profiles[0][1])
        self.assertEqual(conflict.read_bytes(), b"conflict")
        self.assertEqual(config.read_bytes(), b"[keep]\n")
