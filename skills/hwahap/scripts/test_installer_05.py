try:
    from .test_installerkit import InstallerFixture, installer
except ImportError:
    from test_installerkit import InstallerFixture, installer
import os
import unittest
from unittest.mock import patch


class InstallerRaceTests(InstallerFixture, unittest.TestCase):
    def test_exclusive_create_preserves_racing_target(self):
        profiles = self.profiles()
        agents = self.agents()
        agents.mkdir(parents=True)
        count = 0
        original = installer.os.open
        racing = agents / profiles[0][0].name

        def race(name, flags, mode=0o777, *, dir_fd=None):
            nonlocal count
            if flags & os.O_CREAT and flags & os.O_EXCL:
                count += 1
                if count == 1:
                    racing.write_bytes(b"racing")
                    raise FileExistsError("race")
            return original(name, flags, mode, dir_fd=dir_fd)

        with patch.object(installer.os, "open", new=race):
            with self.assertRaises(installer.InstallError) as error:
                self.run_install()
        self.assertEqual(error.exception.code, "HW_AGENT_CONFLICT")
        self.assertEqual(racing.read_bytes(), b"racing")
        self.assertEqual(tuple(p.name for p in agents.glob("*.toml")), (racing.name,))

    def test_replaced_created_target_is_not_deleted_during_rollback(self):
        profiles = self.profiles()
        agents = self.agents()
        agents.mkdir(parents=True)
        original = installer.os.fdopen
        calls = 0

        class Faulty:
            def __init__(self, handle): self.handle = handle
            def __enter__(self): self.handle.__enter__(); return self
            def __exit__(self, kind, value, trace): return self.handle.__exit__(kind, value, trace)
            def write(self, data):
                nonlocal calls
                calls += 1
                result = self.handle.write(data)
                if calls == 2:
                    path = agents / profiles[0][0].name
                    path.unlink()
                    path.write_bytes(b"replacement")
                    raise OSError("write")
                return result

        def fdopen(handle, *args, **kwargs): return Faulty(original(handle, *args, **kwargs))
        with patch.object(installer.os, "fdopen", new=fdopen):
            with self.assertRaises(installer.InstallError): self.run_install()
        self.assertEqual((agents / profiles[0][0].name).read_bytes(), b"replacement")
