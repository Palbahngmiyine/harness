try:
    from .test_installerkit import *
except ImportError:
    from test_installerkit import *

from pathlib import Path
from unittest.mock import patch


class InstallerFailureTests(InstallerFixture, unittest.TestCase):
    def test_source_invalid_before_workspace_mutation(self):
        source = self.root / "source"
        source.mkdir()
        source.joinpath("hwahap-luna-implementer.toml").write_bytes(b"bad")
        with patch.object(installer, "PROFILE_DIR", source):
            with self.assertRaises(installer.InstallError):
                installer.install(str(self.root / "new"))
        self.assertFalse((self.root / "new/.codex").exists())

    def test_symlink_workspace_and_target_rejected(self):
        target = self.root / "target"
        target.mkdir()
        link = self.root / "link"
        link.symlink_to(target)
        with self.assertRaises(installer.InstallError) as error:
            installer.install(str(link))
        self.assertEqual(error.exception.code, "HW_AGENT_PATH_INVALID")
        agents = target / ".codex/agents"
        agents.mkdir(parents=True)
        profile = agents / installer.source_profiles()[0][0].name
        profile.symlink_to(self.root / "other")
        with self.assertRaises(installer.InstallError) as error:
            installer.install(str(target))
        self.assertEqual(error.exception.code, "HW_AGENT_PATH_INVALID")

    def test_failed_write_rolls_back_created_profiles(self):
        original = Path.open
        calls = 0

        def fail_second(path, mode="r", *args, **kwargs):
            nonlocal calls
            if mode == "xb":
                calls += 1
                if calls == 2:
                    raise OSError("write")
            return original(path, mode, *args, **kwargs)

        with patch.object(installer.Path, "open", new=fail_second):
            with self.assertRaises(installer.InstallError) as error:
                installer.install(str(self.root))
        self.assertEqual(error.exception.code, "HW_AGENT_INSTALL_FAILED")
        agents = self.root / ".codex/agents"
        self.assertEqual(list(agents.iterdir()), [])
